"""추출한 명단과 실제로 들어간 명단 대조."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import edufine  # noqa: E402
import reconcile  # noqa: E402
from automation import FAIL_DUPLICATE, FAIL_NO_USER  # noqa: E402


class MessengerTallyTest(unittest.TestCase):
    def test_counts_added_already_and_missing(self):
        items = [
            {'org': '가초', 'name': '갑', 'added': True},
            {'org': '나초', 'name': '을', 'failure_reason': FAIL_DUPLICATE},
            {'org': '다초', 'name': '병', 'failure_reason': FAIL_NO_USER},
            {'org': '라초', 'name': '정', 'added': True},
        ]
        tally = reconcile.messenger_tally(items)
        self.assertEqual(tally.total, 4)
        self.assertEqual(len(tally.placed), 2)
        self.assertEqual(len(tally.already), 1)
        self.assertEqual(tally.reflected, 3, '원래 있던 사람도 들어 있는 것이다')
        self.assertEqual(tally.short, 1)
        self.assertEqual(tally.missing[0][1], FAIL_NO_USER)

    def test_items_without_a_result_are_not_swallowed(self):
        """중지하면 뒤쪽 사람은 결과가 없다. 담긴 것처럼 넘어가면 안 된다."""
        items = [{'org': '가초', 'name': '갑', 'added': True},
                 {'org': '나초', 'name': '을'},
                 {'org': '다초', 'name': '병'}]
        stopped = reconcile.messenger_tally(items, stopped=True)
        self.assertEqual(stopped.short, 2)
        self.assertEqual({r for _i, r in stopped.missing}, {reconcile.NOT_TRIED})

        finished = reconcile.messenger_tally(items, stopped=False)
        self.assertEqual({r for _i, r in finished.missing}, {reconcile.NOT_CHECKED})

    def test_total_always_adds_up(self):
        items = [{'added': True}, {'failure_reason': FAIL_DUPLICATE},
                 {'failure_reason': '자동화 오류'}, {}]
        tally = reconcile.messenger_tally(items)
        self.assertEqual(len(tally.placed) + len(tally.already) + tally.short,
                         tally.total)


class EdufineTallyTest(unittest.TestCase):
    CODES = {'기관': {
        '충청북도진천교육지원청 학성초등학교': 'M100000001',
        '충청북도진천교육지원청 백곡초등학교': 'M100000002',
        '충청북도교육청 행정과': 'M100000003',
        '충청북도청주교육지원청 행정과': 'M100000004',
    }}

    def item(self, org, grade='exact'):
        return {'raw': org, 'org': org, 'search': org, 'grade': grade}

    def test_every_extracted_org_gets_a_place_or_a_reason(self):
        items = [
            self.item('학성초등학교'),
            self.item('백곡초등학교'),
            self.item('없는초등학교'),
            self.item('행정과'),                       # 두 곳에 있다
            self.item('삼보초', grade='fuzzy'),        # 사람이 골라야 한다
        ]
        written = ['M100000001', 'M100000002']
        tally = reconcile.edufine_tally(items, self.CODES, written)
        self.assertEqual(tally.total, 5)
        self.assertEqual([i['org'] for i in tally.placed],
                         ['학성초등학교', '백곡초등학교'])
        reasons = {i['org']: r for i, r in tally.missing}
        self.assertEqual(reasons['없는초등학교'], reconcile.NO_CODE)
        self.assertEqual(reasons['행정과'], reconcile.AMBIGUOUS)
        self.assertEqual(reasons['삼보초'], reconcile.UNCONFIRMED)
        self.assertEqual(len(tally.placed) + tally.short, tally.total)

    def test_org_missing_from_the_file_is_reported(self):
        """만들려던 목록에 있어도 파일에 없으면 들어간 것이 아니다."""
        items = [self.item('학성초등학교'), self.item('백곡초등학교')]
        tally = reconcile.edufine_tally(items, self.CODES, ['M100000001'])
        self.assertEqual(len(tally.placed), 1)
        self.assertEqual(tally.missing[0][1], reconcile.NOT_WRITTEN)

    def test_same_org_twice_needs_two_rows(self):
        items = [self.item('학성초등학교'), self.item('학성초등학교')]
        one_row = reconcile.edufine_tally(items, self.CODES, ['M100000001'])
        self.assertEqual(one_row.short, 1)
        two_rows = reconcile.edufine_tally(items, self.CODES,
                                           ['M100000001', 'M100000001'])
        self.assertEqual(two_rows.short, 0)

    def test_rows_that_are_not_in_the_list_are_counted(self):
        tally = reconcile.edufine_tally([self.item('학성초등학교')], self.CODES,
                                        ['M100000001', 'M100000002'])
        self.assertEqual(tally.extra, 1)
        self.assertIn('명단에 없는 줄 1개', reconcile.summary_line(tally, '곳'))


class CompareCountTest(unittest.TestCase):
    def compare(self, expected, shown):
        return reconcile.compare_count(expected, shown, '소통메신저 [선택된 사용자]',
                                       '명', '사람')

    def test_match(self):
        kind, message = self.compare(45, 45)
        self.assertEqual(kind, 'match')
        self.assertIn('빠진 사람이 없습니다', message)

    def test_short_says_how_many(self):
        kind, message = self.compare(45, 42)
        self.assertEqual(kind, 'short')
        self.assertIn('3명이 모자랍니다', message)
        self.assertIn('[들어간 명단 복사]', message)

    def test_over(self):
        kind, message = self.compare(45, 47)
        self.assertEqual(kind, 'over')
        self.assertIn('2명이 더 많습니다', message)


class TextTest(unittest.TestCase):
    def test_summary_line(self):
        tally = reconcile.messenger_tally([
            {'added': True}, {'added': True},
            {'failure_reason': FAIL_DUPLICATE},
            {'failure_reason': FAIL_NO_USER},
        ])
        line = reconcile.summary_line(tally, '명')
        self.assertEqual(
            line, '추출 4명  ·  들어감 3명  ·  (원래 있던 1명 포함)  ·  빠짐 1명')

    def test_missing_text_groups_by_reason(self):
        tally = reconcile.messenger_tally([
            {'org': '가초', 'name': '갑', 'failure_reason': FAIL_NO_USER},
            {'org': '나초', 'name': '을', 'failure_reason': FAIL_NO_USER},
            {'org': '다초', 'name': '병'},
        ], stopped=True)
        text = reconcile.missing_text(tally, '명')
        self.assertTrue(text.startswith(f'[{FAIL_NO_USER}]  2명'), text)
        self.assertIn('가초 갑', text)
        self.assertIn(f'[{reconcile.NOT_TRIED}]  1명', text)

    def test_placed_text_marks_people_who_were_already_there(self):
        tally = reconcile.messenger_tally([
            {'org': '가초', 'name': '갑', 'added': True},
            {'org': '나초', 'name': '을', 'failure_reason': FAIL_DUPLICATE},
        ])
        self.assertEqual(reconcile.placed_text(tally), '가초 갑\n나초 을  (원래 있던)')


class ReadWrittenCodesTest(unittest.TestCase):
    def test_reads_every_row_even_when_the_same_org_repeats(self):
        rows = [
            {'name': '학성초등학교', 'code': 'M100000001',
             'fullname': '충청북도진천교육지원청 학성초등학교'},
            {'name': '학성초등학교', 'code': 'M100000001',
             'fullname': '충청북도진천교육지원청 학성초등학교'},
            {'name': '백곡초등학교', 'code': 'M100000002',
             'fullname': '충청북도진천교육지원청 백곡초등학교'},
        ]
        meta = {'그룹명': '시험', '등록교육청코드': 'M100000098',
                '사용자ID': 'test', '사용자명': '홍길동'}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'out.xlsx')
            edufine.build_workbook(rows, meta, path)
            self.assertEqual(edufine.read_written_codes(path),
                             ['M100000001', 'M100000001', 'M100000002'])


if __name__ == '__main__':
    unittest.main()
