"""개발용 실행.bat 이 부르는 부품 확인."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

import ensure_packages  # noqa: E402


class EnsurePackagesTest(unittest.TestCase):
    def test_reads_names_without_versions_or_build_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'requirements.txt')
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write('pyautogui>=0.9.54\n# 주석\n\npywin32>=306\n'
                         'comtypes>=1.2  # 화면 읽어 주기\npyinstaller>=6.0.0\n')
            self.assertEqual(ensure_packages.requirements(path),
                             ['pyautogui', 'pywin32', 'comtypes'])

    def test_real_requirements_include_comtypes(self):
        self.assertIn('comtypes', ensure_packages.requirements())
        self.assertNotIn('pyinstaller', ensure_packages.requirements())

    def test_pywin32_is_checked_by_its_import_name(self):
        seen = []

        def find_spec(name):
            seen.append(name)
            return object() if name == 'win32gui' else None

        with patch.object(ensure_packages.importlib.util, 'find_spec', find_spec):
            self.assertEqual(ensure_packages.missing(['pywin32', 'comtypes']), ['comtypes'])
        self.assertEqual(seen, ['win32gui', 'comtypes'])

    def test_installs_only_what_is_missing(self):
        with patch.object(ensure_packages, 'missing', return_value=['comtypes']), \
                patch.object(ensure_packages.subprocess, 'call', return_value=0) as call:
            self.assertEqual(ensure_packages.main(), 0)
        cmd = call.call_args.args[0]
        self.assertEqual(cmd[1:4], ['-m', 'pip', 'install'])
        self.assertEqual(cmd[-1], 'comtypes')

    def test_does_nothing_when_all_present(self):
        with patch.object(ensure_packages, 'missing', return_value=[]), \
                patch.object(ensure_packages.subprocess, 'call') as call:
            self.assertEqual(ensure_packages.main(), 0)
        call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
