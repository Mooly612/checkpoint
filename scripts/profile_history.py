"""Reproducible synthetic history timings. Fixture creation is outside timers."""
import json, os, sys, tempfile, statistics, resource
from pathlib import Path
from time import perf_counter
sys.path.insert(0, os.environ.get('CHECKPOINT_SOURCE', str(Path(__file__).resolve().parents[1])))
from checkpoint.core.store import HistoryStore

def measure(fn, n=9):
    times=[]
    for i in range(n):
        t=perf_counter(); fn(i); times.append((perf_counter()-t)*1000)
    return dict(median=round(statistics.median(times),3), p95=round(sorted(times)[-1],3), min=round(min(times),3), repeats=n)

with tempfile.TemporaryDirectory() as directory:
    for count, image_bytes in [(20,0),(100,400000),(1000,0)]:
        store=HistoryStore(Path(directory),f'/{count}.qgz',limit=count)
        state={'tree':{'type':'group','name':'','visible':True,'expanded':True,'children':[]},'layers':{},'extent':[0,0,1,1],'scale':100}
        records=[]
        memory=HistoryStore(Path(directory))
        for i in range(count):
            r=memory.append(state,force=True,pinned=True)
            r['preview']={'maps':{'after':'x'*image_bytes}}
            records.append(r)
        with store._transaction(): store._commit(records)
        other=HistoryStore(Path(directory),f'/{count}.qgz',limit=count)
        result={'records':count,'image_bytes':image_bytes,'db_bytes':store.path.stat().st_size}
        key=records[0]['id']
        result['open']=measure(lambda i: HistoryStore(Path(directory),f'/{count}.qgz'))
        result['refresh']=measure(lambda i: store.refresh())
        result['rename_real']=measure(lambda i: store.rename(key,f'name{i}'))
        result['rename_noop']=measure(lambda i: store.rename(key,'name8'))
        result['pin']=measure(lambda i: store.set_pinned(key,bool(i%2)))
        result['external_refresh']=measure(lambda i: (other.rename(key,f'external{i}'),store.refresh()))
        result['rss_peak_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(json.dumps(result),flush=True)
