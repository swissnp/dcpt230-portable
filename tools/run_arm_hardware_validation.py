#!/usr/bin/env python3
"""Run both ARM executables on real ARM hardware, with independent CUPS decoding."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
targets={"armv6":"arm-unknown-linux-musleabihf","armv7":"armv7-unknown-linux-musleabihf"}
summary=[]
for name,target in targets.items():
    reference=targets["armv7" if name=="armv6" else "armv6"]
    env=dict(os.environ,DCPT230_RUST_COMMAND=json.dumps([str(ROOT/"dist/rust"/("dcpt230-rust-"+target))]),
             DCPT230_REFERENCE_COMMAND=json.dumps([str(ROOT/"dist/rust"/("dcpt230-rust-"+reference))]))
    print("Physical ARM regression: "+name,flush=True)
    with (ROOT/("arm-hardware-checks-"+name+".log")).open("wb") as out:
        for pattern in ("test_rust_consistency.py","test_rust_features.py","test_status.py"):
            subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-v"],
                           cwd=ROOT,env=env,stdout=out,stderr=out,check=True)
    summary.append(dict(target=name,passed=True))
model=Path("/proc/device-tree/model")
report=dict(model=model.read_text().strip("\0") if model.exists() else platform.machine(),
            kernel=platform.platform(),results=summary)
(ROOT/"arm-hardware-validation-results.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
