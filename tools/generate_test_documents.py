#!/usr/bin/env python3
"""Generate synthetic benchmark documents without submitting print jobs."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COLOR_PAGE = b'''%!PS-Adobe-3.0
<< /PageSize [595.28 841.89] >> setpagedevice
/Helvetica findfont 18 scalefont setfont
36 780 moveto (DCP-T230 portable filter test - Page 1) show
0 0 0 setrgbcolor 36 744 moveto (Portable PJL/PWG Raster test) show
1 0 0 setrgbcolor 36 600 140 100 rectfill
0 1 0 setrgbcolor 206 600 140 100 rectfill
0 0 1 setrgbcolor 376 600 140 100 rectfill
0 0 0 setrgbcolor 36 530 moveto (Red              Green             Blue) show
36 470 moveto (Please check text, colors and page margins.) show
showpage
'''

def generate(root=ROOT):
    root = Path(root)
    (root / 'test.ps').write_bytes(COLOR_PAGE)
    pages = b'%!PS\n<< /PageSize [595.28 841.89] >> setpagedevice\n'
    for page in (1, 2):
        pages += (b'/Helvetica findfont 24 scalefont setfont\n'
                  b'36 750 moveto (page %d of 2) show\nshowpage\n' % page)
    (root / 'multipage.ps').write_bytes(pages)
    subprocess.run(['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE',
                    '-sDEVICE=pdfwrite', '-sOutputFile=' + str(root / 'multipage.pdf'),
                    str(root / 'multipage.ps')], check=True)

if __name__ == '__main__':
    generate()
