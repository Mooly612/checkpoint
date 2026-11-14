#!/usr/bin/env python3
"""Run real-QGIS checks in a disposable profile, optionally against a built ZIP."""
import argparse
import json
import os
import platform
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
parser.add_argument("--expected-qgis", help="Require a specific major.minor release line")
parser.add_argument("--report", type=Path, help="Write native runtime and scenario results as JSON")
args = parser.parse_args()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Only use the bundle belonging to this interpreter. Never mix another installed
# QGIS.app into a Linux, conda, or different macOS QGIS environment.
mac = next((p for p in Path(sys.executable).absolute().parents
            if p.name == "Contents" and p.parent.suffix == ".app"), None)
if mac is not None:
    os.environ.setdefault("QT_PLUGIN_PATH", str(mac / "PlugIns"))
    os.environ.setdefault("PROJ_DATA", str(mac / "Resources/qgis/proj"))
    for site in sorted((mac / "Resources").glob("python*/site-packages")):
        sys.path.append(str(site))
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
    if mac is not None:
        app.setPrefixPath(str(mac / "MacOS"), True)
        app.setPluginPath(str(mac / "PlugIns/qgis"))
        app.setPkgDataPath(str(mac / "Resources/qgis"))
    app.initQgis()
    report = {"platform": platform.platform(), "qgis": Qgis.QGIS_VERSION,
              "qt": QT_VERSION_STR, "python": platform.python_version(),
              "package": str(args.package) if args.package else None,
              "scenarios": [], "passed": False}
    try:
        assert Path(app.qgisSettingsDirPath()).is_relative_to(profile)
        import checkpoint
        assert Path(checkpoint.__file__).resolve().is_relative_to(source.resolve())
        from checkpoint.core.compat import supported_runtime
        assert supported_runtime(Qgis.QGIS_VERSION_INT, Qgis.QGIS_VERSION, QT_VERSION_STR), report
        if args.expected_qgis:
            actual = f"{Qgis.QGIS_VERSION_INT // 10000}.{Qgis.QGIS_VERSION_INT // 100 % 100}"
            assert actual == args.expected_qgis, ("Unexpected QGIS release", actual, args.expected_qgis)
        from qgis.PyQt.QtGui import QIcon
        icon = QIcon(str(source / "checkpoint/icon.png"))
        assert not icon.isNull() and not icon.pixmap(24, 24).isNull()
        print("Runtime:", Qgis.QGIS_VERSION, "Qt", QT_VERSION_STR, "Python", sys.version.split()[0], flush=True)
        print("Platform:", report["platform"], flush=True)
        print("Plugin:", checkpoint.__file__, flush=True)
        for name in ("qgis_settings_smoke.py", "qgis_smoke.py", "qgis_watcher_smoke.py",
                     "qgis_plugin_smoke.py", "qgis_restore_smoke.py", "qgis_thumbnail_smoke.py", "qgis_regression_smoke.py", "qgis_demo_smoke.py", "qgis_reopen_smoke.py", "qgis_followup_smoke.py", "qgis_shutdown_smoke.py"):
            if args.only and Path(name).stem not in args.only:
                continue
            print("Running", name, flush=True)
            runpy.run_path(str(ROOT / "tests" / name), run_name="__main__")
            report["scenarios"].append(name)
        if args.demo:
            runpy.run_path(str(ROOT / "scripts/create_demo.py"), run_name="__main__")
        report["passed"] = True
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
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
        app.exitQgis()
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
