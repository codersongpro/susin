"""theme / glass 단위 테스트. tkinter 없이 돈다. 저장소의 tests/ 로 옮겨 쓴다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import theme  # noqa: E402

try:
    import glass  # noqa: E402
except ImportError:  # Pillow 없음
    glass = None


class ThemeTest(unittest.TestCase):
    def test_text_contrast_meets_aa(self):
        for tool in theme.TOOLS:
            acc, on_acc, acc_c, on_acc_c = theme.accent(tool)
            self.assertGreaterEqual(theme.contrast(acc, on_acc), 4.5, tool)
            self.assertGreaterEqual(theme.contrast(acc_c, on_acc_c), 4.5, tool)
        for name in ('error', 'warn', 'ok'):
            self.assertGreaterEqual(
                theme.contrast(theme.COLORS[name + '_container'],
                               theme.COLORS['on_' + name + '_container']), 4.5, name)

    def test_text_on_glass_is_readable(self):
        # 가장 어두운 바탕 덩어리 위에 흰색 56% 를 얹어도 본문 글자가 읽혀야 한다
        worst = theme.mix('#FFFFFF', '#7A84FF', theme.GLASS['fill'])
        self.assertGreaterEqual(theme.contrast(theme.COLORS['on_surface'], worst), 7)
        self.assertGreaterEqual(theme.contrast(theme.COLORS['on_surface_variant'], worst), 4.5)

    def test_mix(self):
        self.assertEqual(theme.mix('#FFFFFF', '#000000', 0.5), '#808080')


@unittest.skipIf(glass is None, 'Pillow 가 없습니다')
class GlassTest(unittest.TestCase):
    def test_backdrop_and_panel(self):
        bg = glass.make_backdrop(400, 300, 'susin')
        self.assertEqual(bg.size, (400, 300))
        panel = glass.glass_panel(bg, (20, 20, 220, 160), radius=28)
        self.assertEqual(panel.size, (200, 140))
        self.assertEqual(panel.getpixel((0, 0))[3], 0)       # 둥근 모서리는 투명
        self.assertEqual(panel.getpixel((100, 70))[3], 255)  # 안쪽은 불투명
        color = glass.average_color(panel)
        self.assertRegex(color, r'^#[0-9A-F]{6}$')

    def test_compose_keeps_size(self):
        bg = glass.make_backdrop(300, 200)
        out = glass.compose(bg, [((10, 10, 150, 100), 20, False)])
        self.assertEqual(out.size, (300, 200))


@unittest.skipIf(glass is None, 'Pillow 가 없습니다')
class ShellTest(unittest.TestCase):
    """신통픽 창 틀에 쓰는 확장."""

    def test_layout_follows_the_spec(self):
        layout = glass.shell_layout(1120, 720)
        self.assertEqual(layout['top'], (16, 16, 1104, 80))
        self.assertEqual(layout['rail'][2] - layout['rail'][0], 92)
        self.assertEqual(layout['body'][0] - layout['rail'][2], 14)   # 판 사이 14
        self.assertEqual(layout['status'][3], 720 - 16)

    def test_every_panel_has_the_same_mean_color(self):
        """위젯 바탕색을 한 가지로 쓰므로, 판 안 평균색이 PANEL_BG 여야 한다."""
        from PIL import ImageStat
        for tool in theme.TOOLS:
            shell = glass.compose_shell(1120, 720, tool)
            for name, box in glass.shell_layout(1120, 720).items():
                inner = shell.crop((box[0] + 24, box[1] + 10, box[2] - 24, box[3] - 10))
                mean = ImageStat.Stat(inner).mean
                target = theme.hex_to_rgb(glass.PANEL_BG)
                for got, want in zip(mean, target):
                    self.assertLess(abs(got - want), 4, (tool, name, mean))

    def test_color_variation_inside_a_panel_is_small(self):
        """위젯 사각형이 보이지 않으려면 판 안 색 차이가 작아야 한다."""
        shell = glass.compose_shell(1120, 720, 'sotong')
        box = glass.shell_layout(1120, 720)['body']
        inner = shell.crop((box[0] + 30, box[1] + 30, box[2] - 30, box[3] - 30))
        for low, high in inner.getextrema():
            self.assertLess(high - low, 14)

    def test_backdrop_is_not_muddy(self):
        """색 덩어리를 투명 검정 위에서 흐리게 하면 가장자리가 어두워진다 (예전 버그)."""
        bg = glass.make_backdrop(1120, 720, 'sotong')
        for point in ((115, 300), (560, 87), (8, 300)):
            self.assertGreater(min(bg.getpixel(point)), 200, point)

    def test_size_is_clamped(self):
        self.assertEqual(glass.compose_shell(10, 10).size, (320, 240))

    def test_pill_has_transparent_corners(self):
        pill = glass.pill(120, 40, fill='#4A53C9')
        self.assertEqual(pill.getpixel((0, 0))[3], 0)
        self.assertEqual(pill.getpixel((60, 20))[3], 255)
        left = glass.pill(60, 40, fill='#4A53C9', sides='left')
        self.assertEqual(left.getpixel((0, 0))[3], 0)
        self.assertEqual(left.getpixel((59, 0))[3], 255)    # 오른쪽은 각진 모서리

    def test_icons(self):
        for name in glass.ICON_NAMES:
            img = glass.icon(name, 20, '#4A53C9')
            self.assertEqual(img.size, (20, 20))
            self.assertGreater(max(img.getchannel('A').tobytes()), 0, name)
        with self.assertRaises(ValueError):
            glass.icon('없는것', 20, '#000000')

    def test_png_base64_round_trips(self):
        import base64
        import io
        from PIL import Image
        data = glass.png_base64(glass.circle(12, '#FFFFFF'))
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(data))).size, (12, 12))


@unittest.skipIf(glass is None, 'Pillow 가 없습니다')
class FastDrawingTest(unittest.TestCase):
    """창 크기를 끌어 바꾸는 동안 쓰는 빠른 그리기가 느린 쪽과 같은 모양을 내야 한다."""

    def test_fast_mask_matches_the_slow_one(self):
        from PIL import ImageChops
        for size, radius in (((300, 200), 28), ((120, 60), 30), ((50, 50), 20)):
            fast = glass.fast_rounded_mask(size, radius)
            slow = glass._rounded_mask(size, min(radius, size[0] // 2, size[1] // 2))
            diff = ImageChops.difference(fast, slow)
            self.assertLessEqual(diff.getextrema()[1], 40, (size, radius))
            # 모서리 바깥은 비고 가운데는 찬다
            self.assertEqual(fast.getpixel((0, 0)), 0)
            self.assertEqual(fast.getpixel((size[0] // 2, size[1] // 2)), 255)

    def test_card_image_has_round_corners_and_a_ring(self):
        image = glass.card_image(200, 100, '#FFFFFF', outline='#767684', outline_width=1, radius=20)
        self.assertEqual(image.size, (200, 100))
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertEqual(image.getpixel((100, 50))[:3], (255, 255, 255))
        self.assertGreater(image.getpixel((100, 0))[3], 200)        # 위쪽 가장자리 선

    def test_backdrop_keeps_its_size_when_drawn_small(self):
        for size in ((1280, 820), (333, 211), (40, 30)):
            self.assertEqual(glass.make_backdrop(*size, 'sotong').size, size)

    def test_compose_shell_is_fast_enough_for_live_resizing(self):
        import time
        start = time.time()
        glass.compose_shell(1280, 820, 'sotong')
        self.assertLess(time.time() - start, 0.6)          # 예전에는 0.35~0.6초였다

    def test_ppm_round_trip(self):
        from PIL import Image
        import io
        image = Image.new('RGB', (7, 5), (10, 20, 30))
        data = glass.ppm_bytes(image)
        self.assertTrue(data.startswith(b'P6 7 5 255\n'))
        self.assertEqual(Image.open(io.BytesIO(data)).getpixel((3, 2)), (10, 20, 30))

    def test_layout_scales_with_zoom(self):
        base = glass.shell_layout(1280, 820)
        zoomed = glass.shell_layout(1600, 1025, zoom=1.25)
        self.assertEqual(zoomed['rail'][2] - zoomed['rail'][0], round(92 * 1.25))
        self.assertGreater(zoomed['top'][3] - zoomed['top'][1], base['top'][3] - base['top'][1])


@unittest.skipIf(glass is None, 'Pillow 가 없습니다')
class GuideDrawingTest(unittest.TestCase):
    """Iorad 처럼 화면을 어둡게 하고 대상만 밝게 비추는 그림."""

    def setUp(self):
        from PIL import Image
        self.base = Image.new('RGB', (400, 300), (240, 240, 250))

    def test_spotlight_keeps_the_target_bright_and_dims_the_rest(self):
        out = glass.spotlight(self.base, (100, 100, 200, 160), radius=12, dim=0.6, ring='#4A53C9')
        self.assertEqual(out.getpixel((150, 130)), (240, 240, 250))     # 대상은 그대로
        dark = out.getpixel((20, 20))
        self.assertLess(sum(dark), sum((240, 240, 250)) * 0.6)          # 나머지는 어둡다
        # 테두리 색이 구멍 바로 바깥에 있다
        ring = out.getpixel((150, 100 - 2))
        self.assertGreater(ring[2], ring[0])

    def test_spotlight_without_a_target_only_dims(self):
        out = glass.spotlight(self.base, None, dim=0.5)
        self.assertEqual(out.size, self.base.size)
        self.assertLess(sum(out.getpixel((200, 150))), sum((240, 240, 250)))

    def test_spotlight_survives_a_box_outside_the_image(self):
        out = glass.spotlight(self.base, (-30, -30, 60, 40), ring='#00695C')
        self.assertEqual(out.size, self.base.size)
        out = glass.spotlight(self.base, (390, 290, 500, 400), ring='#00695C')
        self.assertEqual(out.size, self.base.size)

    def test_callout_draws_a_white_bubble_with_a_tail(self):
        dark = glass.spotlight(self.base, None, dim=0.6)
        out = glass.callout(dark, (150, 100, 330, 220), radius=18,
                            arrow=[(152, 140), (136, 160), (152, 180)])
        self.assertEqual(out.getpixel((240, 160)), (255, 255, 255))     # 말풍선 안
        self.assertEqual(out.getpixel((142, 160)), (255, 255, 255))     # 꼬리
        self.assertNotEqual(out.getpixel((151, 101)), (255, 255, 255))  # 둥근 모서리 바깥


if __name__ == '__main__':
    unittest.main()
