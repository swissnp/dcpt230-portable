"""Check that public distributions cannot leak private research directories."""
import hashlib
import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_release', ROOT/'tools/prepare_source_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

class SourceReleaseTests(unittest.TestCase):
    def fixture(self, root):
        for name in release.TOP:
            (root/name).write_text('Public source\n')
        (root/'rust').mkdir()
        (root/'rust/Cargo.toml').write_text('[package]\nversion = "0.4.0"\n')
        (root/'src').mkdir()
        (root/'src/filter.py').write_text('print("public")\n')
        for tree in ('docs', 'research-private', 'dist'):
            (root/tree).mkdir()
            (root/tree/'private.md').write_text('PRIVATE RESEARCH MUST NOT BE EXPORTED')

    def test_public_archive_excludes_private_material_and_is_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            archive=release.export(root);first=archive.read_bytes()
            self.assertEqual(release.export(root).read_bytes(),first)
            with tarfile.open(archive) as tar:
                names=tar.getnames()
                self.assertTrue(any(n.endswith('/LICENSE') for n in names))
                self.assertTrue(any(n.endswith('/src/filter.py') for n in names))
                self.assertFalse(any('/docs/' in n or '/research-private/' in n or '/dist/' in n for n in names))
                self.assertFalse(any(b'PRIVATE RESEARCH' in tar.extractfile(n).read() for n in names))
            checksum=archive.with_suffix(archive.suffix+'.sha256').read_text().split()[0]
            self.assertEqual(checksum,hashlib.sha256(first).hexdigest())

    def test_symlink_to_private_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            (root/'src/leak.py').symlink_to(root/'docs/private.md')
            with self.assertRaises(ValueError): release.export(root)

    def test_deployment_address_in_public_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            address='.'.join(('192','168','1','99'))
            (root/'src/filter.py').write_text('# '+address+'\n')
            with self.assertRaises(ValueError): release.export(root)

if __name__=='__main__': unittest.main()
