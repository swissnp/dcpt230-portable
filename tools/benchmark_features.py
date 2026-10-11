#!/usr/bin/env python3
"""Compare Rust 0.3/0.4 encoding and cold/warm rendering without printing."""
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
sys.path.insert(0,str(ROOT/"tests"))
from test_compression import decode
new=Path(os.environ.get("DCPT230_RUST_BINARY",str(ROOT/"dist/rust/dcpt230-rust-x86_64-unknown-linux-musl")))
old=Path(os.environ.get("DCPT230_BASELINE_RUST",str(ROOT/"package-check/amd64/usr/lib/cups/filter/dcpt230-rust")))
report=[]
with tempfile.TemporaryDirectory() as d:
    temp=Path(d)
    def measure(command,source,env=None):
        times=[];cpu=[];sizes=[];last=None
        for i in range(5):
            metrics=temp/"time";target=temp/"out"
            start=time.perf_counter()
            with source.open("rb") as src,target.open("wb") as out:
                r=subprocess.run(["/usr/bin/time","-f","%U %S","-o",str(metrics)]+list(map(str,command)),
                                 stdin=src,stdout=out,stderr=subprocess.PIPE,env=env,check=True)
            times.append(time.perf_counter()-start);u,s=map(float,metrics.read_text().split());cpu.append(u+s)
            sizes.append(target.stat().st_size);last=target.read_bytes()
        return dict(median_seconds=statistics.median(times),seconds=times,cpu_seconds=cpu,bytes=sizes[-1]),last
    w,h=2480,3507;header=b"P6\n%d %d\n255\n"%(w,h)
    text=subprocess.check_output(["gs","-q","-dSAFER","-dBATCH","-dNOPAUSE","-sDEVICE=ppmraw",
        "-r300","-g2480x3507","-sOutputFile=-","-sstdout=%stderr","-f",str(ROOT/"test.ps")])
    fixtures={"blank":header+b"\xff"*(w*h*3),"text-color":text,
              "noise":header+random.Random(230).randbytes(w*h*3)}
    for name,data in fixtures.items():
        source=temp/"input.ppm";source.write_bytes(data)
        a,ao=measure([old,"--ppm"],source);b,bo=measure([new,"--ppm"],source)
        assert ao==bo and decode(ao)==decode(bo)
        report.append(dict(fixture=name,baseline=a,current=b,bytes_equal=True))
    source=ROOT/"multipage.pdf"
    for mode in ("FullColor","Mono"):
        args=[new,"1","test","benchmark","1","PageSize=A4 BRMonoColor="+mode,source]
        cold,output=measure(args,source)
        cache=temp/("cache-"+mode);env=dict(os.environ,DCPT230_CACHE_DIR=str(cache))
        warmargs=args.copy();warmargs[5]+=" BRCache=On"
        subprocess.run(list(map(str,warmargs)),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=env,check=True)
        warm,cached=measure(warmargs,source,env)
        assert output==cached
        report.append(dict(fixture="two-page-PDF-"+mode,cold=cold,warm_cache=warm,bytes_equal=True))
(ROOT/"feature-benchmark-results.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
