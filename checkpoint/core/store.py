"""Atomic JSON history, bounded unpinned entries, and in-memory projects."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from .differ import component_hashes, describe, digest


class HistoryError(ValueError):
    """Stored history is unreadable or uses an unsupported format."""


def project_key(project_path: str) -> str:
    """Hash the absolute file path, without following symlinks."""
    if not project_path:
        raise ValueError("A saved project needs a path")
    path = os.path.abspath(os.path.expanduser(project_path))
    return hashlib.sha256(os.fsencode(path)).hexdigest()


class HistoryStore:
    """The caller supplies QgsApplication's settings directory / checkpoint."""

    def __init__(self, root: Path, project_path: str = "", limit: int = 20):
        self.root = Path(root)
        self._validate_limit(limit)
        self.limit = limit
        self.saved = bool(project_path)
        self.key = project_key(project_path) if self.saved else "temporary-" + uuid4().hex
        self._records = self._read() if self.saved else []

    @property
    def records(self) -> list[dict]:
        """Return detached data so callers cannot accidentally mutate history."""
        return deepcopy(self._records)

    @property
    def path(self) -> Path:
        return self.root / self.key / "history.json"

    @staticmethod
    def _validate_limit(limit: int):
        if type(limit) is not int or limit < 1:
            raise ValueError("Buffer size must be a positive integer")

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload["version"] != 1 or not isinstance(payload["records"], list):
                raise ValueError("Unsupported history format")
            seen = set()
            for record in payload["records"]:
                for field in ("id", "created_at", "description", "name", "state_hash"):
                    if not isinstance(record[field], str):
                        raise ValueError("Invalid record field: " + field)
                if type(record["pinned"]) is not bool or record["id"] in seen:
                    raise ValueError("Invalid pin or duplicate record id")
                seen.add(record["id"])
                components = component_hashes(record["state"])
                if components != record["components"] or digest(components) != record["state_hash"]:
                    raise ValueError("Snapshot hash mismatch")
            return payload["records"]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise HistoryError(f"Cannot read history at {self.path}: {exc}") from exc

    def _trim(self, records: list[dict], limit: int) -> list[dict]:
        unpinned = [record["id"] for record in records if not record["pinned"]]
        evict = set(unpinned[:-limit])
        return [record for record in records if record["id"] not in evict]

    def _commit(self, records: list[dict]):
        """Replace atomically; preserve memory and the old file if writing fails."""
        if self.saved:
            payload = json.dumps({"version": 1, "records": records}, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                                 dir=self.path.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        self._records = records

    def append(self, state: dict, *, pinned: bool = False, name: str = "",
               description: str | None = None) -> dict | None:
        """Skip an unchanged latest state, including view-only changes."""
        return self._append(state, pinned=pinned, name=name, description=description)

    def append_restore(self, state: dict, *, before: bool = False,
                       description: str | None = None) -> dict:
        """Always record restore events, including their exact map view."""
        return self._append(state, pinned=before,
                            name="before restore" if before else "",
                            description=description, force=True)

    def _append(self, state: dict, *, pinned=False, name="", description=None,
                force=False) -> dict | None:
        state = deepcopy(state)
        components = component_hashes(state)
        hashed = digest(components)
        previous = self._records[-1] if self._records else None
        if not force and previous and previous["state_hash"] == hashed:
            return None
        record = {
            "id": uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "state": state, "components": components, "state_hash": hashed,
            "description": description if description is not None else describe(
                previous["state"] if previous else None, state),
            "pinned": bool(pinned), "name": name,
        }
        self._commit(self._trim(self._records + [record], self.limit))
        return deepcopy(record)

    def _update(self, record_id: str, **changes):
        records = self.records
        record = next((record for record in records if record["id"] == record_id), None)
        if record is None:
            raise KeyError(record_id)
        record.update(changes)
        self._commit(self._trim(records, self.limit))

    def set_pinned(self, record_id: str, pinned: bool):
        self._update(record_id, pinned=bool(pinned))

    def rename(self, record_id: str, name: str):
        self._update(record_id, name=name.strip())

    def delete(self, record_id: str):
        if not any(record["id"] == record_id for record in self._records):
            raise KeyError(record_id)
        self._commit([record for record in self._records if record["id"] != record_id])

    def set_limit(self, limit: int):
        self._validate_limit(limit)
        self._commit(self._trim(self._records, limit))
        self.limit = limit

    def migrate(self, project_path: str):
        """Persist an unsaved project on first save, retaining existing history."""
        if self.saved:
            raise ValueError("Only unsaved projects can migrate history")
        destination = HistoryStore(self.root, project_path, self.limit)
        if not destination.saved:
            raise ValueError("Migration requires a saved project path")
        # Preserve pinned and named records if two sessions contain the same state.
        # Append-time deduplication remains scoped to the latest record in a session.
        by_id = {record["id"]: record for record in destination._records + self._records}
        records = sorted(by_id.values(), key=lambda record: record["created_at"])
        destination._commit(self._trim(records, self.limit))
        self.key, self.saved = destination.key, True
        self._records = destination._records
