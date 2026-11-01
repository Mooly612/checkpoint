from pathlib import Path
import runpy
from zipfile import ZipFile

build = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/package.py"))["build"]


def test_release_archive_is_complete_and_reproducible(tmp_path):
    first = build(output=tmp_path / "first.zip")
    second = build(output=tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        names = set(archive.namelist())
        assert archive.testzip() is None
        assert {"checkpoint/__init__.py", "checkpoint/plugin.py", "checkpoint/metadata.txt",
                "checkpoint/icon.svg", "checkpoint/LICENSE", "checkpoint/README.md",
                "checkpoint/ui/settings.py", "checkpoint/core/thumbnail.py"} <= names
        assert all(name.startswith("checkpoint/") for name in names)
        assert not any(part in {"tests", "scripts", "__pycache__", ".git"}
                       for name in names for part in Path(name).parts)
        assert not any(name.endswith((".pyc", ".qgz", ".json")) for name in names)
