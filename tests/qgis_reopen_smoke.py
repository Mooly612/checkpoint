"""Repeated enable in fresh QGIS processes must not duplicate unchanged styling."""
import os
import gc
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory


def child(source, demo, history):
    sys.path.insert(0, source)
    from qgis.core import QgsApplication, QgsProject, QgsSettings
    from qgis.PyQt.QtTest import QTest
    from checkpoint import classFactory
    harness = runpy.run_path(str(Path(__file__).with_name('qgis_plugin_smoke.py')))['InterfaceHarness']
    with TemporaryDirectory(prefix='checkpoint-reopen-profile-') as profile:
        os.environ['QGIS_CUSTOM_CONFIG_PATH'] = profile
        app = QgsApplication([], True, profile)
        mac = Path('/Applications/QGIS.app/Contents')
        if mac.exists():
            app.setPrefixPath(str(mac / 'MacOS'), True)
            app.setPluginPath(str(mac / 'PlugIns/qgis'))
            app.setPkgDataPath(str(mac / 'Resources/qgis'))
        app.initQgis()
        project, iface = QgsProject(), harness()
        plugin = classFactory(iface)
        plugin.project, plugin.root = project, Path(history)
        try:
            assert project.read(str(Path(demo) / 'checkpoint-demo.qgz'))
            iface.canvas.setDestinationCrs(project.crs())
            QgsSettings().setValue('checkpoint/previews', False)
            plugin.initGui()
            if len(plugin.store.records) != 1:
                from checkpoint.core.differ import describe, normalized_style
                import difflib, json
                records = plugin.store.records
                if len(records) > 1:
                    old, new = records[-2]['state'], records[-1]['state']
                    print('Unexpected diff:', describe(old, new), flush=True)
                    print('Tree:', json.dumps(old['tree'], sort_keys=True), json.dumps(new['tree'], sort_keys=True), flush=True)
                    for key in old['layers'].keys() & new['layers'].keys():
                        difference = list(difflib.unified_diff(normalized_style(old['layers'][key]['style']).splitlines(),
                            normalized_style(new['layers'][key]['style']).splitlines()))
                        if difference:
                            print(old['layers'][key]['name'], '\n'.join(difference[:50]), flush=True)
                raise AssertionError('Starting checkpoint count: ' + str(len(records)))
            print('One starting checkpoint', flush=True)
        finally:
            plugin.unload()
            QTest.qWait(20)
            iface.canvas.stopRendering(); iface.canvas.setLayers([])
            project.clear(); iface.window.close(); iface.window.deleteLater()
            QTest.qWait(50)
            del plugin, iface, project
            gc.collect()
            app.exitQgis()


def run():
    import checkpoint
    package = Path(checkpoint.__file__).resolve().parent
    demo = package / 'demo' if (package / 'demo').exists() else package.parent / 'demo'
    with TemporaryDirectory(prefix='checkpoint-reopen-history-') as history:
        for seed in ('1', '2'):
            environment = dict(os.environ, QT_HASH_SEED=seed, PYTHONFAULTHANDLER='1')
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child',
                                     str(package.parent), str(demo), history],
                                    env=environment, capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, str(result.returncode) + ": " + result.stdout + result.stderr
            assert 'One starting checkpoint' in result.stdout
    print('Checkpoint independent-process reopening checks passed', flush=True)


if '--child' in sys.argv:
    child(*sys.argv[-3:])
else:
    run()
