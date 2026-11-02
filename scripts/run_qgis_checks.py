#!/usr/bin/env python3
"""Run real-QGIS checks in a disposable profile, optionally against a built ZIP."""
import argparse
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--package", type=Path)
parser.add_argument("--demo", action="store_true", help="Generate synthetic project and real widget screenshots")
parser.add_argument("--only", nargs="+", help="Smoke filenames without .py")
args = parser.parse_args()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
mac = Path("/Applications/QGIS.app/Contents")
if mac.exists():
    os.environ.setdefault("QT_PLUGIN_PATH", str(mac / "PlugIns"))
    os.environ.setdefault("PROJ_DATA", str(mac / "Resources/qgis/proj"))
    sys.path.insert(0, str(mac / "Resources/python3.11/site-packages"))
with TemporaryDirectory(prefix="checkpoint-checks-") as directory:
    temporary = Path(directory)
    profile = temporary / "profile"
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(profile)
    source = ROOT
    if args.package:
        source = temporary / "installed"
        with ZipFile(args.package) as archive:
            for name in archive.namelist():
                if not name.startswith("checkpoint/") or ".." in Path(name).parts:
                    raise ValueError("Unexpected package member: " + name)
            archive.extractall(source)
    sys.path.insert(0, str(source))
    from qgis.core import Qgis, QgsApplication
    from qgis.PyQt.QtCore import QT_VERSION_STR
    app = QgsApplication([], True, str(profile))
    if mac.exists():
        app.setPrefixPath(str(mac / "MacOS"), True)
        app.setPluginPath(str(mac / "PlugIns/qgis"))
        app.setPkgDataPath(str(mac / "Resources/qgis"))
    app.initQgis()
    try:
        assert Path(app.qgisSettingsDirPath()).is_relative_to(profile)
        import checkpoint
        assert Path(checkpoint.__file__).resolve().is_relative_to(source.resolve())
        from qgis.PyQt.QtSvg import QSvgRenderer
        assert QSvgRenderer(str(source / "checkpoint/icon.svg")).isValid()
        print("Runtime:", Qgis.QGIS_VERSION, "Qt", QT_VERSION_STR, "Python", sys.version.split()[0], flush=True)
        print("Plugin:", checkpoint.__file__, flush=True)
        for name in ("qgis_settings_smoke.py", "qgis_smoke.py", "qgis_watcher_smoke.py",
                     "qgis_plugin_smoke.py", "qgis_restore_smoke.py", "qgis_thumbnail_smoke.py", "qgis_regression_smoke.py", "qgis_demo_smoke.py", "qgis_reopen_smoke.py", "qgis_followup_smoke.py", "qgis_shutdown_smoke.py"):
            if args.only and Path(name).stem not in args.only:
                continue
            print("Running", name, flush=True)
            runpy.run_path(str(ROOT / "tests" / name), run_name="__main__")
        if args.demo:
            runpy.run_path(str(ROOT / "scripts/create_demo.py"), run_name="__main__")
    finally:
        from checkpoint.core.thumbnail import _RUNNING
        from qgis.PyQt.QtTest import QTest
        for _ in range(150):
            if not _RUNNING:
                break
            QTest.qWait(20)
        assert not _RUNNING, "Preview resources still in use at QGIS shutdown"
        # runpy scripts can leave Python/Qt cycles and deferred widget deletes.
        # Finalize them while QGIS registries/providers are still alive.
        import gc
        from qgis.PyQt.QtCore import QCoreApplication, QEvent
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()
        app.exitQgis()
