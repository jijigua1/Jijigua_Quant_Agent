import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('terminal_paper_upload', Path(__file__).parents[1] / 'deploy' / 'terminal_paper_upload.py')
uploader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uploader)
PDF = b'%PDF-1.4\nsynthetic transport fixture, not a paper\n%%EOF\n'


class TerminalPaperUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.received = self.root / 'received'
        self.received.mkdir()
        self.staging = self.root / 'staging'
        self.staging.mkdir()
        self.uid_patch = patch.object(uploader.os, 'geteuid', lambda: self.received.stat().st_uid, create=True)
        self.uid_patch.start()

    def tearDown(self):
        self.uid_patch.stop()
        self.temp.cleanup()

    def write(self, name='论文 空格.pdf', content=PDF):
        p = self.received / name
        p.write_bytes(content)
        return p

    def test_batch_checks_type_content_and_deduplicates(self):
        self.write()
        self.write('duplicate.pdf')
        checked = uploader.check_received(self.received)
        self.assertEqual(len(checked), 1)
        self.assertEqual(len(checked[0][1]), 64)
        self.write('fake.pdf', b'not a PDF')
        with self.assertRaisesRegex(SystemExit, '本批没有导入'):
            uploader.check_received(self.received)

    def test_word_empty_large_and_directory_are_rejected(self):
        for name, content in [('paper.docx', PDF), ('empty.pdf', b'')]:
            p = self.write(name, content)
            with self.assertRaises(SystemExit):
                uploader.check_received(self.received)
            p.unlink()
        self.write()
        with patch.object(uploader, 'MAX_BYTES', 2), self.assertRaises(SystemExit):
            uploader.check_received(self.received)
        (self.received / 'subdirectory').mkdir()
        with self.assertRaises(SystemExit):
            uploader.check_received(self.received)

    @unittest.skipUnless(os.name == 'posix', 'real link ownership is checked on Linux')
    def test_symlinks_and_hardlinks_are_rejected(self):
        original = self.root / 'original.pdf'
        original.write_bytes(PDF)
        target = self.received / 'linked.pdf'
        target.symlink_to(original)
        with self.assertRaises(SystemExit):
            uploader.check_received(self.received)
        target.unlink()
        os.link(original, target)
        with self.assertRaises(SystemExit):
            uploader.check_received(self.received)

    def test_import_preserves_unicode_hash_and_existing_launcher_contract(self):
        original = self.write('论文 $(echo bad); 空格.pdf')
        path, sha = uploader.check_received(self.received)[0]

        def run(args, **kwargs):
            self.assertEqual(args[:4], [sys.executable, '-I', str(uploader.LAUNCHER), 'paper-import'])
            self.assertRegex(args[4], r'^up-[0-9a-f]{16}-[0-9a-f]{8}\.pdf$')
            decoded = base64.urlsafe_b64decode(args[5] + '=' * (-len(args[5]) % 4)).decode('utf-8')
            self.assertEqual(decoded, original.name)
            self.assertEqual(args[6], sha)
            self.assertEqual((self.staging / args[4]).read_bytes(), PDF)
            self.assertNotIn('shell', kwargs)
            return subprocess.CompletedProcess(args, 0, json.dumps({'name': decoded, 'version': 1, 'pages': 1}), '')

        with patch.object(uploader.subprocess, 'run', run):
            result = uploader.import_received(path, sha, self.staging)
        self.assertEqual(result['pages'], 1)
        self.assertFalse(original.exists())
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_import_failure_timeout_and_bad_response_cleanup_only_the_staged_file(self):
        sentinel = self.staging / 'existing.pdf'
        sentinel.write_bytes(b'keep')
        for response in [subprocess.CompletedProcess([], 1, '', 'rejected'),
                         subprocess.CompletedProcess([], 0, 'not json', ''),
                         subprocess.TimeoutExpired('importer', 120)]:
            path = self.write()
            _, sha = uploader.check_received(self.received)[0]
            kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
            with patch.object(uploader.subprocess, 'run', **kwargs), self.assertRaises(SystemExit):
                uploader.import_received(path, sha, self.staging)
            self.assertEqual(list(self.staging.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_failed_receive_never_imports_or_leaves_temporary_files(self):
        with patch.object(uploader, 'private_staging', return_value=self.staging), \
             patch.object(uploader, 'receive_into', side_effect=SystemExit('cancelled')), \
             patch.object(uploader, 'import_received') as importer:
            with self.assertRaises(SystemExit):
                uploader.upload()
        importer.assert_not_called()
        self.assertEqual(list(self.staging.iterdir()), [])

    def test_receive_restores_terminal_after_cancel_timeout_and_interrupt(self):
        terminal = types.SimpleNamespace(isatty=lambda: True, fileno=lambda: 17)
        fake_termios = types.SimpleNamespace(tcgetattr=lambda fd: ['saved'], tcsetattr=unittest.mock.Mock(), TCSANOW=0)
        outcomes = [subprocess.CompletedProcess([], 1), subprocess.TimeoutExpired('rz', 600), KeyboardInterrupt()]
        for outcome in outcomes:
            fake_termios.tcsetattr.reset_mock()
            kwargs = {'side_effect': outcome} if isinstance(outcome, BaseException) else {'return_value': outcome}
            with patch.dict(sys.modules, termios=fake_termios), \
                 patch.object(sys, 'stdin', terminal), patch.object(sys, 'stdout', terminal), \
                 patch.object(uploader.shutil, 'which', return_value='/usr/bin/rz'), \
                 patch('builtins.print'), patch.object(uploader.subprocess, 'run', **kwargs) as run:
                with self.assertRaises((SystemExit, KeyboardInterrupt)):
                    uploader.receive_into(self.received)
            self.assertIn('--restricted', run.call_args.args[0])
            self.assertNotIn('--allow-remote-commands', run.call_args.args[0])
            fake_termios.tcsetattr.assert_called_once_with(17, 0, ['saved'])

    def test_invalid_batch_never_imports(self):
        def receive(directory):
            (directory / 'good.pdf').write_bytes(PDF)
            (directory / 'bad.docx').write_bytes(b'word')
        with patch.object(uploader, 'private_staging', return_value=self.staging), \
             patch.object(uploader, 'receive_into', receive), \
             patch.object(uploader, 'import_received') as importer:
            with self.assertRaises(SystemExit):
                uploader.upload()
        importer.assert_not_called()
        self.assertEqual(list(self.staging.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
