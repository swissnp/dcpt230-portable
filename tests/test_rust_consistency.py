"""Independent CUPS decoding compares Rust with Python 0.1 and 0.2.

Set DCPT230_RUST_COMMAND to a JSON argv array to test under QEMU as well.
"""
import io
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest

from test_compression import ROOT, baseline, current, decode, encode

class RustConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform!='linux' and 'DCPT230_RUST_COMMAND' not in os.environ:
            raise unittest.SkipTest('Default Rust binary targets Linux; provide a host command')
        default=ROOT/'dist/rust/dcpt230-rust-x86_64-unknown-linux-musl'
        cls.command=json.loads(os.environ.get('DCPT230_RUST_COMMAND',json.dumps([str(default)])))
        cls.reference=json.loads(os.environ.get('DCPT230_REFERENCE_COMMAND',json.dumps([str(default)])))
        if not Path(cls.command[0]).exists():
            raise unittest.SkipTest('Build the Rust binary first')

    def check_pages(self,pages):
        ppm=b''.join(b'P6\n# RGB consistency fixture\n%d %d\n255\n'%
                     (len(rows[0])//3,len(rows))+b''.join(rows) for rows in pages)
        result=subprocess.run(self.command+['--ppm'],input=ppm,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        if self.command!=self.reference:
            native_output=subprocess.check_output(self.reference+['--ppm'],input=ppm,timeout=30)
            self.assertEqual(result.stdout,native_output,'Cross-architecture Rust bytes differ')
        decoded=decode(result.stdout)
        self.assertEqual(decoded,decode(encode(current,pages)))
        self.assertEqual(decoded,decode(encode(baseline,pages)))
        self.assertEqual([p[1] for p in decoded],[b''.join(rows) for rows in pages])

    def test_pixel_and_scanline_limits(self):
        for width in (1,2,3,127,128,129,255,256,257,6000):
            for repeat in (1,2,255,256,257,513):
                with self.subTest(width=width,repeat=repeat):
                    flat=b'\x10\x20\x30'*width
                    self.check_pages([[flat]*repeat,[flat]*2])

    def test_random_mixed_and_unaligned_data(self):
        rng=random.Random(230)
        for _ in range(40):
            width=rng.randint(1,1000)
            row=bytearray(rng.getrandbits(8) for _ in range(width*3))
            for _ in range(8):
                start=rng.randrange(width);count=rng.randint(1,min(140,width-start))
                pixel=bytes(rng.getrandbits(8) for _ in range(3))
                row[start*3:(start+count)*3]=pixel*count
            self.check_pages([[bytes(row)]*2,[b'\xff\xff\xff'*width,bytes(row)]])
        for prefix in (b'A',b'AB',b'ABC',b'ABCD',b'ABCDE'):
            row=prefix+b'xyz'*300+b'end';row+=b'Z'*(-len(row)%3)
            self.check_pages([[row]])

    def test_noise_flat_transition_and_blank_a4(self):
        rng=random.Random(64)
        noise=[bytes(rng.getrandbits(8) for _ in range(129*3)) for _ in range(130)]
        flat=b'\xff\xff\xff'*129
        self.check_pages([noise+[flat]*600+noise,[flat]*257])
        self.check_pages([[b'\xff\xff\xff'*2480]*3507])

    def test_all_supported_envelopes(self):
        for paper,quality,media in itertools.product(current.PAPERS,
                ('Draft','Normal','Fine'),('Plain','Inkjet','Glossy','Recycled')):
            opts=dict(PageSize=paper,BRResolution=quality,BRMediaType=media)
            text=' '.join(k+'='+v for k,v in opts.items())
            result=subprocess.run(self.command+['--preamble',text],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,current.preamble(opts))
            self.assertEqual(result.stdout,baseline.preamble(opts))
        text="PageSize='Letter' BRResolution=\"Fine\" title=hello\\ world"
        result=subprocess.run(self.command+['--preamble',text],capture_output=True,timeout=10)
        self.assertEqual(result.stdout,current.preamble(dict(PageSize='Letter',BRResolution='Fine')))

    def test_malformed_ppm_and_options(self):
        for bad in (b'',b'P6\n1 1\n255\n\0',b'P6\n0 1\n255\n',
                    b'P6\n1 1\n65535\n',b'P6\n6001 1\n255\n',b'P6\n1',b'P4\n1 1\n255\n\0'):
            result=subprocess.run(self.command+['--ppm'],input=bad,capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
        for opts in ('PageSize=Unknown','BRMonoColor=Invalid','Duplex=DuplexNoTumble',
                     'BRMediaType=Unknown','BRInputSlot=Manual','BRResolution=Unknown',"PageSize='A4"):
            result=subprocess.run(self.command+['--preamble',opts],capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(result.stdout)

if __name__=='__main__':
    unittest.main()
