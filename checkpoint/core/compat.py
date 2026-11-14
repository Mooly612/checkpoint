"""Explicit release targets, without importing QGIS or either Qt binding."""
import re


# Extend only after running the native suite on a released QGIS version.
RELEASE_QT = {(3, 44): 5, (4, 0): 6, (4, 2): 6}
REQUIREMENT = (
    "Checkpoint requires a stable QGIS 3.44 / Qt5 or QGIS 4.0, 4.2 / Qt6 release. "
    "Development and unvalidated release lines are not supported. No styling was applied."
)


def supported_runtime(version_int, version, qt_version):
    if type(version_int) is not int or not isinstance(version, str) or not isinstance(qt_version, str):
        return False
    major, remainder = divmod(version_int, 10000)
    minor, patch = divmod(remainder, 100)
    advertised = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if advertised is None or tuple(map(int, advertised.groups())) != (major, minor, patch):
        return False
    # QGIS uses odd minor versions and patch 99 for development builds.
    # A suffix can directly follow the patch (4.2.0rc1), so a word boundary
    # would miss it. Do not mistake letters inside a release codename for tags.
    if patch == 99 or re.search(
        r"(?<![a-z])(?:master|nightly|development|dev|alpha|beta|preview|pre|rc)\d*(?![a-z])",
        version, re.I,
    ):
        return False
    expected_qt = RELEASE_QT.get((major, minor))
    return expected_qt is not None and qt_version.split(".", 1)[0] == str(expected_qt)
