"""Benchmark frozen 0.1 versus optimized filter, verifying decoded equality."""
import importlib.util
import io
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
if "--worker" not in sys.argv and (not (ROOT/"test.ps").exists() or not (ROOT/"multipage.pdf").exists()):
    from generate_test_documents import generate
    generate(ROOT)

def load(path):
    spec=importlib.util.spec_from_file_location('filter',path)
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    return driver

if len(sys.argv)>1 and sys.argv[1]=='--worker':
    driver=load(sys.argv[2])
    with open(sys.argv[3],'rb') as source,open(sys.argv[4],'wb') as out:
        driver.convert(source,out)
    raise SystemExit(0)

sys.path.insert(0,str(ROOT/'tests'))
from test_compression import decode

filters={'baseline':ROOT/'tests/fixtures/dcpt230_filter_v0_1.py',
         'optimized':ROOT/'src/dcpt230_filter.py'}
width,height=2480,3507
report=[]
with tempfile.TemporaryDirectory(prefix='t230-bench-') as temporary:
    temp=Path(temporary)
    ppm_header=b'P6\n%d %d\n255\n'%(width,height)
    fixtures={
        'blank-A4':ppm_header+b'\xff'*(width*height*3),
        'RGB-text-A4':subprocess.check_output(['gs','-q','-dSAFER','-dBATCH','-dNOPAUSE',
            '-sDEVICE=ppmraw','-r300','-g2480x3507','-sOutputFile=-','-sstdout=%stderr',
            '-f',str(ROOT/'test.ps')]),
        'noise-A4':ppm_header+random.Random(230).randbytes(width*height*3),
    }
    for name,ppm in fixtures.items():
        source=temp/'input.ppm';source.write_bytes(ppm)
        results={};decoded={}
        for version,path in filters.items():
            times=[]
            target=temp/(version+'.pwg')
            for _ in range(3):
                start=time.perf_counter()
                subprocess.run([sys.executable,__file__,'--worker',str(path),str(source),str(target)],check=True)
                times.append(time.perf_counter()-start)
            results[version]=dict(bytes=target.stat().st_size,seconds=times,
                                 median_seconds=statistics.median(times))
            decoded[version]=decode(target.read_bytes())
        assert decoded['baseline']==decoded['optimized'],name+' decoded differently'
        result=dict(fixture=name,decoded_equal=True,results=results,
                    size_reduction_percent=100*(1-results['optimized']['bytes']/results['baseline']['bytes']),
                    speedup=results['baseline']['median_seconds']/results['optimized']['median_seconds'])
        report.append(result);print(json.dumps(result),flush=True)
    for version,path in filters.items():
        target=temp/(version+'-complete.prn')
        start=time.perf_counter()
        with target.open('wb') as out:
            subprocess.run([sys.executable,str(path),'1','test','benchmark','1','PageSize=A4',
                            str(ROOT/'multipage.pdf')],stdout=out,check=True)
        report.append(dict(fixture='complete-two-page-PDF',version=version,
                           seconds=time.perf_counter()-start,bytes=target.stat().st_size))
(ROOT/'benchmark-results.json').write_text(json.dumps(report,indent=2)+'\n')
