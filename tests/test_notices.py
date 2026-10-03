"""라이선스, 이용약관, 오픈소스 고지가 서로 어긋나지 않는지 본다."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build_notices  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


class NoticesTest(unittest.TestCase):
    def test_generated_notices_are_up_to_date(self):
        """licenses/ 나 목록을 고치고 build_notices.py --apply 를 안 돌리면 여기서 걸린다."""
        page = read('index.html')
        self.assertEqual(build_notices.apply_html(page), page)
        self.assertEqual(build_notices.build_markdown(), read('THIRD_PARTY_NOTICES.md'))

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

    def test_app_license_is_mit_and_matches_the_page(self):
        text = read('LICENSE')
        self.assertTrue(text.startswith('MIT License'))
        self.assertIn('Copyright (c) 2026 송동석 (Dustin)', text)
        body = text.split('\n\n이 라이선스는')[0].strip()
        self.assertIn(body, read('index.html'))

    def test_page_has_terms_license_and_notice_sections(self):
        page = read('index.html')
        for anchor in ('id="terms"', 'id="license"', 'id="oss"'):
            self.assertIn(anchor, page)
        self.assertIn('시행일', page)
        for clause in ('제1조', '제5조 정보 처리', '제7조 책임의 한계', '제10조 문의'):
            self.assertIn(clause, page)

    def test_gpl_part_is_disclosed_with_full_text_and_source(self):
        notice = read('THIRD_PARTY_NOTICES.md')
        self.assertIn('MouseInfo', notice)
        self.assertIn('https://github.com/asweigart/mouseinfo', notice)
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'licenses', 'MouseInfo-GPL-3.0-full.txt')))

    def test_notices_ship_with_the_exe(self):
        spec = read('sintongpick.spec')
        for item in ("'LICENSE'", "'THIRD_PARTY_NOTICES.md'", "'licenses'"):
            self.assertIn(item, spec)

    def test_privacy_statement_matches_what_the_app_stores(self):
        """약관에 적은 저장 위치와 기록 수가 코드와 같다."""
        import app_config
        page = read('index.html')
        self.assertIn(f'최근 {app_config.MAX_ORG_EXTRACT_HISTORY}회', page)
        self.assertEqual(os.path.basename(app_config.APP_DATA_DIR), 'SintongPick')
        self.assertIn('%LOCALAPPDATA%', page)


if __name__ == '__main__':
    unittest.main()
