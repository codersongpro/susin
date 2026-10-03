import os
import unittest
from unittest import mock

import fonts
import theme


class FontsTest(unittest.TestCase):
    def test_bundled_files_and_license_are_present(self):
        for path in fonts.font_paths():
            self.assertTrue(os.path.exists(path), f'{path} 이 없습니다')
        self.assertTrue(os.path.exists(os.path.join(fonts.font_dir(), 'LICENSE.txt')),
                        '글꼴 라이선스 파일이 같이 있어야 합니다')

    def test_app_uses_pretendard_when_the_files_are_there(self):
        self.assertEqual(theme.FONT_FAMILY, fonts.FAMILY)

    def test_falls_back_to_malgun_gothic_without_the_files(self):
        with mock.patch.object(fonts, 'font_paths', return_value=['/없는/파일.ttf']):
            self.assertEqual(fonts.family(), fonts.FALLBACK)

    def test_no_hardcoded_font_names_left_in_the_app(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ('main.py', 'ui_kit.py'):
            with open(os.path.join(root, name), encoding='utf-8') as source:
                self.assertNotIn("'맑은 고딕'", source.read(), name)

    def test_landing_page_uses_pretendard(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'index.html'), encoding='utf-8') as source:
            html = source.read()
        self.assertIn('pretendard', html.lower())
        self.assertNotIn('Noto Sans', html)


if __name__ == '__main__':
    unittest.main()
