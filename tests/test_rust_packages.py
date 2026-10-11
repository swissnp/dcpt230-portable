"""Verify every CPU package's architecture, payload and target selection."""
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rust_targets', ROOT/'tools/rust_targets.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def members(path):
    payload = path.read_bytes()
    assert payload[:8] == b'!<arch>\n'
    result = {}
    offset = 8
    while offset < len(payload):
        header = payload[offset:offset + 60]
        size = int(header[48:58])
        name = header[:16].decode().strip().rstrip('/')
        result[name] = payload[offset + 60:offset + 60 + size]
        offset += 60 + size + size % 2
    return result


class RustPackageTests(unittest.TestCase):
    def fixture(self, root):
        (root/'tools').mkdir()
        for name in ('build_rust_deb.py', 'rust_targets.py'):
            shutil.copyfile(ROOT/'tools'/name, root/'tools'/name)
        for name in ('README.md', 'LICENSE', 'NOTICE', 'src/dcpt230-arm.ppd',
                     'tools/printer_status.py'):
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, path)
        notices = root/'dist/rust/notices'
        notices.mkdir(parents=True)
        for name in ('RUST-COPYRIGHT.html', 'MUSL-COPYRIGHT'):
            (notices/name).write_text('Fixture notice\n')
        for target in module.TARGETS:
            (root/'dist/rust'/('dcpt230-rust-' + target)).write_bytes(target.encode())

    def test_all_cpu_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            subprocess.run([sys.executable, str(root/'tools/build_rust_deb.py')],
                           check=True, capture_output=True)
            self.assertEqual(len(list((root/'dist').glob('*.deb'))), len(module.TARGETS))
            for target, info in module.TARGETS.items():
                with self.subTest(target=target):
                    package = root/'dist'/('dcpt230-portable-rust_0.4.0_' + info['label'] + '.deb')
                    entries = members(package)
                    with tarfile.open(fileobj=io.BytesIO(entries['control.tar.gz'])) as tar:
                        control = tar.extractfile('control').read().decode()
                        self.assertIn('Architecture: ' + info['arch'] + '\n', control)
                    with tarfile.open(fileobj=io.BytesIO(entries['data.tar.gz'])) as tar:
                        binary = tar.getmember('usr/lib/cups/filter/dcpt230-rust')
                        self.assertEqual(binary.mode, 0o755)
                        self.assertEqual(tar.extractfile(binary).read(), target.encode())
                        self.assertIn('usr/share/doc/dcpt230-portable-rust/MUSL-COPYRIGHT', tar.getnames())

    def test_selected_target_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            target = 'aarch64-unknown-linux-musl'
            subprocess.run([sys.executable, str(root/'tools/build_rust_deb.py'),
                            '--target', target], check=True, capture_output=True)
            self.assertEqual([p.name for p in (root/'dist').glob('*.deb')],
                             ['dcpt230-portable-rust_0.4.0_arm64.deb'])


if __name__ == '__main__':
    unittest.main()
