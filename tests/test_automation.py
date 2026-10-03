"""검색 결과가 떴는지 보는 픽셀 판정 테스트."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation import (
    RESULT_MIN_COLUMNS,
    looks_like_result,
    result_text_columns,
)

WHITE = (255, 255, 255)
INK = (40, 40, 40)
LINE = (200, 200, 200)


def make_pixels(width, height, painted, color=INK, background=WHITE):
    """painted 에 든 (행, 열) 자리만 칠한 픽셀 목록을 만든다."""
    return [
        color if (row, col) in painted else background
        for row in range(height)
        for col in range(width)
    ]


class ResultDetectionTest(unittest.TestCase):
    def test_blank_area_has_no_result(self):
        pixels = make_pixels(40, 10, set())
        self.assertFalse(looks_like_result(pixels, 40, 10))

    def test_text_in_the_area_counts_as_a_result(self):
        painted = {(5, col) for col in range(10, 20)}
        pixels = make_pixels(40, 10, painted)
        self.assertTrue(looks_like_result(pixels, 40, 10))

    def test_text_off_to_the_side_still_counts(self):
        """좌표가 글자 사이 빈 칸에 떨어져도 옆의 글자를 본다."""
        painted = {(4, col) for col in range(30, 38)}
        pixels = make_pixels(40, 10, painted)
        self.assertTrue(looks_like_result(pixels, 40, 10))

    def test_a_ruled_line_is_not_a_result(self):
        """표 테두리처럼 가로로 이어진 단색 줄은 글자로 세지 않는다."""
        painted = {(3, col) for col in range(40)}
        pixels = make_pixels(40, 10, painted, color=LINE)
        self.assertEqual(result_text_columns(pixels, 40, 10), 0)
        self.assertFalse(looks_like_result(pixels, 40, 10))

    def test_text_on_a_highlighted_row_still_counts(self):
        """선택 강조로 줄 전체가 칠해져 있어도 글자가 있으면 결과로 본다."""
        pixels = make_pixels(40, 10, set(), background=WHITE)
        for col in range(40):                       # 파란 강조 띠
            pixels[3 * 40 + col] = (51, 102, 204)
        for col in range(12, 22):                   # 그 위의 흰 글자
            pixels[3 * 40 + col] = (255, 255, 255)
        self.assertTrue(looks_like_result(pixels, 40, 10))

    def test_a_few_stray_dots_are_not_enough(self):
        painted = {(2, 5)}
        pixels = make_pixels(40, 10, painted)
        self.assertLess(result_text_columns(pixels, 40, 10), RESULT_MIN_COLUMNS)
        self.assertFalse(looks_like_result(pixels, 40, 10))

    def test_short_pixel_list_does_not_crash(self):
        self.assertFalse(looks_like_result([WHITE] * 10, 40, 10))
        self.assertEqual(result_text_columns([], 0, 0), 0)


if __name__ == '__main__':
    unittest.main()


class SelectedListTest(unittest.TestCase):
    """[선택된 사용자] 목록 칸 고르기."""

    def test_message_depends_on_the_kind_of_list(self):
        from automation import LB_GETCOUNT, LVM_GETITEMCOUNT, count_message_for
        self.assertEqual(count_message_for('ListBox'), LB_GETCOUNT)
        self.assertEqual(count_message_for('TListBox'), LB_GETCOUNT)
        self.assertEqual(count_message_for('SysListView32'), LVM_GETITEMCOUNT)
        self.assertIsNone(count_message_for('Button'))
        self.assertIsNone(count_message_for(''))

    def test_picks_the_list_right_of_the_arrow(self):
        from automation import pick_selected_list
        children = [
            (1, 'ListBox', (0, 0, 300, 500)),        # 검색 결과
            (2, 'Button', (310, 240, 340, 260)),     # 화살표
            (3, 'ListBox', (350, 0, 650, 500)),      # 선택된 사용자
            (4, 'ListBox', (700, 0, 900, 500)),      # 더 먼 목록
        ]
        self.assertEqual(pick_selected_list(children, 325, 250)[0], 3)

    def test_list_must_span_the_arrow_height(self):
        from automation import pick_selected_list
        children = [(3, 'ListBox', (350, 0, 650, 200))]
        self.assertIsNone(pick_selected_list(children, 325, 250))

    def test_nothing_to_the_right(self):
        from automation import pick_selected_list
        self.assertIsNone(pick_selected_list([(1, 'ListBox', (0, 0, 300, 500))], 325, 250))


def web_dialog_nodes(selected=6, offscreen_after=4, with_label=True):
    """CEF 로 그린 [사용자 선택] 창을 흉내 낸 요소 목록.

    왼쪽 조직도(x 0~300)에 사람 20명, 오른쪽(x 400~600) 에 담긴 사람 selected 명.
    담긴 사람 한 줄에는 사진, 이름, 소속, 빼기 단추가 있다.
    """
    nodes = []

    def add(parent, kind, rect, name='', off=False):
        nodes.append({'id': len(nodes), 'parent': parent, 'type': kind,
                      'rect': rect, 'name': name, 'offscreen': off})
        return len(nodes) - 1

    doc = add(-1, 50030, (0, 0, 600, 600))
    if with_label:
        add(doc, 50020, (400, 10, 500, 30), '선택된 사용자')
    tree = add(doc, 50023, (0, 40, 300, 600))
    for k in range(20):
        add(tree, 50024, (0, 40 + k * 20, 300, 60 + k * 20), f'조직도사람{k}')
    box = add(doc, 50026, (400, 40, 600, 400))
    for k in range(selected):
        top = 40 + k * 60
        row = add(box, 50026, (400, top, 600, top + 60), off=k > offscreen_after)
        add(row, 50006, (400, top, 440, top + 60))
        add(row, 50020, (440, top, 560, top + 30), f'담긴사람{k}')
        add(row, 50020, (440, top + 30, 560, top + 60), '소속')
        add(row, 50000, (560, top, 600, top + 60), '빼기')
    return nodes


class WebDialogGuessTest(unittest.TestCase):
    """웹 화면 속 [선택된 사용자] 목록 고르기."""

    def test_counts_rows_on_the_right_including_offscreen(self):
        from automation import guess_selected_list
        node, kid_type, count, offscreen = guess_selected_list(web_dialog_nodes(), 350)
        self.assertEqual((kid_type, count, offscreen), (50026, 6, 1))

    def test_left_tree_is_never_picked(self):
        from automation import guess_selected_list
        guess = guess_selected_list(web_dialog_nodes(selected=0), 350)
        self.assertTrue(guess is None or guess[2] < 20, '조직도를 셌습니다')

    def test_works_without_the_label(self):
        from automation import guess_selected_list
        guess = guess_selected_list(web_dialog_nodes(with_label=False), 350)
        self.assertEqual(guess[2], 6)

    def test_type_names(self):
        from automation import uia_type_name
        self.assertEqual(uia_type_name(50007), 'ListItem')
        self.assertEqual(uia_type_name(12345), '12345')


class RowTextsTest(unittest.TestCase):
    def test_each_row_joins_its_texts(self):
        from automation import guess_selected_list, row_texts
        nodes = web_dialog_nodes(selected=3)
        node, kid_type, _count, _off = guess_selected_list(nodes, 350)
        rows = row_texts(nodes, node['id'], kid_type)
        self.assertEqual(rows, ['담긴사람0 소속 빼기', '담긴사람1 소속 빼기', '담긴사람2 소속 빼기'])


def real_messenger_nodes():
    """2026-10-03 실제 PC 에서 읽은 [사용자 선택] 창의 짜임새.

    읽은 요소 88개. 오른쪽에 'Custom 안 Button 7개' (선택된 사용자 7명) 와
    그 아래 'Custom 안 Text 2개' (그룹단위 선택추가 제목) 가 있었다. 화면 밖 요소
    하나는 '선택된 사용자 입니다.' 안내문으로 보이며, 제목보다 먼저 나왔다.
    창 왼쪽 위가 (970, 120), 화살표 버튼이 (1284, 403).
    """
    nodes = []

    def add(parent, kind, rect, name='', off=False):
        nodes.append({'id': len(nodes), 'parent': parent, 'type': kind,
                      'rect': rect, 'name': name, 'offscreen': off})
        return len(nodes) - 1

    x0, y0 = 970, 120
    doc = add(-1, 50030, (x0, y0, x0 + 630, y0 + 600))
    # 숨은 안내문이 제목보다 먼저 나온다
    add(doc, 50020, (x0 + 200, y0 + 300, x0 + 400, y0 + 320), '선택된 사용자 입니다.', off=True)
    tree = add(doc, 50023, (x0 + 10, y0 + 150, x0 + 290, y0 + 530))
    for k in range(18):
        add(tree, 50024, (x0 + 10, y0 + 150 + k * 20, x0 + 290, y0 + 170 + k * 20),
            f'조직도{k}[교사(초등)]')
    add(doc, 50020, (x0 + 339, y0 + 60, x0 + 450, y0 + 78), '선택된 사용자')
    box = add(doc, 50025, (x0 + 339, y0 + 83, x0 + 615, y0 + 383))
    names = ['문유리 [부장교사]', '이경숙 [교사(초등)]', '김다래 [교사(초등)]',
             '나상연 [교사(초등)]', '함봉주 [교사(초등)]', '이정훈 [교사(초등)]',
             '송동석 [교사(초등)]']
    for k, name in enumerate(names):
        add(box, 50000, (x0 + 339, y0 + 83 + k * 49, x0 + 600, y0 + 132 + k * 49),
            f'{name} [전담] 교무')
    group = add(doc, 50025, (x0 + 339, y0 + 383, x0 + 615, y0 + 420))
    add(group, 50020, (x0 + 339, y0 + 383, x0 + 450, y0 + 400), '그룹단위 선택추가')
    add(group, 50020, (x0 + 450, y0 + 383, x0 + 600, y0 + 400), '(내그룹/조직도 더블클릭)')
    return nodes


class RealMessengerTest(unittest.TestCase):
    """7명이 담겨 있는데 2명으로 세던 문제의 회귀 방지선."""

    def test_counts_seven_not_two(self):
        from automation import guess_selected_list
        node, kid_type, count, _off = guess_selected_list(real_messenger_nodes(), 1284)
        self.assertEqual((kid_type, count), (50000, 7))

    def test_hidden_notice_is_not_the_label(self):
        from automation import find_label
        label = find_label(real_messenger_nodes(), '선택된 사용자')
        self.assertEqual(label['name'], '선택된 사용자')
        self.assertFalse(label['offscreen'])

    def test_person_rows(self):
        from automation import guess_selected_list, person_rows
        nodes = real_messenger_nodes()
        node, kid_type, _count, _off = guess_selected_list(nodes, 1284)
        self.assertEqual(person_rows(nodes, node['id'], kid_type), 7)

    def test_names_are_read_for_comparison(self):
        import reconcile
        from automation import guess_selected_list, row_texts
        nodes = real_messenger_nodes()
        node, kid_type, _count, _off = guess_selected_list(nodes, 1284)
        names = [reconcile.person_name_from_row(t) for t in row_texts(nodes, node['id'], kid_type)]
        self.assertEqual(names, ['문유리', '이경숙', '김다래', '나상연', '함봉주', '이정훈', '송동석'])


class SearchCountTest(unittest.TestCase):
    def test_visible_label_first(self):
        import re
        from automation import search_count_in
        pattern = re.compile(r'검색\s*결과\s*\(?\s*(\d+)\s*명')
        nodes = [{'name': '검색 결과(5명)', 'offscreen': True},
                 {'name': '검색 결과(2명)', 'offscreen': False}]
        self.assertEqual(search_count_in(nodes, pattern), 2)
        self.assertIsNone(search_count_in([{'name': '선택된 사용자'}], pattern))
