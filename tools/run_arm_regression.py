#!/usr/bin/env python3
"""Standalone CI suite: does not need proprietary vendor files or a printer."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
qemu=os.environ.get("QEMU_ARM") or shutil.which("qemu-arm-static") or str(ROOT/"qemu/usr/bin/qemu-arm-static")
targets={
    "native":([], "x86_64-unknown-linux-musl"),
    "armv6":([qemu,"-cpu","arm1176"],"arm-unknown-linux-musleabihf"),
    "armv7":([qemu,"-cpu","cortex-a7"],"armv7-unknown-linux-musleabihf")}
results=[]
for name,(prefix,target) in targets.items():
    command=prefix+[str(ROOT/"dist/rust"/("dcpt230-rust-"+target))]
    env=dict(os.environ,DCPT230_RUST_COMMAND=json.dumps(command))
    print("Regression: "+name,flush=True)
    subprocess.run(prefix+[str(ROOT/"dist/rust"/("test-"+target))],check=True,cwd=ROOT)
    for pattern in ("test_rust_consistency.py","test_rust_features.py","test_status.py"):
        subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-v"],
                       cwd=ROOT,env=env,check=True)
    results.append(dict(target=name,passed=True))
(ROOT/"arm-regression-results.json").write_text(json.dumps(results,indent=2)+"\n")
