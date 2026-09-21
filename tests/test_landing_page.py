import base64
import json
import os
import re
import unittest


class LandingPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(cls.root, 'index.html'), encoding='utf-8') as source:
            cls.html = source.read()
        with open(os.path.join(cls.root, 'vercel.json'), encoding='utf-8') as source:
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

    def test_each_tool_gets_its_own_how_to_block(self):
        """탭 하나에 두 도구를 섞어 두면 어느 쪽 단계인지 헷갈린다."""
        self.assertEqual(self.html.count('class="how-group"'), 2)
        self.assertNotIn('① 수신픽 ·', self.html)
        self.assertNotIn('④ 소통픽 ·', self.html)

    def test_guide_pictures_match_the_files_on_disk(self):
        """랜딩페이지는 파일 한 장으로 배포하므로 그림을 data URI 로 박아 둔다.

        그림을 다시 찍고 index.html 을 안 고치면 옛 그림이 조용히 남는다.
        어긋나면 tools/embed_guide_images.py --apply 로 맞춘다.
        """
        names = re.findall(r'data-guide="([^"]+)"', self.html)
        self.assertGreaterEqual(len(names), 10, '안내 그림이 랜딩페이지에서 빠졌습니다')

        for name in ('edufine_settings.png', 'edufine_group_menu.png',
                     'edufine_bulk_upload.png', 'edufine_browse.png'):
            self.assertIn(name, names, f'수신픽 안내 그림 {name} 이 랜딩페이지에 없습니다')

        for name in dict.fromkeys(names):
            path = os.path.join(self.root, 'assets', 'guide', name)
            self.assertTrue(os.path.exists(path), f'assets/guide/{name} 이 없습니다')
            with open(path, 'rb') as image:
                encoded = base64.b64encode(image.read()).decode('ascii')
            self.assertIn(
                f'data:image/png;base64,{encoded}', self.html,
                f'{name} 이 파일과 다릅니다. '
                'python3 tools/embed_guide_images.py --apply 를 돌리세요',
            )

    def test_old_code_import_instructions_are_removed(self):
        self.assertNotIn('기관코드 가져오기', self.html)
        self.assertIn('충청북도교육청으로 자동 적용', self.html)
        self.assertIn('그룹기호는 선택 사항', self.html)


if __name__ == '__main__':
    unittest.main()
