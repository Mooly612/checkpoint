#!/usr/bin/env python3
"""Launch checks using a selected QGIS.app's own Python, never system Python."""
import argparse
import os
from pathlib import Path
import re
import subprocess


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    args, checks = parser.parse_known_args(argv)
    contents = args.app.resolve() / "Contents"
    candidates = [contents / "MacOS/bin/python3", contents / "MacOS/python3"]
    versioned = [p for p in (contents / "MacOS").glob("python3.*")
                 if re.fullmatch(r"python3\.\d+", p.name)]
    candidates += sorted(versioned, key=lambda p: int(p.name.split(".")[-1]), reverse=True)
    candidates += sorted((contents / "Frameworks/Python.framework/Versions").glob("*/bin/python3"), reverse=True)
    candidates += [contents / "Resources/python/bin/python3"]
    interpreter = next((p for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)
    if interpreter is None:
        raise SystemExit(f"No bundled Python found in {args.app}; use its configured QGIS Python environment.")
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    # A shell configured for another Qt/QGIS/PROJ installation must not mix its
    # plugins or coordinate database into the explicitly selected application.
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QGIS_PREFIX_PATH",
                "QGIS_PLUGINPATH", "PROJ_DATA", "PROJ_LIB"):
        env.pop(key, None)
    env["QT_PLUGIN_PATH"] = str(contents / "PlugIns")
    env["PROJ_DATA"] = str(contents / "Resources/qgis/proj")
    # Older official bundles keep the Python stdlib directly in Frameworks.
    if list((contents / "Frameworks/lib").glob("python3.*")):
        env["PYTHONHOME"] = str(contents / "Frameworks")
    sites = sorted((contents / "Resources").glob("python*/site-packages"))
    if sites:
        env["PYTHONPATH"] = os.pathsep.join(str(p) for p in sites)
    env["QT_QPA_PLATFORM"] = "offscreen"
    runner = Path(__file__).with_name("run_qgis_checks.py")
    print("QGIS Python:", interpreter, flush=True)
    return subprocess.run([str(interpreter), str(runner), *checks], env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
