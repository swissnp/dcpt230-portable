#!/usr/bin/env python3
"""Read CUPS queue status via IPP, without opening or claiming the USB printer."""
import argparse
import json
import struct
import urllib.parse
import urllib.request
import ctypes
import ctypes.util

def port_status(bits):
    return dict(paper_empty=bool(bits&0x20),selected=bool(bits&0x10),error=not bool(bits&0x08))

def usb_status():
    """Standard printer-class read only; never detach or claim CUPS interfaces."""
    library=ctypes.util.find_library("usb-1.0")
    if not library:return dict(available=False,reason="libusb-1.0 unavailable")
    lib=ctypes.CDLL(library)
    lib.libusb_init.argtypes=[ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_open_device_with_vid_pid.argtypes=[ctypes.c_void_p,ctypes.c_uint16,ctypes.c_uint16]
    lib.libusb_open_device_with_vid_pid.restype=ctypes.c_void_p
    lib.libusb_control_transfer.argtypes=[ctypes.c_void_p,ctypes.c_uint8,ctypes.c_uint8,
        ctypes.c_uint16,ctypes.c_uint16,ctypes.c_void_p,ctypes.c_uint16,ctypes.c_uint]
    lib.libusb_close.argtypes=[ctypes.c_void_p];lib.libusb_exit.argtypes=[ctypes.c_void_p]
    context=ctypes.c_void_p()
    code=lib.libusb_init(ctypes.byref(context))
    if code<0:return dict(available=False,reason="libusb initialization failed",code=code)
    handle=None
    try:
        # VID/PID and printer interface verified from the attached DCP-T230 descriptors.
        handle=lib.libusb_open_device_with_vid_pid(context,0x04f9,0x0716)
        if not handle:return dict(available=False,reason="DCP-T230 absent or USB access denied")
        byte=ctypes.c_ubyte()
        code=lib.libusb_control_transfer(handle,0xa1,1,0,0,ctypes.byref(byte),1,1000)
        if code!=1:return dict(available=False,reason="USB status request unavailable",code=code)
        return dict(available=True,raw=byte.value,**port_status(byte.value),
                    note="Standard port status; device may return benign flags. Ink levels unavailable.")
    finally:
        if handle:lib.libusb_close(handle)
        lib.libusb_exit(context)

def attribute(tag, name, value):
    name=name.encode();value=value.encode()
    return bytes([tag])+struct.pack(">H",len(name))+name+struct.pack(">H",len(value))+value

def parse_response(data):
    if len(data)<8: raise ValueError("Truncated IPP response")
    status=struct.unpack_from(">H",data,2)[0]
    if status>=0x400: raise ValueError("IPP error 0x%04x"%status)
    values={};pos=8;name=None
    while pos<len(data):
        tag=data[pos];pos+=1
        if tag==3: return values
        if tag<16: name=None;continue
        def take():
            nonlocal pos
            if pos+2>len(data): raise ValueError("Truncated IPP length")
            n=struct.unpack_from(">H",data,pos)[0];pos+=2
            if pos+n>len(data): raise ValueError("Truncated IPP value")
            value=data[pos:pos+n];pos+=n
            return value
        raw_name=take();raw=take()
        if raw_name: name=raw_name.decode("utf-8","replace")
        if name is None: raise ValueError("IPP value without attribute")
        if tag in (0x21,0x23):
            if len(raw)!=4: raise ValueError("Invalid IPP integer")
            value=struct.unpack(">i",raw)[0]
        elif tag==0x22:
            if len(raw)!=1: raise ValueError("Invalid IPP boolean")
            value=bool(raw[0])
        else: value=raw.decode("utf-8","replace")
        values.setdefault(name,[]).append(value)
    raise ValueError("Missing IPP end tag")

def summarize(attrs):
    first=lambda key,default=None:attrs.get(key,[default])[0]
    reasons=attrs.get("printer-state-reasons",["unknown"])
    return dict(state={3:"idle",4:"printing",5:"stopped"}.get(first("printer-state"),"unknown"),
                accepting_jobs=first("printer-is-accepting-jobs"),
                message=first("printer-state-message",""),
                reasons=reasons,
                alerts=[r for r in reasons if r not in ("none","unknown")],
                supplies={k:v for k,v in attrs.items() if k.startswith("printer-supply") or k=="marker-levels"},
                source="CUPS queue (USB backend reports available device information)")

def query(queue,server="http://localhost:631"):
    url=urllib.parse.urlsplit(server)
    if url.scheme not in ("http","https") or not url.hostname: raise ValueError("Use HTTP(S) CUPS server")
    path="/printers/"+urllib.parse.quote(queue,safe="")
    uri="ipp://"+url.netloc+path
    body=b"\x02\x00\x00\x0b\x00\x00\x00\x01\x01"
    body+=attribute(0x47,"attributes-charset","utf-8")
    body+=attribute(0x48,"attributes-natural-language","en")
    body+=attribute(0x45,"printer-uri",uri)
    for i,name in enumerate(("printer-state","printer-state-reasons","printer-state-message",
                             "printer-is-accepting-jobs","printer-supply","printer-supply-description","marker-levels")):
        body+=attribute(0x44,"requested-attributes" if i==0 else "",name)
    body+=b"\x03"
    request=urllib.request.Request(server.rstrip("/")+path,body,{"Content-Type":"application/ipp"})
    with urllib.request.urlopen(request,timeout=5) as response:
        data=response.read(1024*1024+1)
    if len(data)>1024*1024: raise ValueError("Oversized IPP response")
    return summarize(parse_response(data))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("queue",nargs="?",default="DCPT230");p.add_argument("--server",default="http://localhost:631")
    p.add_argument("--usb",action="store_true",help="Also attempt read-only local USB port status")
    args=p.parse_args()
    try:
        result=query(args.queue,args.server)
        if args.usb:result["usb"]=usb_status()
        print(json.dumps(result,indent=2))
    except Exception as e: p.exit(1,"Status query failed: %s\n"%e)
if __name__=="__main__":main()
