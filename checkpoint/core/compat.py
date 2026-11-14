"""Explicit release targets, without importing QGIS or either Qt binding."""
import re


# Extend only after running the native suite on a released QGIS version.
RELEASE_QT = {(3, 44): 5, (4, 0): 6, (4, 2): 6}
REQUIREMENT = (
    "Checkpoint requires a stable QGIS 3.44 / Qt5 or QGIS 4.0, 4.2 / Qt6 release. "
    "Development and unvalidated release lines are not supported. No styling was applied."
)


def supported_runtime(version_int, version, qt_version):
    major, remainder = divmod(version_int, 10000)
    minor, patch = divmod(remainder, 100)
    # QGIS uses odd minor versions and patch 99 for development builds.
    if patch == 99 or re.search(r"master|dev|alpha|beta|preview|\brc\d*", version, re.I):
        return False
    expected_qt = RELEASE_QT.get((major, minor))
    return expected_qt is not None and qt_version.split(".", 1)[0] == str(expected_qt)
