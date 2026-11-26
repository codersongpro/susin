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
        self.assertIn('구성원은 명단에서 직접 확인해 주세요', message)

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


class MessengerCompareTest(unittest.TestCase):
    """소통메신저 [선택된 사용자] 와 소통픽 명단 맞춰 보기."""

    ROWS = ['박소통 [교사(초등)] [1학년] 안전/통학버스, 도서',
            '정수신 [부장교사] [전담] 교무, 생활교육(202,310)',
            '김충북 [교사(초등)] [3학년] 연구학력 (303)']

    def item(self, org, name):
        return {'org': org, 'name': name}

    def snapshot(self, rows=None, complete=True):
        return reconcile.MessengerSnapshot(self.ROWS if rows is None else rows, complete)

    def test_name_is_read_from_a_row(self):
        self.assertEqual(reconcile.person_name_from_row(self.ROWS[0]), '박소통')
        self.assertEqual(reconcile.person_name_from_row('정수신 (부장교사)'), '정수신')
        self.assertEqual(reconcile.person_name_from_row('송동석'), '송동석')
        self.assertIsNone(reconcile.person_name_from_row('123 abc'))

    def test_who_got_in_and_who_did_not(self):
        items = [self.item('학성초등학교', '박소통'), self.item('학성초등학교', '정수신'),
                 self.item('학성초등학교', '최신통')]
        result = reconcile.compare_with_messenger(items, self.snapshot())
        self.assertEqual(result.inside, [])
        self.assertEqual([i['name'] for i in result.name_only], ['박소통', '정수신'])
        self.assertEqual([i['name'] for i in result.missing], ['최신통'])
        self.assertEqual(len(result.extra), 1, '김충북는 소통메신저에만 있다')
        self.assertEqual(result.rows, 3)

    def test_same_name_in_two_schools_is_not_guessed(self):
        """소통메신저에는 학교가 안 나온다. 김충북가 한 명뿐이면 어느 학교 사람인지 모른다."""
        items = [self.item('가초등학교', '김충북'), self.item('나초등학교', '김충북')]
        result = reconcile.compare_with_messenger(items, self.snapshot())
        self.assertEqual(result.inside, [])
        self.assertEqual(result.missing, [])
        self.assertEqual(result.name_only, items)

    def test_name_only_text_tells_who_needs_identity_confirmation(self):
        items = [self.item('가초등학교', '김충북'), self.item('나초등학교', '김충북'),
                 self.item('학성초등학교', '박소통')]
        result = reconcile.compare_with_messenger(items, self.snapshot())
        text = reconcile.compare_text(result)
        self.assertIn('[이름 일치, 본인 확인 필요]  3명', text)
        self.assertIn('가초등학교 김충북', text)
        self.assertIn('나초등학교 김충북', text)

    def test_equal_same_name_counts_do_not_confirm_identity(self):
        rows = self.ROWS + ['김충북 [교사(초등)] [5학년]']
        items = [self.item('가초등학교', '김충북'), self.item('나초등학교', '김충북')]
        result = reconcile.compare_with_messenger(items, self.snapshot(rows))
        self.assertEqual(result.inside, [])
        self.assertEqual(result.name_only, items)
        self.assertNotIn('등록 확인', reconcile.compare_text(result))

    def test_structured_identity_confirms_a_registered_person(self):
        by_org = self.item('학성초등학교', '박소통')
        by_id = {**self.item('한천초등학교', '김충북'), 'user_id': 'mb353'}
        rows = [reconcile.MessengerRow(self.ROWS[0], org='학성초등학교'),
                reconcile.MessengerRow(self.ROWS[2], org='가초등학교', user_id='mb353')]
        result = reconcile.compare_with_messenger([by_org, by_id], self.snapshot(rows))
        self.assertEqual(result.inside, [by_org, by_id])
        self.assertEqual(result.name_only, [])

    def test_status_text_matching_the_school_does_not_confirm_identity(self):
        item = self.item('학성초등학교', '박소통')
        rows = ['박소통 [교사(초등)] 학성초등학교']
        result = reconcile.compare_with_messenger([item], self.snapshot(rows))
        self.assertEqual(result.inside, [])
        self.assertEqual(result.name_only, [item])

    def test_one_school_match_cannot_confirm_two_people_with_distinct_ids(self):
        first = {**self.item('학성초등학교', '박소통'), 'user_id': 'one'}
        second = {**self.item('학성초등학교', '박소통'), 'user_id': 'two'}
        rows = [reconcile.MessengerRow(self.ROWS[0], org='학성초등학교')]
        result = reconcile.compare_with_messenger([first, second], self.snapshot(rows))
        self.assertEqual(result.inside, [])
        self.assertEqual(result.name_only, [first, second])

    def test_partial_snapshot_defers_unobserved_people(self):
        seen = self.item('학성초등학교', '박소통')
        not_seen = self.item('학성초등학교', '최신통')
        result = reconcile.compare_with_messenger(
            [seen, not_seen], self.snapshot([self.ROWS[0]], complete=False))
        self.assertEqual(result.name_only, [seen])
        self.assertEqual(result.missing, [])
        self.assertEqual(result.pending, [not_seen])

    def test_unreadable_row_prevents_an_absence_confirmation(self):
        item = self.item('학성초등학교', '최신통')
        result = reconcile.compare_with_messenger([item], self.snapshot(['']))
        self.assertFalse(result.complete)
        self.assertEqual(result.missing, [])
        self.assertEqual(result.pending, [item])

    def test_items_without_a_name_are_reported(self):
        result = reconcile.compare_with_messenger([{'org': '학성초등학교'}], self.snapshot())
        self.assertEqual(len(result.no_name), 1)

    def test_text_lists_missing_first(self):
        items = [self.item('학성초등학교', '박소통'), self.item('학성초등학교', '최신통')]
        text = reconcile.compare_text(reconcile.compare_with_messenger(items, self.snapshot()))
        self.assertTrue(text.startswith('[소통메신저에 없음]  1명'), text)
        self.assertIn('학성초등학교 최신통', text)
        self.assertIn('[이름 일치, 본인 확인 필요]  1명', text)


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


