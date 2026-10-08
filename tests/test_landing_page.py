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

    def test_app_screenshots_match_the_files_on_disk(self):
        """앱 화면 캡처(assets/landing)도 같은 방식으로 박혀 있어야 한다."""
        names = re.findall(r'data-shot="([^"]+)"', self.html)
        self.assertGreaterEqual(len(names), 8, '앱 화면 캡처가 랜딩페이지에서 빠졌습니다')
        for name in dict.fromkeys(names):
            path = os.path.join(self.root, 'assets', 'landing', name)
            self.assertTrue(os.path.exists(path), f'assets/landing/{name} 이 없습니다')
            with open(path, 'rb') as image:
                encoded = base64.b64encode(image.read()).decode('ascii')
            self.assertIn(
                f'data:image/webp;base64,{encoded}', self.html,
                f'{name} 이 파일과 다릅니다. '
                'python3 tools/embed_guide_images.py --apply 를 돌리세요',
            )

    def test_page_has_no_dashes_or_arrow_chains(self):
        """문체 규칙: 제목과 문장에 대시나 화살표를 쓰지 않는다."""
        text = re.sub(r'data:[^"]+', '', self.html)
        text = re.sub(r'<style.*?</style>|<script.*?</script>', '', text, flags=re.S)
        self.assertNotIn('\u2014', text)
        self.assertNotIn('\u2192', text)

    def test_old_code_import_instructions_are_removed(self):
        self.assertNotIn('기관코드 가져오기', self.html)
        self.assertIn('충청북도교육청으로 자동 적용', self.html)
        self.assertIn('그룹기호는 선택 사항', self.html)


if __name__ == '__main__':
    unittest.main()


class LandingVideoTest(unittest.TestCase):
    """사용 방법 영상이 페이지에 박혀 있고, 파일이 있고, 배포에서 빠지지 않는다."""

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def read(self, *parts):
        with open(os.path.join(self.root, *parts), encoding='utf-8') as source:
            return source.read()

    def test_both_videos_and_posters_exist_and_are_small_enough(self):
        html = self.read('index.html')
        for name in ('susin', 'sotong', 'intro'):
            for ext in ('mp4', 'jpg'):
                path = f'assets/video/{name}.{ext}'
                self.assertIn(path, html)
                full = os.path.join(self.root, path)
                self.assertTrue(os.path.exists(full), path)
                # 학교 망에서도 바로 열리게 한 편에 6MB 를 넘기지 않는다
                self.assertLess(os.path.getsize(full), 6 * 1024 * 1024, path)

    def test_videos_load_only_when_played(self):
        """사용 방법 영상 두 편은 누를 때 받는다. 첫 화면 소개 영상 하나만 미리 받는다."""
        html = self.read('index.html')
        self.assertEqual(html.count('<video'), 3)
        self.assertEqual(html.count('preload="none"'), 2)
        self.assertEqual(html.count('preload="auto"'), 1)

    def test_intro_video_opens_the_page_quietly(self):
        """소개 영상은 페이지 맨 앞에서 소리 없이 돌고, 소리는 사람이 켠다."""
        html = self.read('index.html')
        intro = html.index('id="intro"')
        self.assertLess(intro, html.index('<nav'), '소개 영상이 위쪽 바보다 앞에 있어야 합니다')
        tag = html[html.index('<video id="intro-video"'):]
        tag = tag[:tag.index('>')]
        for attr in ('muted', 'playsinline', 'poster="assets/video/intro.jpg"'):
            self.assertIn(attr, tag)
        self.assertNotIn('autoplay', tag, '움직임 줄이기를 켠 사람을 위해 재생은 스크립트가 정한다')
        self.assertIn('id="intro-sound"', html)
        self.assertIn('prefers-reduced-motion: reduce)\').matches', html)
        # 영상은 화면에 붙어 있고, 본문(위쪽 바부터 끝까지)이 그 위로 덮으며 올라온다
        self.assertIn('.intro-stage { position: fixed;', html)
        sheet = html.index('<div class="sheet">')
        self.assertLess(intro, sheet)
        self.assertLess(sheet, html.index('<nav'))
        # 내려가는 단추가 이어 붙는 페이지 본문으로 간다
        self.assertIn('class="intro-down" href="#top"', html)
        self.assertIn('<main id="top">', html)

    def test_intro_cues_are_valid_and_inside_the_video(self):
        """그림(intro.html)과 소리(intro_sound.py)가 함께 읽는 박자표."""
        text = self.read('tools', 'video', 'intro_cues.js')
        body = text[text.index('INTRO_CUES'):]
        cues = json.loads(body[body.index('{'):body.rindex('}') + 1])
        total = cues['total']
        times = []
        for value in cues.values():
            if isinstance(value, list):
                times.extend(value)
            elif isinstance(value, (int, float)) and value is not total and value != cues['bpm']:
                times.append(value)
        self.assertTrue(times)
        for at in times:
            self.assertGreaterEqual(at, 0)
            self.assertLess(at, total)
        # 끼어드는 장면(타이핑 수, 순서 꼬임)의 시각은 그 장면 안에 있어야 한다
        insert = cues['insert']
        self.assertLess(insert['at'], total)
        for value in insert['cues'].values():
            for at in (value if isinstance(value, list) else [value]):
                self.assertGreaterEqual(at, 0)
                self.assertLess(at, insert['dur'])

    def test_video_folder_is_deployed_but_other_assets_are_not(self):
        ignore = self.read('.vercelignore').splitlines()
        self.assertIn('!assets/video/', ignore)
        self.assertIn('!assets/video/*', ignore)
        self.assertIn('assets/*', ignore)
        self.assertLess(ignore.index('assets/*'), ignore.index('!assets/video/'))

    def test_video_scenes_follow_the_writing_rules(self):
        for name in ('scenes.html', 'intro.html'):
            scenes = self.read('tools', 'video', name)
            self.assertNotIn('\u2014', scenes, name)
            self.assertNotIn('\u2192', scenes, name)
            self.assertNotIn('지금 바로', scenes, name)
