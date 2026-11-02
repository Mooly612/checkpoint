"""Transactional local history. Legacy JSON is imported once and never overwritten."""
from __future__ import annotations
from ..i18n import tr

from contextlib import contextmanager, closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .differ import component_hashes, describe, digest


class HistoryError(ValueError):
    """History cannot be read or changed safely."""


def project_key(project_path: str) -> str:
    if not project_path:
        raise ValueError(tr("A saved project needs a path"))
    return hashlib.sha256(os.fsencode(os.path.abspath(os.path.expanduser(project_path)))).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def validate_records(records):
    if not isinstance(records, list):
        raise HistoryError(tr("Invalid history records"))
    seen = set()
    for record in records:
        for field in ("id", "created_at", "description", "name", "state_hash"):
            if not isinstance(record[field], str):
                raise HistoryError(tr("Invalid record field: ") + field)
        if type(record["pinned"]) is not bool or record["id"] in seen:
            raise HistoryError(tr("Invalid pin or duplicate record ID"))
        seen.add(record["id"])
        components = component_hashes(record["state"])
        if components != record["components"] or digest(components) != record["state_hash"]:
            raise HistoryError(tr("Snapshot hash mismatch"))
    return records


class HistoryStore:
    """All mutations read the current state AFTER acquiring SQLite's write lock.

    A 150 ms busy timeout bounds lock contention, not filesystem/provider I/O.
    Deleted records raise KeyError on update; no operation recreates them.
    Each row is independent, so preview/pin updates do not rewrite other images.
    """
    def __init__(self, root: Path, project_path: str = "", limit: int = 20):
        self.root = Path(root)
        self._validate_limit(limit)
        self.limit, self.saved = limit, bool(project_path)
        self.key = project_key(project_path) if self.saved else "temporary-" + uuid4().hex
        self._connection, self._revision = None, None
        self._undo_head = None
        self._records = self._read() if self.saved else []

    @property
    def records(self):
        return deepcopy(self._records)

    def get_record(self, record_id):
        return deepcopy(next((r for r in self._records if r["id"] == record_id), None))

    def undo_target(self):
        # Only the newest explicitly marked user Apply can be undone. Never fall
        # back to an older event when its target is missing or already consumed.
        event = next((r for r in self._records if r["id"] == self._undo_head), None)
        return event["id"] if event and event.get("outcome") != "undone" else None

    @property
    def has_records(self):
        return bool(self._records)

    @property
    def path(self):
        return self.root / self.key / "history.sqlite3"

    @property
    def legacy_path(self):
        return self.path.with_name("history.json")

    @staticmethod
    def _validate_limit(limit):
        if type(limit) is not int or limit < 1:
            raise ValueError(tr("Buffer size must be a positive integer"))

    def _legacy(self):
        if not self.legacy_path.exists():
            return []
        payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        if payload["version"] != 1:
            raise HistoryError(tr("Unsupported legacy history format"))
        return validate_records(payload["records"])

    def _load(self, db):
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version != 2:
            raise HistoryError(tr("Unsupported database format"))
        self.limit = int(db.execute("SELECT value FROM settings WHERE key='limit'").fetchone()[0])
        self._validate_limit(self.limit)
        head = db.execute("SELECT value FROM settings WHERE key='undo_head'").fetchone()
        self._undo_head = head[0] if head else None
        row = db.execute("SELECT value FROM settings WHERE key='revision'").fetchone()
        revision = int(row[0]) if row else 0
        if self._revision == revision and hasattr(self, "_records"):
            return self._records
        records = validate_records([json.loads(row[0]) for row in db.execute(
            "SELECT payload FROM records ORDER BY position")])
        self._revision = revision
        return records

    def _read(self):
        try:
            if not self.path.exists():
                return self._legacy()
            # A failed first transaction can leave an empty database, but no schema.
            with closing(sqlite3.connect(self.path, timeout=0.15)) as db:
                db.execute("BEGIN")
                if db.execute("PRAGMA user_version").fetchone()[0] == 0:
                    return self._legacy()
                return self._load(db)
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise HistoryError(f"Cannot read history at {self.path}: {exc}") from exc

    def refresh(self, *, return_records=True):
        if self.saved:
            self._records = self._read()
        return self.records if return_records else None

    @contextmanager
    def _transaction(self):
        original, original_limit, original_revision = self._records, self.limit, self._revision
        original_head = self._undo_head
        db = None
        try:
            if self.saved:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                db = sqlite3.connect(self.path, timeout=0.15, isolation_level=None)
                db.execute("BEGIN IMMEDIATE")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    legacy = self._legacy()
                    db.execute("CREATE TABLE records(id TEXT PRIMARY KEY, position INTEGER NOT NULL, payload TEXT NOT NULL)")
                    db.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    db.execute("INSERT INTO settings VALUES('limit', ?)", (str(self.limit),))
                    db.executemany("INSERT INTO records VALUES(?,?,?)", [
                        (r["id"], i, _json(r)) for i, r in enumerate(legacy)])
                    db.execute("PRAGMA user_version=2")
                db.execute("INSERT OR IGNORE INTO settings VALUES('revision', '0')")
                self._records = self._load(db)
                self._connection = db
            yield
            if db is not None:
                db.commit()
        except Exception as exc:
            if db is not None:
                db.rollback()
            self._records, self.limit, self._revision = original, original_limit, original_revision
            self._undo_head = original_head
            if isinstance(exc, sqlite3.Error):
                raise HistoryError(tr("History unavailable (busy or storage error); retry: ") + str(exc)) from exc
            raise
        finally:
            self._connection = None
            if db is not None:
                db.close()

    def _trim(self, records, limit):
        ordinary = [r["id"] for r in records if not r["pinned"] and r.get("kind") != "recovery"]
        evict = set(ordinary[:-limit])
        return [r for r in records if r["id"] not in evict]

    def _commit(self, records):
        """Called only inside a transaction. Touch only changed rows."""
        old_ids = {r["id"] for r in self._records}
        for record in records:
            if record["id"] not in old_ids and record.get("operation") == "apply" and record.get("kind") == "recovery":
                self._undo_head = record["id"]
        db = self._connection
        if db is not None:
            if self._undo_head:
                db.execute("INSERT OR REPLACE INTO settings VALUES('undo_head', ?)", (self._undo_head,))
            old = {r["id"]: r for r in self._records}
            new = {r["id"]: r for r in records}
            db.executemany("DELETE FROM records WHERE id=?", [(key,) for key in old.keys() - new.keys()])
            position = db.execute("SELECT COALESCE(MAX(position), -1) FROM records").fetchone()[0]
            for record in records:
                key = record["id"]
                if key not in old:
                    position += 1
                    db.execute("INSERT INTO records VALUES(?,?,?)", (key, position, _json(record)))
                elif record != old[key]:
                    db.execute("UPDATE records SET payload=? WHERE id=?", (_json(record), key))
            db.execute("UPDATE settings SET value=? WHERE key='limit'", (str(self.limit),))
            self._revision = (self._revision or 0) + 1
            db.execute("UPDATE settings SET value=? WHERE key='revision'", (str(self._revision),))
        self._records = records

    def append(self, state, *, pinned=False, name="", description=None, force=False):
        return self._append(state, pinned=pinned, name=name, description=description, force=force)

    def append_restore(self, state, *, before=False, description=None, event_id=None, target="", operation="legacy", undo_of=None):
        return self._append(state, force=True, kind="recovery" if before else "application",
                            event_id=event_id or uuid4().hex, target=target, operation=operation, undo_of=undo_of,
                            name=("Recovery: " + target) if before else "", description=description,
                            outcome="pending" if before else "complete")

    def _append(self, state, *, pinned=False, name="", description=None, force=False, **metadata):
        state = deepcopy(state)
        components = component_hashes(state)
        hashed = digest(components)
        with self._transaction():
            previous = self._records[-1] if self._records else None
            if not force and previous and previous["state_hash"] == hashed:
                return None
            record = dict(id=uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
                          state=state, components=components, state_hash=hashed,
                          description=description if description is not None else describe(
                              previous["state"] if previous else None, state,
                              before_hashes=previous["components"] if previous else None, after_hashes=components),
                          pinned=bool(pinned), name=name, **metadata)
            self._commit(self._trim(self._records + [record], self.limit))
        return deepcopy(record)

    def _update(self, record_id, **changes):
        with self._transaction():
            records = list(self._records)
            record = next((r for r in records if r["id"] == record_id), None)
            if record is None:
                raise KeyError(record_id)
            if all(record.get(key) == value for key, value in changes.items()):
                return
            index = records.index(record)
            record = dict(record)
            records[index] = record
            record.update(deepcopy(changes))
            self._commit(self._trim(records, self.limit))

    def set_preview(self, record_id, preview):
        with self._transaction():
            records = list(self._records)
            record = next((r for r in records if r["id"] == record_id), None)
            if record is None:
                raise KeyError(record_id)
            if record.get("preview") == preview and "preview" in record:
                return
            # Published images never get overwritten, including by late callbacks.
            if "preview" in record and record["preview"] != preview:
                raise HistoryError(tr("Saved previews are immutable"))
            index = records.index(record)
            record = dict(record)
            records[index] = record
            record["preview"] = deepcopy(preview)
            self._commit(records)

    def finish_recovery(self, record_id, outcome):
        if outcome not in {"complete", "partial", "undone"}:
            raise ValueError(tr("Unknown application outcome"))
        self._update(record_id, outcome=outcome)

    def set_pinned(self, record_id, pinned):
        self._update(record_id, pinned=bool(pinned))

    def rename(self, record_id, name):
        self._update(record_id, name=name.strip())

    def delete(self, record_id):
        with self._transaction():
            if not any(r["id"] == record_id for r in self._records):
                raise KeyError(record_id)
            self._commit([r for r in self._records if r["id"] != record_id])

    def set_limit(self, limit):
        self._validate_limit(limit)
        with self._transaction():
            self.limit = limit
            self._commit(self._trim(self._records, limit))

    def cleanup_recovery(self, keep=10):
        """Explicit action only. Keep unresolved, pinned and latest recovery events."""
        self._validate_limit(keep)
        with self._transaction():
            recoveries = [r for r in self._records if r.get("kind") == "recovery"]
            protected = {r["id"] for r in recoveries[-keep:]}
            protected.add(self._undo_head)
            records = [r for r in self._records if r.get("kind") != "recovery"
                       or r["id"] in protected or r["pinned"]
                       or r.get("outcome") not in {"complete", "undone"}]
            removed = len(self._records) - len(records)
            self._commit(records)
        return removed

    def migrate(self, project_path):
        if self.saved:
            raise ValueError(tr("Only unsaved projects can migrate history"))
        destination = self.copy_to(project_path)
        self.key, self.saved, self.limit = destination.key, True, destination.limit
        self._records, self._revision = destination._records, destination._revision
        self._undo_head = destination._undo_head

    def copy_to(self, project_path):
        if not project_path:
            raise ValueError(tr("A destination path is required"))
        records = self.refresh()
        destination = HistoryStore(self.root, project_path, self.limit)
        with destination._transaction():
            # Never merge independently existing project histories on Save As.
            if destination._records:
                raise HistoryError(tr("The destination already has history. Open that history or choose another path."))
            destination._commit(records)
            destination._undo_head = self._undo_head
            destination._connection.execute("INSERT OR REPLACE INTO settings VALUES('undo_head', ?)", (self._undo_head or "",))
        return destination

    def export(self, path):
        records = self.refresh()
        payload = _json(dict(version=2, project_key=self.key, undo_head=self._undo_head, records=records))
        # The dialog requests overwrite approval; create atomically via a sibling.
        import tempfile
        output = Path(path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                             delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
