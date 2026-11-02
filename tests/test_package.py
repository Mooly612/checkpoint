import configparser
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
                "checkpoint/icon.png", "checkpoint/LICENSE", "checkpoint/README.md",
                "checkpoint/ui/settings.py", "checkpoint/core/thumbnail.py",
                "checkpoint/demo/checkpoint-demo.qgz", "checkpoint/demo/roads.geojson",
                "checkpoint/demo/buildings.geojson"} <= names
        metadata = configparser.ConfigParser()
        metadata.read_string(archive.read("checkpoint/metadata.txt").decode())
        assert metadata["general"]["qgisMinimumVersion"] == "3.44"
        assert metadata["general"]["qgisMaximumVersion"] == "3.99"
        assert not metadata["general"].getboolean("supportsQt6")
        general = metadata["general"]
        assert general["license"] == "GPL-2.0-or-later"
        assert general["version"] in general["changelog"]
        assert "checkpoint/" + general["icon"] in names
        assert first.stat().st_size < 25 * 1024 * 1024
        for field in ("repository", "homepage", "tracker"):
            assert general[field].startswith("https://github.com/Mooly612/checkpoint")
        assert not any(name.endswith((".so", ".dll", ".dylib", ".exe")) for name in names)
        assert all(name.startswith("checkpoint/") for name in names)
        assert not any(part in {"tests", "scripts", "__pycache__", ".git"}
                       for name in names for part in Path(name).parts)
        assert not any(name.endswith((".pyc", ".json")) for name in names)
