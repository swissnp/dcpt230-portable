#!/usr/bin/env python3
"""Compare Rust and a locally supplied Brother driver on one Linux host.

Does not install vendor software or submit print jobs. The PDF benchmark uses
an identical Ghostscript renderer for both encoders, not Brother's CUPS wrapper.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def worker(source, command):
    renderer = subprocess.Popen([
        'gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dFIXEDMEDIA',
        '-dPDFFitPage', '-sDEVICE=ppmraw', '-r300', '-g2480x3507',
        '-sOutputFile=-', '-sstdout=%stderr', '-f', source], stdout=subprocess.PIPE)
    try:
        encoded = subprocess.run(command, stdin=renderer.stdout)
        renderer.stdout.close()
        rendered = renderer.wait()
        if encoded.returncode or rendered:
            raise RuntimeError('Rendering or encoding failed')
    finally:
        if renderer.poll() is None:
            renderer.kill()
            renderer.wait()


def raster(data):
    # Brother emits a PJL envelope; --ppm emits a bare PWG stream.
    if not data.startswith(b'RaS2'):
        data = b'RaS2' + data.split(b'RaS2', 1)[1]
        data = data.rsplit(b'\x1b%-12345X' * 2, 1)[0]
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor-dir', type=Path, required=True,
                        help='Extracted Brother dcpt230 directory containing inf/ and lpd/')
    parser.add_argument('--rust', type=Path, default=ROOT/'dist/rust/dcpt230-rust-x86_64-unknown-linux-musl')
    parser.add_argument('--runs', type=int, default=7)
    parser.add_argument('--output', type=Path, default=ROOT/'official-benchmark-results.json')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run on Linux with Ghostscript, libcups and GNU time installed')
    if args.runs < 3:
        parser.error('Use at least three measured runs')
    sys.path.insert(0, str(ROOT/'tests'))
    from test_compression import decode
    from generate_test_documents import generate
    vendor = args.vendor_dir.resolve()
    binary = vendor/'lpd/x86_64/brdcpt230filter'
    rust = args.rust.resolve()
    for path in (binary, rust, vendor/'inf/brdcpt230rc', vendor/'inf/paperinfij2'):
        if not path.is_file():
            parser.error('Missing input: ' + str(path))
    env = dict(os.environ)
    for key in ('OWNER', 'TITLE'):
        env.pop(key, None)
    report = dict(host=platform.platform(), cpu=platform.processor(),
                  cpu_info=subprocess.check_output(["lscpu"], text=True),
                  ghostscript=subprocess.check_output(["gs", "--version"], text=True).strip(),
                  vendor_version=subprocess.check_output(["dpkg-query", "-W", "dcpt230pdrv"], text=True).strip(),
                  rust_sha256=hashlib.sha256(rust.read_bytes()).hexdigest(),
                  vendor_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  runs=args.runs, warmups=1, dpi=300, cache='off', results=[])
    with tempfile.TemporaryDirectory(prefix='dcpt230-official-benchmark-') as temporary:
        temp = Path(temporary)
        generate(temp)
        rc = temp/'brdcpt230rc'
        rc.write_text((vendor/'inf/brdcpt230rc').read_text().replace('PageSize=Letter', 'PageSize=A4'))
        commands = {'official': [str(binary), '-pi', str(vendor/'inf/paperinfij2'), '-rc', str(rc)],
                    'rust': [str(rust), '--ppm']}
        header = b'P6\n2480 3507\n255\n'
        fixtures = {'blank-A4': header + b'\xff' * (2480 * 3507 * 3),
                    'noise-A4': header + random.Random(230).randbytes(2480 * 3507 * 3)}
        rendered = subprocess.check_output(['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE',
            '-sDEVICE=ppmraw', '-r300', '-g2480x3507', '-sOutputFile=-', '-sstdout=%stderr',
            '-f', str(temp/'test.ps')])
        # Normalize comments for Brother's PPM parser.
        import io
        from test_compression import current
        stream = io.BytesIO(rendered)
        for _ in range(4):
            current.token(stream)
        fixtures['text-color-A4'] = header + stream.read()
        for name in (*fixtures, 'two-page-PDF-common-renderer'):
            source = temp/'input.ppm'
            if name in fixtures:
                source.write_bytes(fixtures[name])
            measurements = {key: [] for key in commands}
            outputs = {}
            for trial in range(args.runs + 1):
                # Alternate order to reduce warm-cache and scheduling bias.
                order = list(commands) if trial % 2 == 0 else list(reversed(commands))
                for key in order:
                    command = commands[key]
                    if name not in fixtures:
                        command = [sys.executable, str(Path(__file__).resolve()), '--worker',
                                   str(temp/'multipage.pdf'), json.dumps(command)]
                    output = temp/(key + '.prn')
                    metrics = temp/'time.txt'
                    start = time.perf_counter()
                    with source.open('rb') as stdin, output.open('wb') as stdout:
                        subprocess.run(['/usr/bin/time', '-f', '%U %S %M', '-o', str(metrics)] + command,
                                       stdin=stdin, stdout=stdout, env=env, check=True)
                    elapsed = time.perf_counter() - start
                    user, system, rss = metrics.read_text().split()
                    if trial:
                        measurements[key].append(dict(seconds=elapsed, cpu_seconds=float(user)+float(system),
                                                      peak_rss_kib=int(rss)))
                    outputs[key] = output.read_bytes()
            if decode(raster(outputs['official'])) != decode(raster(outputs['rust'])):
                raise RuntimeError(name + ': decoded output differs')
            results = {key: dict(median_seconds=statistics.median(r['seconds'] for r in rows),
                                median_cpu_seconds=statistics.median(r['cpu_seconds'] for r in rows),
                                median_peak_rss_kib=statistics.median(r['peak_rss_kib'] for r in rows),
                                bytes=len(outputs[key]), trials=rows)
                       for key, rows in measurements.items()}
            row = dict(fixture=name, decoded_equal=True, results=results,
                       speedup=results['official']['median_seconds']/results['rust']['median_seconds'])
            report['results'].append(row)
            print(json.dumps(row), flush=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--worker']:
        worker(sys.argv[2], json.loads(sys.argv[3]))
    else:
        main()
