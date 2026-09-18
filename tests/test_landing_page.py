import json
import os
import unittest


class LandingPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'index.html'), encoding='utf-8') as source:
            cls.html = source.read()
        with open(os.path.join(root, 'vercel.json'), encoding='utf-8') as source:
            cls.vercel = json.load(source)

    def test_download_buttons_point_to_the_latest_release_file(self):
        direct_url = (
            'https://github.com/codersongpro/susin/releases/latest/download/'
            'sintongpick.exe'
        )
        self.assertGreaterEqual(self.html.count(direct_url), 2)
        self.assertNotIn('sintongpick-windows.zip', self.html)
        download_redirect = next(
            item for item in self.vercel['redirects'] if item['source'] == '/download'
        )
        self.assertEqual(download_redirect['destination'], direct_url)

    def test_each_product_has_its_own_guide_and_video(self):
        self.assertIn('소통픽 사용법', self.html)
        self.assertIn('수신픽 사용법', self.html)
        self.assertIn('https://youtu.be/shZnB5NRN5g', self.html)
        self.assertIn('https://youtu.be/IcFX3UKdMEw', self.html)

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
