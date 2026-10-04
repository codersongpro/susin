"""사용 허가서, 이용약관, 오픈소스 고지가 서로 어긋나지 않는지 본다."""
import os
import re
import sys
import unittest
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build_notices  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


class GeneratedFilesTest(unittest.TestCase):
    def test_generated_files_are_up_to_date(self):
        """licenses/ 나 목록, 약관을 고치고 build_notices.py --apply 를 안 돌리면 여기서 걸린다."""
        self.assertEqual(build_notices.build_markdown(), read('THIRD_PARTY_NOTICES.md'))
        self.assertEqual(build_notices.build_license_page(), read('license.html'))
        self.assertEqual(build_notices.build_terms_page(), read('terms.html'))

    def test_every_requirement_has_a_notice(self):
        names = {c[0].lower() for c in build_notices.COMPONENTS}
        for line in read('requirements.txt').splitlines():
            package = re.split(r'[<>=!~ ]', line.strip(), maxsplit=1)[0].lower()
            if package:
                self.assertTrue(any(package in n for n in names),
                                f'{package} 의 오픈소스 고지가 없습니다')

    def test_every_notice_has_real_text(self):
        for name, url, _use, kind, source in build_notices.COMPONENTS:
            text = build_notices.license_text(source)
            self.assertGreater(len(text), 150, f'{name} 의 라이선스 글이 너무 짧습니다')
            self.assertTrue(url.startswith('https://'), name)
            self.assertTrue(kind, name)

    def test_pages_share_the_landing_page_look(self):
        """두 페이지의 색과 틀은 랜딩페이지에서 그대로 가져온다."""
        shared = build_notices.shared_css()
        self.assertIn('--primary: #4A53C9', shared)
        for name in ('license.html', 'terms.html'):
            self.assertIn(shared, read(name))
        self.assertNotIn('—', read('license.html'))
        self.assertNotIn('—', read('terms.html'))


class LicenseTermsTest(unittest.TestCase):
    def test_license_is_free_use_but_no_sale_and_no_modification(self):
        text = read('LICENSE')
        self.assertIn('Copyright (c) 2026 신통픽 개발자. All rights reserved.', text)
        self.assertIn('무료로 내려받아 쓸 수 있습니다', text)
        self.assertIn('가. 판매', text)
        self.assertIn('나. 수정', text)
        self.assertNotIn('MIT', text)
        self.assertNotIn('송동석', text)
        self.assertNotIn('Permission is hereby granted', text)

    def test_license_page_preserves_all_license_text_in_readable_blocks(self):
        page = build_notices.build_license_page()
        body = re.search(r'<div class="plain">(.*?)</div>', page, re.S).group(1)
        visible = unescape(re.sub(r'<[^>]+>', ' ', body))
        self.assertEqual(' '.join(read('LICENSE').split()), ' '.join(visible.split()))
        self.assertEqual(body.count('<h3>'), 6)
        self.assertEqual(body.count('<li>'), 7)
        self.assertNotRegex(body, r'\S\n +\S')

    def test_terms_say_the_same_thing_as_the_license(self):
        terms = read('terms.html')
        self.assertIn('판매와 수정은 개발자의 허락 없이 할 수 없습니다', terms)
        self.assertIn('시행일은 2026년 10월 3일', terms)
        self.assertNotIn('고의 또는 중대한 과실로 발생한 손해는 제외합니다', terms)
        for clause in ('제1조 목적', '제4조 이용자의 확인 책임', '제5조 정보 처리',
                       '제7조 책임의 한계', '제10조 문의'):
            self.assertIn(clause, terms)

    def test_landing_page_links_to_both_pages_and_says_no_sale_no_edit(self):
        page = read('index.html')
        self.assertIn('href="terms.html"', page)
        self.assertIn('href="license.html"', page)
        self.assertIn('판매와 수정에는 개발자의 사전 서면 허락이 필요합니다', page)
        self.assertIn('학성초 송충북', page)
        self.assertNotIn('학성초 송동석', page)
        self.assertNotIn('MIT', re.sub(r'data:[^"]+', '', page))

    def test_privacy_statement_matches_what_the_app_stores(self):
        """약관에 적은 저장 위치와 기록 수가 코드와 같다."""
        import app_config
        terms = read('terms.html')
        self.assertIn(f'최근 {app_config.MAX_ORG_EXTRACT_HISTORY}회', terms)
        self.assertEqual(os.path.basename(app_config.APP_DATA_DIR), 'SintongPick')
        self.assertIn('%LOCALAPPDATA%', terms)


class BundlingTest(unittest.TestCase):
    def test_notices_ship_with_the_exe(self):
        spec = read('sintongpick.spec')
        for item in ("'LICENSE'", "'THIRD_PARTY_NOTICES.md'", "'licenses'"):
            self.assertIn(item, spec)

    def test_gpl_part_is_not_bundled(self):
        """MouseInfo(GPL-3.0) 는 신통픽 사용 허가서와 맞지 않으므로 exe 에서 뺀다."""
        self.assertIn("excludes=['mouseinfo']", read('sintongpick.spec'))
        self.assertIn('mouseinfo', read('.github', 'workflows', 'release.yml').lower())
        self.assertNotIn('mouseinfo', read('THIRD_PARTY_NOTICES.md').lower())

    def test_site_files_are_deployed(self):
        ignore = read('.vercelignore')
        for name in ('index.html', 'terms.html', 'license.html', 'vercel.json'):
            self.assertIn('!' + name, ignore)


if __name__ == '__main__':
    unittest.main()
