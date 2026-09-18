import os
import unittest


class LandingPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'index.html'), encoding='utf-8') as source:
            cls.html = source.read()

    def test_download_buttons_point_to_the_latest_release_file(self):
        direct_url = (
            'https://github.com/codersongpro/susin/releases/latest/download/'
            'sintongpick-windows.zip'
        )
        self.assertGreaterEqual(self.html.count(direct_url), 2)

    def test_bottom_cta_and_visible_repository_address_are_removed(self):
        self.assertNotIn('한 번 써 보세요', self.html)
        self.assertNotIn('href="https://github.com/codersongpro/susin"', self.html)
        self.assertNotIn('>github.com/codersongpro/susin<', self.html)

    def test_old_code_import_instructions_are_removed(self):
        self.assertNotIn('기관코드 가져오기', self.html)
        self.assertIn('충청북도교육청으로 자동 적용', self.html)
        self.assertIn('그룹기호는 선택 사항', self.html)


if __name__ == '__main__':
    unittest.main()
