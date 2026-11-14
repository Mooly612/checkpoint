"""Open the actual demo shipped beside the installed package and resolve its data."""
from pathlib import Path
from qgis.core import QgsProject
import checkpoint

package = Path(checkpoint.__file__).resolve().parent
demo = package / 'demo'
if not demo.exists():
    demo = package.parent / 'demo'
project = QgsProject()
try:
    assert project.read(str(demo / 'checkpoint-demo.qgz'))
    layers = {layer.name(): layer for layer in project.mapLayers().values()}
    assert set(layers) == {'Roads', 'Buildings'}
    assert all(layer.isValid() for layer in layers.values())
    assert layers['Roads'].featureCount() == 6 and layers['Roads'].labelsEnabled()
    assert layers['Buildings'].featureCount() == 20
    assert layers['Buildings'].setSubsetString('"floors" >= 3')
    assert 0 < layers['Buildings'].featureCount() < 20
    assert project.crs().authid() == 'EPSG:3857'
    print('Checkpoint packaged demo checks passed', flush=True)
finally:
    project.clear()
