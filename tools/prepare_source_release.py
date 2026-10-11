#!/usr/bin/env python3
"""Export public source only, with a deterministic archive and file manifest."""
import gzip
import hashlib
import io
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TOP = ('README.md', 'LICENSE', 'NOTICE', 'CONTRIBUTING.md', 'CHANGELOG.md', '.gitignore')
TREES = {'src': {'.py', '.ppd'}, 'rust': {'.rs', '.toml'},
         'tests': {'.py'}, 'tools': {'.py', '.sh', '.rules'},
         '.github': {'.yml', '.yaml'}}
PRIVATE = re.compile(r'(?:192\.168\.\d{1,3}\.\d{1,3}|/home/[A-Za-z0-9_.-]+/dcpt230-portable-test|'
                     r'/Users/[A-Za-z0-9_.-]+/|\bE[0-9]{5}J[0-9]H[0-9]{6}\b)')

def source_files(root=ROOT):
    root = Path(root)
    paths = [root / name for name in TOP]
    for tree, extensions in TREES.items():
        paths.extend(p for p in (root / tree).rglob('*')
                     if p.suffix in extensions and 'target' not in p.relative_to(root).parts
                     and '__pycache__' not in p.parts and not p.name.startswith('vendor-'))
    for path in sorted(set(paths)):
        parts=path.relative_to(root).parts
        if any(root.joinpath(*parts[:i]).is_symlink() for i in range(1,len(parts)+1)) or not path.is_file():
            raise ValueError('Expected regular source file: ' + str(path.relative_to(root)))
        if PRIVATE.search(path.read_text()):
            raise ValueError('Private deployment detail in ' + str(path.relative_to(root)))
        yield path

def export(root=ROOT):
    root = Path(root)
    version = re.search(r'^version = "([\d.]+)"',
                        (root / 'rust/Cargo.toml').read_text(), re.MULTILINE).group(1)
    prefix = 'dcpt230-portable-' + version
    buffer = io.BytesIO()
    manifest = []
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for path in source_files(root):
            name = path.relative_to(root).as_posix()
            payload = path.read_bytes()
            manifest.append(name)
            entry = tarfile.TarInfo(prefix + '/' + name)
            entry.size = len(payload)
            entry.mode = 0o755 if name.startswith('tools/') and path.suffix == '.sh' else 0o644
            entry.mtime = entry.uid = entry.gid = 0
            archive.addfile(entry, io.BytesIO(payload))
    output = root / 'dist' / (prefix + '-source.tar.gz')
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
    output.with_suffix(output.suffix + '.sha256').write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + output.name + '\n')
    output.with_suffix(output.suffix + '.manifest').write_text('\n'.join(manifest) + '\n')
    return output

if __name__ == '__main__':
    print(export())
