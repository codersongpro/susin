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
