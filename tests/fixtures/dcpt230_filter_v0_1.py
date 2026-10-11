#!/usr/bin/python3
"""Experimental portable DCP-T230 CUPS PDF/PostScript to PJL/PWG filter."""
import os
import shlex
import struct
import subprocess
import sys
import tempfile

UEL = b'\x1b%-12345X'
PAPERS = {'A4': (595.28, 841.89, 'A4'),
          'Letter': (612, 792, 'LETTER'), 'Legal': (612, 1008, 'LEGAL'),
          'A5': (419.53, 595.28, 'A5'), 'A6': (297.64, 419.53, 'A6')}
PIXELS = {'A4': (2480, 3507), 'Letter': (2550, 3300), 'Legal': (2550, 4200),
          'A5': (1748, 2480), 'A6': (1236, 1748)}

def preamble(options):
    if options.get('BRMonoColor', 'FullColor') != 'FullColor':
        raise ValueError('This version supports color output only')
    if options.get('BRInputSlot', 'AutoSelect') != 'AutoSelect':
        raise ValueError('This version supports automatic tray selection only')
    paper = options.get('PageSize', 'A4')
    if paper not in PAPERS:
        raise ValueError('Unsupported PageSize: ' + paper)
    quality = options.get('BRResolution', 'Normal')
    if quality not in ('Draft', 'Normal', 'Fine'):
        raise ValueError('Unsupported quality')
    if options.get('Duplex', 'None') != 'None':
        raise ValueError('DCP-T230 supports simplex only')
    media = options.get('BRMediaType', 'Plain')
    media_map = {'Plain': 'REGULAR', 'Inkjet': 'INKJET', 'Glossy': 'GLOSSY',
                 'Recycled': 'RECYCLED'}
    if media not in media_map:
        raise ValueError('Unsupported media')
    # JOBSETTINGLOG is a composite value, not a constant identifier.
    # Codes measured against the supplied 3.6.1 vendor executable.
    paper_code = {'A4': 9, 'Letter': 1, 'Legal': 5, 'A5': 11, 'A6': 70}[paper]
    media_code = {'Plain': 1, 'Inkjet': 261, 'Glossy': 263, 'Recycled': 9}[media]
    quality_code = {'Draft': 1, 'Normal': 2, 'Fine': 3}[quality]
    job_id = 'I000403611' + ''.join('%04X' % value for value in
                                    (0, media_code, quality_code, paper_code, 2, 0, 7))
    lines = ['@PJL ', '@PJL SET HOLD=OFF', '@PJL SET STRINGCODESET=UTF8',
             '@PJL SET PAPER=' + PAPERS[paper][2], '@PJL SET BORDERLESS=OFF']
    lines += ['@PJL SET JT' + side + 'MARGIN=300'
              for side in ('TOP', 'BOT', 'LEFT', 'RIGHT')]
    lines += ['@PJL SET RENDERMODE=COLOR',
              '@PJL SET PRINTQUALITY=' + {'Draft': 'DRAFT', 'Normal': 'NORMAL', 'Fine': 'HIGH'}[quality],
              '@PJL SET DUPLEX=OFF', '@PJL SET MEDIATYPE=' + media_map[media],
              '@PJL SET MANUALFEED=OFF', '@PJL SET SOURCETRAY=AUTO',
              '@PJL JOBSETTINGLOG DRIVER=' + job_id,
              '@PJL SET FIDELITY=TRUE', '@PJL ENTER LANGUAGE=PWGRASTER']
    return UEL + ('\n'.join(lines) + '\n').encode('ascii')

def header(width, height):
    h = bytearray(1796)
    h[:9] = b'PwgRaster'
    h[128:132] = b'auto'
    for offset, value in {276: 300, 280: 300, 352: int(width * 72 / 300 + .5),
                          356: int(height * 72 / 300 + .5), 372: width,
                          376: height, 384: 8, 388: 24, 392: width * 3,
                          400: 19, 420: 3}.items():
        struct.pack_into('>I', h, offset, value)
    return h

def encode_row(row):
    """Valid PWG PackBits: literal RGB packets, no repeated scanlines."""
    out = bytearray(b'\0')  # This row appears once.
    for offset in range(0, len(row), 384):
        block = row[offset:offset + 384]
        count = len(block) // 3
        out.append(0 if count == 1 else 257 - count)
        out.extend(block)
    return out

def token(src):
    out = bytearray()
    while True:
        c = src.read(1)
        if not c:
            if out:
                raise ValueError('Truncated PPM header')
            return None
        if c == b'#' and not out:
            src.readline()
        elif c in b' \t\r\n':
            if out:
                return bytes(out)
        else:
            out.extend(c)
            if len(out) > 32:
                raise ValueError('Invalid PPM token')

def convert(src, out):
    pages = 0
    while True:
        magic = token(src)
        if magic is None:
            break
        if magic != b'P6':
            raise ValueError('Expected binary RGB PPM')
        width, height, maximum = (int(token(src)) for _ in range(3))
        if not (0 < width <= 6000 and 0 < height <= 10000 and maximum == 255):
            raise ValueError('Unsupported PPM geometry/depth')
        if not pages:
            out.write(b'RaS2')
        out.write(header(width, height))
        for _ in range(height):
            row = src.read(width * 3)
            if len(row) != width * 3:
                raise ValueError('Truncated PPM pixels')
            out.write(encode_row(row))
        pages += 1
    if not pages:
        raise ValueError('No pages rendered')
    return pages

def main(argv):
    if len(argv) not in (6, 7):
        raise ValueError('Usage: dcpt230-arm job user title copies options [file]')
    options = dict(t.split('=', 1) for t in shlex.split(argv[5]) if '=' in t)
    envelope = preamble(options)
    copies = int(argv[4])
    if not 1 <= copies <= 999:
        raise ValueError('Invalid copy count')
    width, height, _ = PAPERS[options.get('PageSize', 'A4')]
    # Spool input/output to avoid partial printer jobs if rendering fails.
    with tempfile.TemporaryDirectory(prefix='dcpt230-') as temp:
        filename = os.path.join(temp, 'input')
        source = open(argv[6], 'rb') if len(argv) == 7 else sys.stdin.buffer
        try:
            with open(filename, 'wb') as dest:
                while True:
                    block = source.read(65536)
                    if not block:
                        break
                    dest.write(block)
        finally:
            if len(argv) == 7:
                source.close()
        command = ['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dFIXEDMEDIA',
                   '-dPDFFitPage', '-sDEVICE=ppmraw', '-r300',
                   '-g%dx%d' % PIXELS[options.get('PageSize', 'A4')],
                   '-sOutputFile=-', '-sstdout=%stderr', '-f', filename]
        with tempfile.TemporaryFile() as raster:
            process = subprocess.Popen(command, stdout=subprocess.PIPE)
            try:
                pages = convert(process.stdout, raster)
            except BaseException:
                process.kill()
                process.wait()
                raise
            finally:
                process.stdout.close()
            if process.wait() != 0:
                raise ValueError('Ghostscript failed')
            out = sys.stdout.buffer
            # Separate jobs implement collated copies without changing PWG headers.
            for _ in range(copies):
                out.write(envelope)
                raster.seek(0)
                while True:
                    block = raster.read(65536)
                    if not block:
                        break
                    out.write(block)
                out.write(UEL + UEL)
            out.flush()
            print('INFO: Rendered %d pages, %d copies' % (pages, copies), file=sys.stderr)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except (OSError, ValueError, TypeError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
