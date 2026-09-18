import unittest

from sotong_parser import (
    AUTO_GRADES,
    GRADE_EXACT,
    GRADE_FUZZY,
    GRADE_NONE,
    candidate_orgs,
    lookup_org_graded,
    parse_orgs,
)


class LookupGradedTest(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(lookup_org_graded('학성초등학교'), ('학성초등학교', GRADE_EXACT))

    def test_registered_alias_is_exact(self):
        # 약칭이 org_db 에 별칭으로 들어 있으면 추정이 아니라 정확 일치다
        self.assertEqual(lookup_org_graded('학성초'), ('학성초등학교', GRADE_EXACT))

    def test_sido_prefix_variants_agree(self):
        self.assertEqual(lookup_org_graded('충북교육청')[0], '충청북도교육청')
        self.assertEqual(lookup_org_graded('충청북도교육청')[0], '충청북도교육청')

    def test_compound_abbreviation(self):
        # '충북외고' 가 '충북고등학교' 로 붙으면 공문이 엉뚱한 학교로 간다
        self.assertEqual(lookup_org_graded('충북외고')[0], '충북외국어고등학교')
        self.assertEqual(lookup_org_graded('청주여중')[0], '청주여자중학교')
        self.assertEqual(lookup_org_graded('충북공고')[0], '충북공업고등학교')

    def test_school_level_filter(self):
        # 초등학교 입력이 병설유치원으로 넘어가면 안 된다
        self.assertEqual(lookup_org_graded('오송솔미초')[0], '오송솔미초등학교')

    def test_unknown_is_none(self):
        name, grade = lookup_org_graded('있을리없는이름아무개기관')
        self.assertIsNone(name)
        self.assertEqual(grade, GRADE_NONE)

    def test_fuzzy_is_not_auto(self):
        # 추정 결과는 자동 확정 등급에 들어가면 안 된다
        _, grade = lookup_org_graded('오송솔미')
        self.assertEqual(grade, GRADE_FUZZY)
        self.assertNotIn(grade, AUTO_GRADES)


class ParseOrgsTest(unittest.TestCase):
    def names(self, text):
        return [r['name'] for r in parse_orgs(text)]

    def test_plain_lines(self):
        self.assertEqual(
            self.names('학성초\n한천초'),
            ['학성초등학교', '한천초등학교'],
        )

    def test_comma_and_bullets_and_numbering(self):
        self.assertEqual(
            self.names('- 학성초, 한천초\n1) 백곡초'),
            ['학성초등학교', '한천초등학교', '백곡초등학교'],
        )

    def test_dedupes_preserving_order(self):
        self.assertEqual(
            self.names('한천초\n학성초\n한천초등학교'),
            ['한천초등학교', '학성초등학교'],
        )

    def test_edufine_hierarchical_name_takes_last_segment(self):
        # 에듀파인 수신기관명은 '상위조직 하위조직' 순서다
        self.assertEqual(
            self.names('충청북도진천교육지원청 학성초등학교'),
            ['학성초등학교'],
        )

    def test_person_names_are_skipped(self):
        self.assertEqual(self.names('홍길동'), [])
        self.assertEqual(self.names('김철수 이영희'), [])

    def test_person_name_dropped_from_mixed_line(self):
        self.assertEqual(self.names('충주중학교\t박영수'), ['충주중학교'])

    def test_unresolved_is_reported_not_swallowed(self):
        rows = parse_orgs('있을리없는이름아무개기관')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['grade'], GRADE_NONE)
        self.assertIsNone(rows[0]['name'])

    def test_fuzzy_row_carries_candidates(self):
        rows = parse_orgs('오송솔미')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['grade'], GRADE_FUZZY)
        self.assertIn('오송솔미초등학교', rows[0]['candidates'])

    def test_can_preserve_duplicates_for_extraction_summary(self):
        rows = parse_orgs('학성초\n학성초\n학성초', deduplicate=False)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row['name'] == '학성초등학교' for row in rows))

        # 기본 호출은 기존 동작을 유지한다.
        self.assertEqual(len(parse_orgs('학성초\n학성초\n학성초')), 1)

    def test_auto_rows_have_no_candidates(self):
        for row in parse_orgs('학성초\n한천초'):
            self.assertIn(row['grade'], AUTO_GRADES)
            self.assertEqual(row['candidates'], [])


class CandidateTest(unittest.TestCase):
    def test_candidates_respect_school_level(self):
        # 초등학교로 물으면 유치원이 1순위로 오면 안 된다
        cands = candidate_orgs('오송솔미초')
        self.assertTrue(cands)
        self.assertEqual(cands[0], '오송솔미초등학교')


if __name__ == '__main__':
    unittest.main()


class EdufineOrgNamesTest(unittest.TestCase):
    """에듀파인 조직도에서 가져온 부서명이 org_db 에 안전하게 들어갔는지."""

    def test_departments_are_recognised(self):
        for name in ('정책기획과', '감사관', '교육연수부', '괴산교육도서관'):
            resolved, grade = lookup_org_graded(name)
            self.assertEqual(resolved, name, name)
            self.assertIn(grade, AUTO_GRADES, name)

    def test_unique_department_resolves_to_short_name(self):
        self.assertEqual(
            lookup_org_graded('충청북도교육청 정책기획과')[0], '정책기획과')

    def test_shared_department_keeps_its_full_path(self):
        # '유초등교육과'는 본청과 청주지원청 두 곳에 있다. 짧은 이름으로 줄이면
        # 정확한 전체경로를 줬는데도 어느 곳인지 알 수 없게 된다.
        self.assertEqual(
            lookup_org_graded('충청북도교육청 유초등교육과')[0],
            '충청북도교육청 유초등교육과')

    def test_person_detection_still_works(self):
        # 부서명을 넣다가 사람 이름 판별을 망가뜨리면 소통메신저가 깨진다
        from sotong_parser import is_person_name
        for name in ('홍길동', '김철수', '이영희', '박민', '다하'):
            self.assertTrue(is_person_name(name), name)

    def test_generic_department_names_stay_out(self):
        # '행정과'는 11곳에 있다. 하나로 확정되면 안 된다.
        from sotong_parser import _ORG_LOOKUP
        for generic in ('행정과', '교육과', '학교지원센터', '병설유치원'):
            self.assertNotIn(generic, _ORG_LOOKUP, generic)


