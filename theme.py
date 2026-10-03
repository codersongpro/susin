"""신통픽 Material 3 글래스 테마 토큰.

design/tokens.json 과 같은 값이다. 한쪽을 고치면 다른 쪽도 고친다.
tkinter 없이 import 할 수 있다 (테스트가 돈다).
"""

FONT_FAMILY = '맑은 고딕'   # Windows 기본. Noto Sans KR 은 포함하지 않는다.

# 소통픽 = primary(남보라), 수신픽 = tertiary(청록)
TOOLS = ('sotong', 'susin')

COLORS = {
    'primary': '#4A53C9', 'on_primary': '#FFFFFF',
    'primary_container': '#E1E0FF', 'on_primary_container': '#0A0F6E',
    'tertiary': '#00695C', 'on_tertiary': '#FFFFFF',
    'tertiary_container': '#A7F0E0', 'on_tertiary_container': '#00201B',
    'error': '#B3261E', 'error_container': '#F9DEDC', 'on_error_container': '#410E0B',
    'warn': '#8A5100', 'warn_container': '#FFDDB3', 'on_warn_container': '#2B1700',
    'ok': '#1B6B3A', 'ok_container': '#BDF0CB', 'on_ok_container': '#00210D',
    'on_surface': '#1A1B27', 'on_surface_variant': '#464653', 'outline': '#767684',
}

# 글자 크기(pt). 화면 제목 24px 은 tkinter 에서 약 18pt.
TYPE = {
    'title': (FONT_FAMILY, 18, 'bold'),
    'section': (FONT_FAMILY, 12, 'bold'),
    'body': (FONT_FAMILY, 10),
    'caption': (FONT_FAMILY, 9),
    'label': (FONT_FAMILY, 9, 'bold'),
}

# 판 위에 놓는 tkinter 위젯의 바탕색. 위젯은 투명할 수 없어서 모든 판이 이 색을 평균으로 쓴다.
PANEL_BG = '#F6F7FC'

RADIUS = {'window': 32, 'panel': 28, 'inner': 20, 'field': 14, 'button': 20, 'chip': 8}

GLASS = {
    'fill': 0.56,          # 흰색 채움 농도
    'fill_strong': 0.74,   # 글자가 올라가는 판
    'inner': 0.50,         # 판 위의 판 (블러 없음)
    'edge': 0.78,          # 1px 가장자리
    'blur_px': 26,         # CSS 블러. PIL 반지름은 이 값의 절반쯤
}


def accent(tool):
    """도구별 강조색 4종. 반환: acc, on_acc, acc_container, on_acc_container."""
    if tool == 'susin':
        return (COLORS['tertiary'], COLORS['on_tertiary'],
                COLORS['tertiary_container'], COLORS['on_tertiary_container'])
    return (COLORS['primary'], COLORS['on_primary'],
            COLORS['primary_container'], COLORS['on_primary_container'])


def hex_to_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return '#%02X%02X%02X' % tuple(int(round(max(0, min(255, c)))) for c in rgb)


def mix(fg, bg, alpha):
    """fg 를 alpha(0~1) 만큼 bg 위에 얹은 색. 투명 위젯이 없는 tkinter 에서 쓴다."""
    f, b = hex_to_rgb(fg), hex_to_rgb(bg)
    return rgb_to_hex(tuple(f[i] * alpha + b[i] * (1 - alpha) for i in range(3)))


def luminance(value):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def shell_layout(width, height, pad=16, gap=14, rail=92, top=64, status=40):
    """창 틀 네 판의 자리 (x0, y0, x1, y1). 설계 문서 '화면 틀' 과 같다."""
    top_box = (pad, pad, width - pad, pad + top)
    status_box = (pad, height - pad - status, width - pad, height - pad)
    y0, y1 = top_box[3] + gap, status_box[1] - gap
    rail_box = (pad, y0, pad + rail, y1)
    body_box = (rail_box[2] + gap, y0, width - pad, y1)
    return {'top': top_box, 'rail': rail_box, 'body': body_box, 'status': status_box}
