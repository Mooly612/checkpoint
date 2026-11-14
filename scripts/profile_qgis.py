"""Synthetic GUI-thread benchmark; run with QGIS Python and CHECKPOINT_SOURCE."""
import os, sys, json, statistics, tempfile, resource
from pathlib import Path
from time import perf_counter
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_PLUGIN_PATH','/Applications/QGIS.app/Contents/PlugIns')
os.environ.setdefault('PROJ_DATA','/Applications/QGIS.app/Contents/Resources/qgis/proj')
sys.path.insert(0,os.environ.get('CHECKPOINT_SOURCE',str(Path(__file__).resolve().parents[1])))
from qgis.core import QgsApplication,QgsProject,QgsVectorLayer,QgsRectangle,QgsCategorizedSymbolRenderer,QgsRendererCategory,QgsMarkerSymbol
from qgis.gui import QgsMapCanvas
from qgis.PyQt import sip
from checkpoint.core.snapshot import capture
from checkpoint.core.differ import application_summary,component_hashes
from checkpoint.core.thumbnail import lightweight_preview

def measure(fn):
    values=[]
    for _ in range(5):
        start=perf_counter(); fn(); values.append((perf_counter()-start)*1000)
    return dict(median=round(statistics.median(values),2),p95=round(max(values),2),min=round(min(values),2),repeats=5)

with tempfile.TemporaryDirectory() as profile:
    app=QgsApplication([],True,profile); app.setPrefixPath('/Applications/QGIS.app/Contents/MacOS',True); app.initQgis()
    project=QgsProject(); canvas=QgsMapCanvas()
    for count in (10,100,500):
        project.clear()
        for i in range(count): project.addMapLayer(QgsVectorLayer('Point?crs=EPSG:4326',str(i),'memory'))
        canvas.setDestinationCrs(project.crs()); canvas.setExtent(QgsRectangle(0,0,10,10))
        state=capture(project,canvas)
        print(json.dumps(dict(layers=count,capture=measure(lambda:capture(project,canvas)),components=measure(lambda:component_hashes(state)),summary=measure(lambda:application_summary(state,state)))),flush=True)
    project.clear()
    layer=QgsVectorLayer('Point?crs=EPSG:4326','Categories','memory'); project.addMapLayer(layer)
    for count in (1,100,1000,10000):
        layer.setRenderer(QgsCategorizedSymbolRenderer('id',[QgsRendererCategory(i,QgsMarkerSymbol.createSimple({'color':'red'}),str(i)) for i in range(count)]))
        state=capture(project,canvas)
        print(json.dumps(dict(categories=count,xml_bytes=len(state['layers'][layer.id()]['style']),preview=measure(lambda:lightweight_preview(None,state)),rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)),flush=True)
    canvas.stopRendering(); canvas.setLayers([]); sip.delete(canvas); project.clear(); sip.delete(project)
    app.exitQgis()
