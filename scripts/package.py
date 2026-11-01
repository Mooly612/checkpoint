#!/usr/bin/env python3
"""Build a reproducible, self-contained QGIS plugin ZIP without dev artifacts."""

import argparse
import ast
import configparser
import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def build(root=ROOT, output=None):
    root = Path(root)
    output = Path(output) if output else root / "dist" / "checkpoint.zip"
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(root / "checkpoint" / "metadata.txt", encoding="utf-8")
    for key in ("name", "version", "qgisMinimumVersion", "author", "email", "repository", "icon"):
        if not metadata.get("general", key, fallback="").strip():
            raise ValueError("Missing metadata: " + key)
    files = {}
    for path in sorted((root / "checkpoint").rglob("*")):
        relative = path.relative_to(root / "checkpoint")
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("Plugin source must not contain symlinks: " + str(relative))
        if path.is_file() and (path.suffix in {".py", ".svg"} or relative.as_posix() == "metadata.txt"):
            data = path.read_bytes()
            if path.suffix == ".py":
                ast.parse(data, filename=str(path))
            files["checkpoint/" + relative.as_posix()] = data
    for name in ("LICENSE", "README.md", "CHANGELOG.md"):
        files["checkpoint/" + name] = (root / name).read_bytes()
    for path in sorted((root / "docs").glob("*.md")):
        if path.is_symlink():
            raise ValueError("Documentation must not be a symlink")
        files["checkpoint/docs/" + path.name] = path.read_bytes()
    for path in sorted((root / "docs" / "images").glob("*")):
        if path.suffix in {".png", ".svg"} and path.is_file():
            files["checkpoint/docs/images/" + path.name] = path.read_bytes()
    for required in ("__init__.py", "plugin.py", metadata["general"]["icon"]):
        if "checkpoint/" + required not in files:
            raise ValueError("Missing plugin file: " + required)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix=".zip")
    os.close(fd)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity verification failed")
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = build(output=args.output)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{checksum}  {output.name}\n", encoding="ascii")
    print(f"Built {output} ({output.stat().st_size:,} bytes)\nSHA-256: {checksum}")
