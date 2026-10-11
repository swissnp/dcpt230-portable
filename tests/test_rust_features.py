"""Portable grayscale, caching, and error-handling regression tests."""
import io
import itertools
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from test_compression import ROOT,decode,current

class RustFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform!="linux": raise unittest.SkipTest("Linux executable")
        cls.command=json.loads(os.environ.get("DCPT230_RUST_COMMAND",json.dumps(
            [str(ROOT/"dist/rust/dcpt230-rust-x86_64-unknown-linux-musl")])))
        cls.reference=json.loads(os.environ.get("DCPT230_REFERENCE_COMMAND",json.dumps(
            [str(ROOT/"dist/rust/dcpt230-rust-x86_64-unknown-linux-musl")])))
        if not Path(cls.command[0]).exists(): raise unittest.SkipTest("Build Rust first")
    def invoke(self,opts="",source=None,env=None,copies=1):
        args=self.command+["1","test","features",str(copies),opts]
        data=None
        if source is not None: args.append(str(source))
        else: data=b"%!PS\n1 0 0 setrgbcolor 20 20 100 100 rectfill showpage\n"
        return subprocess.run(args,input=data,capture_output=True,env=env,timeout=60)
    def test_gray_packet_limits_and_architecture(self):
        rng=random.Random(230)
        for width in (1,2,127,128,129,255,256,257,6000):
            for repeats in (1,256,257,513):
                row=bytes(rng.randrange(256) for _ in range(width))
                pgm=b"P5\n%d %d\n255\n"%(width,repeats)+row*repeats
                out=subprocess.check_output(self.command+["--ppm"],input=pgm,timeout=30)
                h,pixels=decode(out)[0];self.assertEqual(pixels,row*repeats)
                self.assertEqual(struct.unpack_from("=I",h,400)[0],18)
                if self.command!=self.reference:self.assertEqual(out,subprocess.check_output(self.reference+["--ppm"],input=pgm))
    def test_gray_render_and_envelope(self):
        for paper,quality,media in itertools.product(current.PAPERS,("Draft","Normal","Fine"),
                ("Plain","Inkjet","Glossy","Recycled")):
            text="PageSize=%s BRResolution=%s BRMediaType=%s BRMonoColor=Mono"%(paper,quality,media)
            expected=current.preamble(dict(PageSize=paper,BRResolution=quality,BRMediaType=media))
            expected=expected.replace(b"RENDERMODE=COLOR",b"RENDERMODE=GRAYSCALE")
            expected=expected.replace(b"000200000007\n",b"000100000007\n")
            self.assertEqual(subprocess.check_output(self.command+["--preamble",text]),expected)
        out=self.invoke("PageSize=A6 BRMonoColor=Mono")
        self.assertEqual(out.returncode,0,out.stderr)
        pjl,raster=out.stdout.split(b"RaS2",1)
        self.assertIn(b"RENDERMODE=GRAYSCALE",pjl)
        self.assertIn(b"000100020046000100000007",pjl)
        pages=decode(b"RaS2"+raster.rsplit(current.UEL*2,1)[0])
        h,pixels=pages[0];self.assertEqual(len(pixels),1236*1748)
        self.assertEqual(struct.unpack_from("=I",h,388)[0],8)
        source=b"%!PS\n1 0 0 setrgbcolor 20 20 100 100 rectfill showpage\n"
        pgm=subprocess.check_output(["gs","-q","-dSAFER","-dBATCH","-dNOPAUSE","-dFIXEDMEDIA",
            "-dPDFFitPage","-sDEVICE=pgmraw","-r300","-g1236x1748","-sOutputFile=-","-sstdout=%stderr","-"],input=source)
        stream=io.BytesIO(pgm);[current.token(stream) for _ in range(4)]
        self.assertEqual(pixels,stream.read(),"Grayscale pixels differ from Ghostscript")
    def test_cache_hit_keys_copies_and_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            env=dict(os.environ,DCPT230_CACHE_DIR=str(Path(d)/"cache"))
            opts="PageSize=A6 BRCache=On"
            a=self.invoke(opts,env=env);b=self.invoke(opts,env=env)
            self.assertEqual(a.returncode,0,a.stderr);self.assertEqual(b.stdout,a.stdout)
            self.assertIn(b"cache hit",b.stderr)
            copies=self.invoke(opts,env=env,copies=2)
            self.assertEqual(copies.stdout,a.stdout*2);self.assertIn(b"cache hit",copies.stderr)
            quality=self.invoke(opts+" BRResolution=Fine BRMediaType=Glossy",env=env)
            self.assertIn(b"cache hit",quality.stderr)
            self.assertIn(b"PRINTQUALITY=HIGH",quality.stdout)
            source=Path(d)/"changed.ps";source.write_bytes(b"%!PS\n0 0 0 setrgbcolor 1 1 10 10 rectfill showpage\n")
            changed=self.invoke(opts,source=source,env=env)
            self.assertEqual(changed.returncode,0,changed.stderr);self.assertNotIn(b"cache hit",changed.stderr)
            for changed in ("PageSize=A5 BRCache=On","PageSize=A6 BRMonoColor=Mono BRCache=On"):
                result=self.invoke(changed,env=env)
                self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn(b"cache hit",result.stderr)
            for file in Path(env["DCPT230_CACHE_DIR"]).glob("*.raster"):file.write_bytes(b"corrupt")
            result=self.invoke(opts,env=env);self.assertEqual(result.stdout,a.stdout)
            self.assertNotIn(b"cache hit",result.stderr)
    def test_cache_expiration_and_unsafe_directory(self):
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)/"cache";env=dict(os.environ,DCPT230_CACHE_DIR=str(cache))
            opts="PageSize=A6 BRCache=On";a=self.invoke(opts,env=env)
            for p in cache.glob("*.raster"):os.utime(p,(1,1))
            b=self.invoke(opts,env=env);self.assertEqual(a.stdout,b.stdout);self.assertNotIn(b"cache hit",b.stderr)
            cache.chmod(0o777);c=self.invoke(opts,env=env)
            self.assertEqual(c.returncode,0,c.stderr);self.assertIn(b"cache disabled",c.stderr)
            link=Path(d)/"link";link.symlink_to(cache,target_is_directory=True)
            c=self.invoke(opts,env=dict(env,DCPT230_CACHE_DIR=str(link)))
            self.assertEqual(c.returncode,0,c.stderr);self.assertIn(b"cache disabled",c.stderr)
    def test_cache_disk_and_entry_limits(self):
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)/"cache";cache.mkdir(mode=0o700)
            for i in range(3):
                with (cache/("large%d.raster"%i)).open("wb") as f:f.truncate(90*1024*1024)
            env=dict(os.environ,DCPT230_CACHE_DIR=str(cache))
            result=self.invoke("PageSize=A6 BRCache=On",env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertLessEqual(sum(p.stat().st_size for p in cache.iterdir()),256*1024*1024)
            for p in cache.iterdir():p.unlink()
            for i in range(128):(cache/("entry%d.raster"%i)).write_bytes(b"junk")
            result=self.invoke("PageSize=A6 BRCache=On",env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertLessEqual(len(list(cache.glob("*.raster"))),128)
    def test_failures_never_deliver_partial_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bad.pdf";p.write_bytes(b"invalid PDF")
            result=self.invoke("BRMonoColor=Mono BRCache=On",source=p,
                               env=dict(os.environ,DCPT230_CACHE_DIR=str(Path(d)/"cache")))
            self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,b"")
            self.assertEqual(list((Path(d)/"cache").glob("*.raster")),[])
