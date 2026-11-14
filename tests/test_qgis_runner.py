"""The native runner must not report success when nothing was tested."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch
from zipfile import ZipFile

import pytest

RUNNER = Path(__file__).resolve().parents[1] / 'scripts/run_qgis_checks.py'


def test_unknown_scenario_fails_before_importing_qgis():
    result = subprocess.run([sys.executable, str(RUNNER), '--only', 'typo_smoke'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert 'invalid choice' in result.stderr


def test_optimized_python_cannot_silently_disable_native_assertions():
    result = subprocess.run([sys.executable, '-O', str(RUNNER), '--only', 'qgis_smoke'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert 'require Python assertions' in result.stderr


def test_missing_package_replaces_stale_success_report(tmp_path):
    report = tmp_path / 'runtime.json'
    report.write_text('{"passed": true}')
    result = subprocess.run([sys.executable, str(RUNNER), '--package', str(tmp_path / 'missing.zip'),
                             '--report', str(report)], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    payload = json.loads(report.read_text())
    assert not payload['passed'] and payload['scenarios'] == []
    assert 'FileNotFoundError' in payload['error']
    assert payload['stage'] == 'package extraction'


def test_teardown_error_cannot_publish_a_pass(tmp_path):
    namespace = runpy.run_path(str(RUNNER))
    main = namespace['main']
    report = tmp_path / 'runtime.json'

    def fail_teardown(args, payload):
        payload['scenarios'] = payload['requested_scenarios'][:]
        raise RuntimeError('teardown failed')

    with patch.dict(main.__globals__, run_checks=fail_teardown):
        with pytest.raises(RuntimeError, match='teardown failed'):
            main(['--only', 'qgis_smoke', '--report', str(report)])
    payload = json.loads(report.read_text())
    assert payload['scenarios'] == ['qgis_smoke.py'] and not payload['passed']


@pytest.mark.parametrize('name', ['other/file.py', 'checkpoint/../escape.py',
                                  'checkpoint/..\\escape.py', 'checkpoint/C:escape.py'])
def test_invalid_package_member_is_rejected_on_every_os(tmp_path, name):
    extract = runpy.run_path(str(RUNNER))['extract_package']
    package = tmp_path / 'invalid.zip'
    with ZipFile(package, 'w') as archive:
        archive.writestr('checkpoint/__init__.py', '')
        archive.writestr('checkpoint/metadata.txt', '[general]')
        archive.writestr(name, 'invalid')
    with pytest.raises(ValueError, match='Unexpected package member'):
        extract(package, tmp_path / 'installed')
    assert not (tmp_path / 'installed').exists()
