"""Run the audit reproduction in subprocesses and report native exit codes.
Use QGIS Python. --matrix additionally isolates runner teardown ordering.
"""
import argparse, subprocess, sys, os
from pathlib import Path
parser=argparse.ArgumentParser(); parser.add_argument('--matrix',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
source=(root/'scripts/run_qgis_checks.py').read_text()
variants={'fixed':source}
if args.matrix:
    variants['legacy']=source.replace('        gc.collect()','        pass').replace('        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)','        pass')
    variants['gc_only']=source.replace('        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)','        pass')
    variants['deferred_only']=source.replace('        gc.collect()','        pass')
for name,script in variants.items():
    code='import sys\nsys.argv=["runner","--only","qgis_shutdown_smoke"]\n__file__='+repr(str(root/'scripts/run_qgis_checks.py'))+'\nexec(compile('+repr(script)+',__file__,"exec"))'
    result=subprocess.run([sys.executable,'-X','faulthandler','-c',code],cwd=root,capture_output=True,text=True)
    print(name,'exit',result.returncode,flush=True)
    if result.returncode and name=='fixed':
        print(result.stdout,result.stderr); raise SystemExit(1)
