"""Compare optimized output with the frozen 0.1 filter via CUPS decoding."""
import ctypes
import ctypes.util
import importlib.util
import io
from pathlib import Path
import random
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

current = module('optimized', ROOT/'src/dcpt230_filter.py')
baseline = module('baseline', ROOT/'tests/fixtures/dcpt230_filter_v0_1.py')

def decode(data):
    lib = ctypes.CDLL(ctypes.util.find_library('cups'))
    lib.cupsRasterOpen.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.cupsRasterOpen.restype = ctypes.c_void_p
    lib.cupsRasterReadHeader2.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.cupsRasterReadPixels.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    lib.cupsRasterClose.argtypes = [ctypes.c_void_p]
    pages = []
    with tempfile.TemporaryFile() as f:
        f.write(data); f.seek(0)
        raster = lib.cupsRasterOpen(f.fileno(), 0)
        if not raster:
            raise AssertionError('CUPS could not open raster')
        try:
            while True:
                h = ctypes.create_string_buffer(1796)
                if not lib.cupsRasterReadHeader2(raster, h):
                    break
                height = struct.unpack_from('=I', h.raw, 376)[0]
                bpl = struct.unpack_from('=I', h.raw, 392)[0]
                pixels = ctypes.create_string_buffer(height*bpl)
                if lib.cupsRasterReadPixels(raster, pixels, len(pixels)) != len(pixels):
                    raise AssertionError('CUPS could not decode all pixels')
                pages.append((h.raw, pixels.raw))
        finally:
            lib.cupsRasterClose(raster)
    return pages

def encode(driver, pages):
    ppm = b''.join(b'P6\n%d %d\n255\n' % (len(rows[0])//3,len(rows))
                   + b''.join(rows) for rows in pages)
    out = io.BytesIO()
    driver.convert(io.BytesIO(ppm), out)
    return out.getvalue()

class CompressionTests(unittest.TestCase):
    def compare(self, pages):
        old, new = encode(baseline,pages), encode(current,pages)
        old_pages, new_pages = decode(old), decode(new)
        self.assertEqual(new_pages, old_pages)
        self.assertEqual([p[1] for p in new_pages], [b''.join(rows) for rows in pages])
        self.assertLessEqual(len(new),len(old))
        return old,new

    def test_pixel_packet_boundaries(self):
        for width in (1,2,3,127,128,129,255,256,257,6000):
            with self.subTest(width=width):
                self.compare([[b'\xff\xff\xff'*width],
                              [b'\x01\x02\x03'*width]])

    def test_row_repeat_boundaries_and_page_reset(self):
        for height in (1,2,255,256,257,512,513):
            with self.subTest(height=height):
                row = b'\xff\xff\xff'*129
                self.compare([[row]*height,[row]*2])

    def test_unaligned_runs_preserve_channel_order(self):
        # Repetition may start at byte offset 1 or 2, rather than at a pixel.
        for prefix in (b'A',b'AB',b'ABC',b'ABCD',b'ABCDE'):
            for pixel in (b'xyz',b'\0\0\0',b'\xff\xff\xff'):
                row=prefix+pixel*300+b'end'
                row+=b'Z'*(-len(row)%3)
                self.compare([[row]])

    def test_random_and_mixed_rows(self):
        rng=random.Random(230)
        for _ in range(60):
            width=rng.randint(1,1000)
            row=bytearray(rng.getrandbits(8) for _ in range(width*3))
            for _ in range(10):
                start=rng.randrange(width)
                count=rng.randint(1,min(140,width-start))
                pixel=bytes(rng.getrandbits(8) for _ in range(3))
                row[start*3:(start+count)*3]=pixel*count
            row=bytes(row)
            self.compare([[row,row,b'\xff\xff\xff'*width,row]])

    def test_blank_page_compresses_without_loss(self):
        row=b'\xff\xff\xff'*2480
        old,new=self.compare([[row]*3507])
        self.assertLess(len(new),len(old)//1000)

    def test_noise_fallback_and_transition_back_to_flat_rows(self):
        rng=random.Random(64)
        noise=[bytes(rng.getrandbits(8) for _ in range(129*3)) for _ in range(130)]
        flat=b'\xff\xff\xff'*129
        self.compare([noise+[flat]*600+noise,[flat]*257])

    def test_invalid_rows(self):
        for row,repeats in ((b'',1),(b'a',1),(b'abc',0),(b'abc',257)):
            with self.assertRaises(ValueError):
                current.encode_row(row,repeats)

if __name__=='__main__':
    unittest.main()
