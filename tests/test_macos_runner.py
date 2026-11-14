"""Selecting a bundle must use its interpreter and its dependency paths."""
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import patch


def test_selected_bundle_ignores_config_executable_and_foreign_environment(tmp_path, monkeypatch):
    main = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/run_qgis_macos.py'))['main']
    app = tmp_path / 'QGIS 测试 with spaces.app'
    contents = app / 'Contents'
    macos = contents / 'MacOS'
    macos.mkdir(parents=True)
    for name in ('python3.9', 'python3.12', 'python3.12-config'):
        binary = macos / name
        binary.write_text('test fixture')
        binary.chmod(0o755)
    sites = contents / 'Resources/python3.12/site-packages'
    sites.mkdir(parents=True)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                'QGIS_PREFIX_PATH', 'QGIS_PLUGINPATH', 'PROJ_DATA', 'PROJ_LIB'):
        monkeypatch.setenv(key, '/unrelated-installation')
    with patch('subprocess.run', return_value=SimpleNamespace(returncode=7)) as run:
        assert main(['--app', str(app), '--only', 'qgis_smoke']) == 7
    argv = run.call_args.args[0]
    env = run.call_args.kwargs['env']
    assert argv[0] == str(macos / 'python3.12')
    assert argv[-2:] == ['--only', 'qgis_smoke']
    assert env['PYTHONPATH'] == str(sites)
    assert env['QT_PLUGIN_PATH'] == str(contents / 'PlugIns')
    assert env['PROJ_DATA'] == str(contents / 'Resources/qgis/proj')
    assert not any(key in env for key in ('PYTHONHOME', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                                         'QGIS_PREFIX_PATH', 'QGIS_PLUGINPATH', 'PROJ_LIB'))
