import importlib.util
from pathlib import Path
import struct
import unittest
spec=importlib.util.spec_from_file_location("status",Path(__file__).resolve().parents[1]/"tools/printer_status.py")
status=importlib.util.module_from_spec(spec);spec.loader.exec_module(status)
class StatusTests(unittest.TestCase):
    def test_usb_flags(self):
        self.assertEqual(status.port_status(0x18),dict(paper_empty=False,selected=True,error=False))
        self.assertEqual(status.port_status(0x20),dict(paper_empty=True,selected=False,error=True))
    def test_multivalue_alerts_and_supplies(self):
        payload=b"\x02\x00\x00\x00\x00\x00\x00\x01\x04"
        payload+=b"\x23\x00\x0dprinter-state\x00\x04"+struct.pack(">i",5)
        payload+=status.attribute(0x44,"printer-state-reasons","media-empty-error")
        payload+=status.attribute(0x44,"","marker-supply-low-warning")
        payload+=status.attribute(0x41,"printer-supply-description","Black ink")
        result=status.summarize(status.parse_response(payload+b"\x03"))
        self.assertEqual(result["state"],"stopped")
        self.assertEqual(result["alerts"],["media-empty-error","marker-supply-low-warning"])
        self.assertEqual(result["supplies"]["printer-supply-description"],["Black ink"])
    def test_idle_does_not_invent_device_details(self):
        result=status.summarize({"printer-state":[3],"printer-state-reasons":["none"]})
        self.assertEqual(result["alerts"],[]);self.assertEqual(result["supplies"],{})
    def test_malformed_and_errors(self):
        for data in (b"",b"\x02\x00\x04\x00"+b"\0"*4,b"\x02\0"+b"\0"*6+b"\x41\x00\xff"):
            with self.assertRaises(ValueError):status.parse_response(data)
