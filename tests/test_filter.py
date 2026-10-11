import ctypes
import ctypes.util
import importlib.util
import io
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('driver', Path(__file__).resolve().parents[1]/'src/dcpt230_filter.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

class FilterTests(unittest.TestCase):
    def test_multipage_with_independent_cups_decoder(self):
        lib = ctypes.CDLL(ctypes.util.find_library('cups') or '/usr/lib/libcups.2.dylib')
        lib.cupsRasterOpen.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.cupsRasterOpen.restype = ctypes.c_void_p
        lib.cupsRasterReadHeader2.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.cupsRasterReadPixels.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
        lib.cupsRasterClose.argtypes = [ctypes.c_void_p]
        pages = [(1, 2, b'\xff\0\0' * 2), (129, 3, bytes(range(256)) * 4 + bytes(range(137)))]
        ppm = b''.join(b'P6\n# test\n%d %d\n255\n' % (w,h) + pixels for w,h,pixels in pages)
        output = io.BytesIO()
        self.assertEqual(driver.convert(io.BytesIO(ppm), output), 2)
        with tempfile.TemporaryFile() as f:
            f.write(output.getvalue()); f.seek(0)
            raster = lib.cupsRasterOpen(f.fileno(), 0)
            self.assertTrue(raster)
            try:
                for w,h,pixels in pages:
                    header = ctypes.create_string_buffer(1796)
                    self.assertEqual(lib.cupsRasterReadHeader2(raster, header), 1)
                    self.assertEqual(struct.unpack_from('=II', header.raw, 372), (w,h))
                    decoded = ctypes.create_string_buffer(len(pixels))
                    self.assertEqual(lib.cupsRasterReadPixels(raster, decoded, len(pixels)), len(pixels))
                    self.assertEqual(decoded.raw, pixels)
                self.assertEqual(lib.cupsRasterReadHeader2(raster, header), 0)
            finally:
                lib.cupsRasterClose(raster)

    def test_bad_inputs(self):
        for bad in [b'', b'P6\n1 1\n255\n\0', b'P6\n0 1\n255\n', b'P6\n1 1\n65535\n']:
            with self.assertRaises(ValueError):
                driver.convert(io.BytesIO(bad), io.BytesIO())

    def test_envelope(self):
        envelope = driver.preamble({})
        self.assertTrue(envelope.startswith(driver.UEL))
        self.assertTrue(envelope.endswith(b'@PJL ENTER LANGUAGE=PWGRASTER\n'))
        self.assertIn(b'PAPER=A4\n', envelope)
        self.assertIn(b'DRIVER=I0004036110000000100020009000200000007\n', envelope)
        with self.assertRaises(ValueError):
            driver.preamble({'PageSize': 'unknown'})

if __name__ == '__main__':
    unittest.main()