class StatusMessageTest(unittest.TestCase):
    """이름 옆의 글은 사람이 정한 상태 메시지다 (업무, 학생 수, 맡은 반, 내선, 없을 수도 있다)."""

    def test_name_is_the_one_before_the_role(self):
        for row in ('권성희 [교사(유치원)]',
                    '권성희 [교사(유치원)] 해님반(208)',
                    '권성희 [교사(유치원)] 6학년 [2반]',
                    '권성희 [교사(초등)] 담임 [전담] 학생 25명',
                    '프로필 권성희 [교사(초등)] 업무: 방과후(2)'):
            self.assertEqual(reconcile.person_name_from_row(row), '권성희', row)

    def test_a_status_with_brackets_never_becomes_the_name(self):
        self.assertEqual(reconcile.person_name_from_row('권성희 해님반(208)'), '권성희')
        self.assertEqual(reconcile.person_name_from_row('권성희 [교사] 해님반(208)'), '권성희')
        self.assertIsNone(reconcile.person_name_from_row('208 (3) [1]'))

    def test_row_label_shortens_the_status_and_survives_a_missing_one(self):
        self.assertEqual(reconcile.person_row_label('권성희 [교사(유치원)]'), '권성희 [교사(유치원)]')
        label = reconcile.person_row_label('권성희 [교사(유치원)] 해님반(208)')
        self.assertEqual(label, '권성희 [교사(유치원)]  (해님반(208))')
        long = reconcile.person_row_label('권성희 [교사] ' + '가' * 60)
        self.assertTrue(long.endswith('…)'))
        self.assertLess(len(long), 60)

    def test_extra_people_are_listed_with_name_role_and_a_short_status(self):
        result = reconcile.compare_with_messenger([], reconcile.MessengerSnapshot(
            ['권성희 [교사(유치원)] 해님반(208)', '강명희 [교사(보건)]'], complete=True))
        text = reconcile.compare_text(result)
        self.assertIn('권성희 [교사(유치원)]  (해님반(208))', text)
        self.assertIn('강명희 [교사(보건)]', text)


if __name__ == '__main__':
    unittest.main()
