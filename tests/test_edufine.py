import os
import tempfile
import unittest

import edufine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(HERE, 'data', 'sample_수신그룹.xlsx')
TEMPLATE = os.path.join(HERE, 'assets', '수신그룹_양식.xlsx')


def codes_from_sample():
    harvested = edufine.read_group_workbook(SAMPLE)
    codes, _, _ = edufine.merge_codes(edufine.empty_codes(), harvested)
    return codes


class HarvestTest(unittest.TestCase):
    def test_reads_real_codes_and_owner(self):
        h = edufine.read_group_workbook(SAMPLE)
        self.assertEqual(h['등록교육청코드'], 'M100000098')
        self.assertEqual(h['사용자ID'], 'dungst')
        self.assertEqual(h['기관']['충청북도진천교육지원청 학성초등학교'], 'M100000795')

    def test_blank_template_yields_nothing(self):
        # 안내용 예시 행이 코드로 섞여 들어가면 안 된다
        self.assertEqual(edufine.read_group_workbook(TEMPLATE)['기관'], {})

    def test_merge_reports_added_and_changed(self):
        codes, added, changed = edufine.merge_codes(
            edufine.empty_codes(), edufine.read_group_workbook(SAMPLE))
        self.assertEqual(added, 4)
        self.assertEqual(changed, [])

        moved = {'기관': {'충청북도진천교육지원청 학성초등학교': 'M100009999'}}
        _, added2, changed2 = edufine.merge_codes(codes, moved)
        self.assertEqual(added2, 0)
        self.assertEqual(changed2,
                         [('충청북도진천교육지원청 학성초등학교', 'M100000795', 'M100009999')])


class LookupTest(unittest.TestCase):
    def setUp(self):
        self.codes = codes_from_sample()

    def test_lookup_by_alias_and_full_name(self):
        for q in ('학성초', '학성초등학교', '충청북도진천교육지원청 학성초등학교'):
            entry, ambiguous = edufine.lookup_code(self.codes, q)
            self.assertEqual(entry['code'], 'M100000795', q)
            self.assertEqual(ambiguous, [])

    def test_unknown_returns_nothing(self):
        self.assertEqual(edufine.lookup_code(self.codes, '없는기관'), (None, []))

    def test_duplicate_short_name_is_never_guessed(self):
        # 부서명은 기관마다 겹친다. 하나를 임의로 고르면 공문이 엉뚱한 곳으로 간다.
        codes = {'기관': {
            '충청북도청주교육지원청 행정지원과': 'M100000001',
            '충청북도충주교육지원청 행정지원과': 'M100000002',
        }}
        entry, ambiguous = edufine.lookup_code(codes, '행정지원과')
        self.assertIsNone(entry)
        self.assertEqual(len(ambiguous), 2)

        # 전체경로로 지목하면 정확히 찾는다
        entry, _ = edufine.lookup_code(codes, '충청북도충주교육지원청 행정지원과')
        self.assertEqual(entry['code'], 'M100000002')


class SplitTest(unittest.TestCase):
    def test_missing_rows_are_reported_with_reason(self):
        codes = codes_from_sample()
        parsed = [
            {'name': '학성초등학교', 'grade': 'exact'},
            {'name': '백곡초등학교', 'grade': 'exact'},   # 코드 사전에 없음
        ]
        ready, missing = edufine.split_by_code(parsed, codes)
        self.assertEqual([r['name'] for r in ready], ['학성초등학교'])
        self.assertEqual([r['name'] for r in missing], ['백곡초등학교'])
        self.assertEqual(missing[0]['reason'], '코드 없음')


class BuildTest(unittest.TestCase):
    meta = {'그룹명': '진천 시범', '그룹기호': '', '등록교육청코드': 'M100000098',
            '사용자ID': 'dungst', '사용자명': '송동석'}

    def test_round_trip(self):
        codes = codes_from_sample()
        rows, _ = edufine.split_by_code(
            [{'name': '학성초등학교'}, {'name': '한천초등학교'}], codes)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'out.xlsx')
            edufine.build_workbook(rows, self.meta, out)

            import openpyxl
            wb = openpyxl.load_workbook(out)
            self.assertIn(edufine.SHEET_NAME, wb.sheetnames)
            ws = wb[edufine.SHEET_NAME]
            self.assertEqual([c.value for c in ws[1]], edufine.HEADERS)
            self.assertEqual(ws.max_row, 3)

            second = [c.value for c in ws[2]]
            self.assertEqual(second[0], '진천 시범')
            self.assertEqual(second[1], ' ')          # 기호가 비면 공백 한 칸
            self.assertEqual(second[2], 'M100000098')
            self.assertEqual(second[3], edufine.KIND_INTERNAL)
            self.assertEqual(second[4], 'M100000795')
            self.assertEqual(second[5], '충청북도진천교육지원청 학성초등학교')
            self.assertEqual(second[6], edufine.TYPE_DOCUMENT)
            self.assertEqual(second[7:], ['dungst', '송동석'])

    def test_generated_file_harvests_back(self):
        # 만든 파일을 다시 읽어 같은 코드가 나와야 한다
        codes = codes_from_sample()
        rows, _ = edufine.split_by_code([{'name': '학성초등학교'}], codes)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'out.xlsx')
            edufine.build_workbook(rows, self.meta, out)
            back = edufine.read_group_workbook(out)
            self.assertEqual(back['기관']['충청북도진천교육지원청 학성초등학교'],
                             'M100000795')

    def test_refuses_empty_or_incomplete(self):
        with self.assertRaises(ValueError):
            edufine.build_workbook([], self.meta, 'x.xlsx')
        with self.assertRaises(ValueError):
            edufine.build_workbook(
                [{'name': 'a', 'code': 'M100000001'}],
                dict(self.meta, 사용자ID=''), 'x.xlsx')

    def test_default_output_name(self):
        import datetime
        self.assertEqual(
            edufine.default_output_name('진천/시범', datetime.date(2026, 9, 17)),
            '수신그룹_진천시범_20260917.xlsx')


if __name__ == '__main__':
    unittest.main()
