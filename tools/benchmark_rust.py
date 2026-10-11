"""Measure native Rust vs Python 0.1/0.2; decode and compare every fixture."""
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/"test.ps").exists() or not (ROOT/"multipage.pdf").exists():
    from generate_test_documents import generate
    generate(ROOT)
sys.path.insert(0,str(ROOT/'tests'))
from test_compression import decode

rust=Path(os.environ.get('DCPT230_RUST_BINARY',str(ROOT/'dist/rust/dcpt230-rust-x86_64-unknown-linux-musl')))
versions={
    'python-0.1':ROOT/'tests/fixtures/dcpt230_filter_v0_1.py',
    'python-0.2':ROOT/'src/dcpt230_filter.py',
    'rust':rust,
}
report=[]
with tempfile.TemporaryDirectory(prefix='t230-rust-bench-') as temporary:
    temp=Path(temporary);w,h=2480,3507
    header=b'P6\n%d %d\n255\n'%(w,h)
    fixtures={
        'blank-A4':header+b'\xff'*(w*h*3),
        'RGB-text-A4':subprocess.check_output(['gs','-q','-dSAFER','-dBATCH','-dNOPAUSE',
            '-sDEVICE=ppmraw','-r300','-g2480x3507','-sOutputFile=-','-sstdout=%stderr',
            '-f',str(ROOT/'test.ps')]),
        'noise-A4':header+random.Random(230).randbytes(w*h*3),
    }
    for name,ppm in fixtures.items():
        source=temp/'input.ppm';source.write_bytes(ppm)
        results={};decoded=[]
        for version,path in versions.items():
            target=temp/(version+'.pwg');measurements=[];cpu=[];memory=[]
            for _ in range(3):
                metrics=temp/'time.txt'
                if version=='rust':
                    command=[str(path),'--ppm']
                else:
                    command=[sys.executable,str(ROOT/'tools/benchmark_compression.py'),
                             '--worker',str(path),str(source),str(target)]
                start=time.perf_counter()
                with source.open('rb') as src,target.open('wb') as out:
                    subprocess.run(['/usr/bin/time','-f','%U %S %M','-o',str(metrics)]+command,
                                   stdin=src,stdout=out,check=True)
                measurements.append(time.perf_counter()-start)
                user,system,rss=metrics.read_text().split()
                cpu.append(float(user)+float(system));memory.append(int(rss))
            results[version]=dict(bytes=target.stat().st_size,
                median_seconds=statistics.median(measurements),seconds=measurements,
                cpu_seconds=cpu,peak_rss_kb=memory)
            decoded.append(decode(target.read_bytes()))
        assert decoded[0]==decoded[1]==decoded[2],name+' decoded differently'
        result=dict(fixture=name,decoded_equal=True,results=results)
        report.append(result);print(json.dumps(result),flush=True)
    for version,path in versions.items():
        target=temp/(version+'.prn');times=[];cpu=[];memory=[]
        for _ in range(3):
            metrics=temp/'time.txt'
            command=([str(path)] if version=='rust' else [sys.executable,str(path)])+[
                '1','test','benchmark','1','PageSize=A4',str(ROOT/'multipage.pdf')]
            start=time.perf_counter()
            with target.open('wb') as out:
                subprocess.run(['/usr/bin/time','-f','%U %S %M','-o',str(metrics)]+command,
                               stdout=out,check=True)
            times.append(time.perf_counter()-start)
            user,system,rss=metrics.read_text().split()
            cpu.append(float(user)+float(system));memory.append(int(rss))
        result=dict(fixture='complete-two-page-PDF',version=version,
                    median_seconds=statistics.median(times),seconds=times,
                    bytes=target.stat().st_size,cpu_seconds=cpu,peak_rss_kb=memory)
        report.append(result);print(json.dumps(result),flush=True)
(ROOT/'rust-benchmark-results.json').write_text(json.dumps(report,indent=2)+'\n')
