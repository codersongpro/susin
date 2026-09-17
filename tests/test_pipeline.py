"""명단 붙여넣기 → 확정 → 일괄등록 엑셀까지, 실제로 쓰는 경로 전체."""

import os
import tempfile
import unittest

import edufine
from sotong_parser import AUTO_GRADES, parse_orgs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(HERE, 'data', 'sample_수신그룹.xlsx')

META = {'그룹명': '진천 초등', '그룹기호': '', '등록교육청코드': 'M100000098',
        '사용자ID': 'dungst', '사용자명': '송동석'}


def confirmed(rows):
    """UI 가 하는 일과 같다 — 추정·실패는 엑셀로 내보내지 않는다."""
    return [{'name': r['name']} for r in rows if r['grade'] in AUTO_GRADES]


class PipelineTest(unittest.TestCase):
    def setUp(self):
        harvested = edufine.read_group_workbook(SAMPLE)
        self.codes, _, _ = edufine.merge_codes(edufine.empty_codes(), harvested)

    def test_paste_to_workbook(self):
        pasted = '학성초\n한천초'
        rows = parse_orgs(pasted)
        ready, missing = edufine.split_by_code(confirmed(rows), self.codes)
        self.assertEqual(len(ready), 2)
        self.assertEqual(missing, [])

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'g.xlsx')
            edufine.build_workbook(ready, META, out)
            back = edufine.read_group_workbook(out)
            self.assertEqual(
                sorted(back['기관'].values()), ['M100000795', 'M100000796'])

    def test_uncertain_entry_never_reaches_the_workbook(self):
        # '오송솔미' 는 추정이다. 확정하지 않은 채로 엑셀에 실리면 안 된다.
        rows = parse_orgs('학성초\n오송솔미')
        grades = {r['raw']: r['grade'] for r in rows}
        self.assertEqual(grades['오송솔미'], 'fuzzy')

        ready, _ = edufine.split_by_code(confirmed(rows), self.codes)
        self.assertEqual([r['name'] for r in ready], ['학성초등학교'])

    def test_known_org_without_code_is_reported_not_dropped(self):
        rows = parse_orgs('학성초\n백곡초')          # 백곡초는 코드 사전에 없다
        ready, missing = edufine.split_by_code(confirmed(rows), self.codes)
        self.assertEqual([r['name'] for r in ready], ['학성초등학교'])
        self.assertEqual([r['name'] for r in missing], ['백곡초등학교'])
        self.assertEqual(missing[0]['reason'], '코드 없음')

    def test_edufine_full_path_input_round_trips(self):
        # 에듀파인에서 복사해 온 수신기관명을 그대로 붙여넣어도 통해야 한다
        rows = parse_orgs('충청북도진천교육지원청 학성초등학교')
        ready, _ = edufine.split_by_code(confirmed(rows), self.codes)
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]['code'], 'M100000795')
        self.assertEqual(ready[0]['fullname'], '충청북도진천교육지원청 학성초등학교')


if __name__ == '__main__':
    unittest.main()


class DepartmentPipelineTest(unittest.TestCase):
    """교육청·직속기관 부서도 엑셀까지 간다."""

    def setUp(self):
        self.codes = edufine.load_codes()
        self.index = edufine.index_by_short_name(self.codes)

    def resolve_all(self, text):
        """앱이 하는 것과 같은 경로 — org_db 로 읽고 코드 사전으로 다시 본다."""
        return edufine.apply_codes(parse_orgs(text), self.codes, self.index)

    def test_departments_reach_the_workbook(self):
        pasted = '정책기획과\n청주교육지원청 행정과\n단재교육연수원 교육연수부\n학성초'
        rows = self.resolve_all(pasted)
        self.assertTrue(all(r['grade'] == 'exact' for r in rows), rows)

        ready, missing = edufine.split_by_code(confirmed(rows), self.codes)
        self.assertEqual(missing, [])
        self.assertEqual(len(ready), 4)

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'g.xlsx')
            edufine.build_workbook(ready, META, out)
            back = edufine.read_group_workbook(out)
            self.assertIn('충청북도청주교육지원청 행정과', back['기관'])
            self.assertIn('충청북도교육청 정책기획과', back['기관'])

    def test_bare_shared_department_is_held_for_the_user(self):
        rows = self.resolve_all('행정과')
        self.assertEqual(rows[0]['grade'], 'ambiguous')
        self.assertGreater(len(rows[0]['candidates']), 1)
        ready, _ = edufine.split_by_code(confirmed(rows), self.codes)
        self.assertEqual(ready, [])

    def test_neighbouring_offices_are_not_swapped(self):
        rows = self.resolve_all('청주교육지원청 행정과\n충주교육지원청 행정과')
        names = [r['name'] for r in rows]
        self.assertEqual(names, ['충청북도청주교육지원청 행정과',
                                 '충청북도충주교육지원청 행정과'])
