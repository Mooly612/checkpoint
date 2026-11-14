"""Release boundaries and Qt pairing must fail closed before project mutation."""
import pytest

from checkpoint.core.compat import supported_runtime


@pytest.mark.parametrize("number,version,qt", [
    (34400, "3.44.0-Solothurn", "5.15.2"),
    (34408, "3.44.8-Solothurn", "5.15.18"),
    (34415, "3.44.15-Solothurn", "5.15.18"),
    (40003, "4.0.3-Norrköping", "6.8.3"),
    (40203, "4.2.3-Belém do Pará", "6.9.2"),
])
def test_released_targets(number, version, qt):
    assert supported_runtime(number, version, qt)


@pytest.mark.parametrize("number,version,qt", [
    (34000, "3.40.0", "5.15.18"),
    (34499, "3.44.99", "5.15.18"),
    (34500, "3.45.0-Master", "5.15.18"),
    (34408, "3.44.8", "6.8.3"),
    (40003, "4.0.3", "5.15.18"),
    (40200, "4.2.0-RC1", "6.8.3"),
    (40200, "4.2.0-beta", "6.8.3"),
    (40299, "4.2.99", "6.8.3"),
    (40300, "4.3.0-Master", "6.8.3"),
    (40400, "4.4.0", "6.8.3"),
    (50000, "5.0.0", "7.0.0"),
])
def test_unsupported_and_prerelease_targets(number, version, qt):
    assert not supported_runtime(number, version, qt)
