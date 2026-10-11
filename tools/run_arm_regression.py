#!/usr/bin/env python3
"""Standalone CI suite: does not need proprietary vendor files or a printer."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from rust_targets import TARGETS

ROOT=Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--target", choices=tuple(TARGETS))
args = parser.parse_args()
targets = {target: (info["runner"], target) for target, info in TARGETS.items()
           if not args.target or target == args.target}
results=[]
for name,(prefix,target) in targets.items():
    prefix = list(prefix)
    if prefix:
        executable = os.environ.get("QEMU_ARM") if prefix[0] == "qemu-arm-static" else None
        prefix[0] = executable or shutil.which(prefix[0]) or str(ROOT/"qemu/usr/bin"/prefix[0])
    command=prefix+[str(ROOT/"dist/rust"/("dcpt230-rust-"+target))]
    env=dict(os.environ,DCPT230_RUST_COMMAND=json.dumps(command))
    print("Regression: "+name,flush=True)
    subprocess.run(prefix+[str(ROOT/"dist/rust"/("test-"+target))],check=True,cwd=ROOT)
    for pattern in ("test_rust_consistency.py","test_rust_features.py","test_status.py"):
        subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-v"],
                       cwd=ROOT,env=env,check=True)
    results.append(dict(target=name,passed=True))
(ROOT/"arm-regression-results.json").write_text(json.dumps(results,indent=2)+"\n")