class TitleColumnTest(unittest.TestCase):
    """소속 / 직위 / 성명 세 칸짜리 표.

    '교사' 가 이름 자리를 차지하고 정작 '송동석' 이 버려지던 문제의 회귀 방지선.
    """

    TABLE = ('소속 학교(기관)\t직위\t성명\n'
             '학성초등학교\t교사\t송동석\n'
             '새터초등학교\t교사\t박동훈\n'
             '음성교육지원청\t교육장\t안병권\n'
             '미래교육추진단\t단장\t이혜원\n'
             '자연과학교육원\t부장\t이강영\n'
             '창의특수교육과\t장학사\t김영국\n'
             '오송솔미초등학교\t연구사\t김은정\n'
             '충북여자고등학교\t교사\t김진설')

    def test_titles_are_not_people(self):
        from sotong_parser import is_person_name
        for title in ('교사', '교감', '교육장', '장학사', '연구사', '단장',
                      '부장', '주무관', '행정실장', '영양사'):
            self.assertFalse(is_person_name(title), title)

    def test_headers_are_not_people(self):
        from sotong_parser import is_person_name
        for header in ('성명', '이름', '직위', '소속', '번호', '비고'):
            self.assertFalse(is_person_name(header), header)

    def test_real_names_still_pass(self):
        from sotong_parser import is_person_name
        for name in ('송동석', '박동훈', '안병권', '이혜원', '김영국', '김은정'):
            self.assertTrue(is_person_name(name), name)

    def test_messenger_takes_the_name_not_the_title(self):
        from sotong_parser import parse_input
        rows = parse_input(self.TABLE)
        self.assertEqual(
            [(r['org'], r['name']) for r in rows],
            [('학성초등학교', '송동석'),
             ('새터초등학교', '박동훈'),
             ('충청북도음성교육지원청', '안병권'),
             ('미래교육추진단', '이혜원'),
             ('충청북도자연과학교육원', '이강영'),
             ('창의특수교육과', '김영국'),
             ('오송솔미초등학교', '김은정'),
             ('충북여자고등학교', '김진설')])

    def test_edufine_takes_only_the_org(self):
        names = [r['name'] for r in parse_orgs(self.TABLE)]
        self.assertEqual(names,
                         ['학성초등학교', '새터초등학교', '충청북도음성교육지원청',
                          '미래교육추진단', '충청북도자연과학교육원', '창의특수교육과',
                          '오송솔미초등학교', '충북여자고등학교'])
        self.assertNotIn(None, names, '머리글 줄이 기관으로 남았습니다')

    def test_hwp_cell_per_line_table(self):
        """한글 파일에서 뽑은 표는 칸 하나가 한 줄로 내려온다.

        순 / 역할 / 소속 / 직위 / 성명 / 연락처 여섯 칸짜리 실제 명단에서
        '교사' 가 이름 자리를 차지하고 '송동석' 이 버려지던 문제의 회귀 방지선.
        """
        from sotong_parser import parse_input
        cells = ['2026. 충북 GEG 성찰중심의 학습공동체 회원 명단',
                 '순', '역할', '소속 학교(기관)', '직위', '성명', '개인 연락처(휴대폰)',
                 '1', '회장', '학성초등학교', '교사', '송동석', '010-1234-5678',
                 '2', '총무', '새터초등학교', '교사', '박동훈', '',
                 '3', '자문', '음성교육지원청', '교육장', '안병권', '',
                 '4', '자문', '미래교육추진단', '단장', '이혜원', '',
                 '5', '회원', '오송솔미초등학교', '연구사', '김은정', '']
        text = '\n'.join(cells)
        self.assertEqual([(r['org'], r['name']) for r in parse_input(text)],
                         [('학성초등학교', '송동석'),
                          ('새터초등학교', '박동훈'),
                          ('충청북도음성교육지원청', '안병권'),
                          ('미래교육추진단', '이혜원'),
                          ('오송솔미초등학교', '김은정')])
        self.assertEqual([r['name'] for r in parse_orgs(text)],
                         ['학성초등학교', '새터초등학교', '충청북도음성교육지원청',
                          '미래교육추진단', '오송솔미초등학교'])

    def test_space_separated_table_with_numbering(self):
        from sotong_parser import parse_input
        text = ('번호 소속 직위 성명\n'
                '1 학성초등학교 교사 송동석\n'
                '2 충북외고 교감 김철수')
        self.assertEqual([(r['org'], r['name']) for r in parse_input(text)],
                         [('학성초등학교', '송동석'),
                          ('충북외국어고등학교', '김철수')])
        self.assertEqual([r['name'] for r in parse_orgs(text)],
                         ['학성초등학교', '충북외국어고등학교'])
