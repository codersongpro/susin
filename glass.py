"""tkinter 에서 글래스 판을 그리는 도구 (Pillow).

tkinter 는 뒤 화면을 흐리게 비추는 기능(backdrop-filter)이 없다. 대신 창 바탕이
고정된 그림이라는 점을 이용한다.
  1. 바탕 그림(색 덩어리)을 한 번 만든다.
  2. 판이 놓일 자리를 바탕에서 오려 흐리게 하고, 흰색을 얹고, 둥근 모서리와
     가장자리 선을 그린다.
  3. 그 그림을 Canvas 에 깐다. 위젯은 판 평균색을 bg 로 써서 판 위에 놓는다.
창 크기가 바뀌면 다시 만든다 (<Configure> 에 디바운스).

이 모듈은 PIL 이미지만 다룬다. PhotoImage 변환은 호출하는 쪽이 한다.
"""
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme import GLASS, PANEL_BG, hex_to_rgb, rgb_to_hex, shell_layout  # noqa: F401

SS = 3  # 모서리 매끈하게: 3배로 그린 뒤 줄인다

BLOBS_SOTONG = [  # (cx, cy, 반지름, 색) 창 크기에 대한 비율. 겹쳐도 탁해지지 않게 옅게 쓴다.
    (0.06, 0.10, 0.34, (140, 150, 255, 150)),
    (0.98, 0.06, 0.30, (255, 175, 215, 130)),
    (0.86, 1.02, 0.38, (130, 235, 220, 150)),
    (0.02, 1.00, 0.26, (255, 222, 160, 120)),
]
BLOBS_SUSIN = [
    (0.06, 0.10, 0.34, (120, 232, 212, 150)),
    (0.98, 0.06, 0.30, (150, 185, 255, 125)),
    (0.86, 1.02, 0.38, (255, 212, 170, 135)),
    (0.02, 1.00, 0.26, (205, 175, 255, 110)),
]
BASE = {'sotong': '#F4F5FE', 'susin': '#F2F9F7'}


def make_backdrop(width, height, tool='sotong'):
    """창 전체 바탕 그림 (RGB)."""
    blobs = BLOBS_SUSIN if tool == 'susin' else BLOBS_SOTONG
    img = Image.new('RGBA', (width, height), hex_to_rgb(BASE.get(tool, BASE['sotong'])) + (255,))
    for cx, cy, r, color in blobs:
        # 투명 검정 위에서 흐리게 하면 가장자리가 어두워져 탁해진다. 같은 색을 깔아 둔다.
        layer = Image.new('RGBA', (width, height), color[:3] + (0,))
        radius = int(r * max(width, height))
        x, y = int(cx * width), int(cy * height)
        ImageDraw.Draw(layer).ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.45))
        img = Image.alpha_composite(img, layer)
    veil = Image.new('RGBA', (width, height), (255, 255, 255, 38))
    return Image.alpha_composite(img, veil).convert('RGB')


def _rounded_mask(size, radius):
    w, h = size
    big = Image.new('L', (w * SS, h * SS), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius * SS, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def glass_panel(backdrop, box, radius=28, strong=False, blur=True):
    """backdrop 의 box(x0,y0,x1,y1) 자리에 놓을 유리 판. RGBA 반환.

    blur=False 는 '판 위의 판'. 흰색 50% 만 얹는다.
    """
    x0, y0, x1, y1 = box
    size = (x1 - x0, y1 - y0)
    crop = backdrop.crop(box).convert('RGB')
    if blur:
        crop = crop.filter(ImageFilter.GaussianBlur(GLASS['blur_px'] / 2))
    fill = GLASS['fill_strong'] if strong else (GLASS['fill'] if blur else GLASS['inner'])
    white = Image.new('RGB', size, (255, 255, 255))
    body = Image.blend(crop, white, fill)

    mask = _rounded_mask(size, radius)
    # 가장자리 1px: 마스크를 한 칸 깎아 뺀 테두리에 흰색 78%
    inner = _rounded_mask((size[0] - 2, size[1] - 2), max(radius - 1, 1))
    inner_full = Image.new('L', size, 0)
    inner_full.paste(inner, (1, 1))
    edge = ImageChops.subtract(mask, inner_full)
    edge_alpha = edge.point(lambda v: int(v * GLASS['edge']))
    body.paste(Image.new('RGB', size, (255, 255, 255)), (0, 0), edge_alpha)

    out = body.convert('RGBA')
    out.putalpha(mask)
    return out


def average_color(image):
    """판 평균색. 판 위에 놓는 tk 위젯의 bg 로 쓴다 (tk 위젯은 투명할 수 없다)."""
    small = image.convert('RGB').resize((1, 1), Image.BOX)
    return rgb_to_hex(small.getpixel((0, 0)))


def compose(backdrop, panels):
    """backdrop 에 panels[(box, radius, strong)] 를 붙인 창 전체 그림. Canvas 한 장으로 깔기 좋다."""
    out = backdrop.convert('RGBA')
    for box, radius, strong in panels:
        out.alpha_composite(glass_panel(backdrop, box, radius, strong), (box[0], box[1]))
    return out.convert('RGB')


# ═══ 신통픽 화면용 확장 ═══════════════════════════════════════════════
# tkinter 위젯은 투명할 수 없다. 판 위에 놓는 위젯은 모두 같은 바탕색(PANEL_BG)을
# 쓰고, 판은 그 색을 평균으로 하되 가장자리 쪽에 바탕 색이 살짝 비치게 그린다.
# 그래야 위젯 사각형이 판과 어긋나 보이지 않고, 도구를 바꿔도 위젯 색을 다시 칠하지 않는다.
FLAT_KEEP = 0.38   # 판 안의 색 변화를 이만큼만 남긴다 (0=완전 균일, 1=그대로)


def _shift_to_mean(image, target_hex, keep):
    """image 의 색 변화를 keep 배로 줄이고, 평균색이 target 이 되게 옮긴다."""
    avg = image.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0))
    target = hex_to_rgb(target_hex)
    flat = Image.new('RGB', image.size, avg)
    softened = Image.blend(flat, image.convert('RGB'), keep)
    bands = []
    for band, delta in zip(softened.split(), (target[i] - avg[i] for i in range(3))):
        bands.append(band.point(lambda v, d=delta: max(0, min(255, v + d))))
    return Image.merge('RGB', bands)


def flat_glass_panel(backdrop, box, radius=28, strong=True, mean=PANEL_BG, keep=FLAT_KEEP):
    """glass_panel 과 같은데 판 안 평균색이 mean 이다. RGBA 반환."""
    x0, y0, x1, y1 = box
    size = (x1 - x0, y1 - y0)
    radius = min(radius, size[1] // 2, size[0] // 2)
    crop = backdrop.crop(box).convert('RGB').filter(ImageFilter.GaussianBlur(GLASS['blur_px'] / 2))
    fill = GLASS['fill_strong'] if strong else GLASS['fill']
    body = Image.blend(crop, Image.new('RGB', size, (255, 255, 255)), fill)
    body = _shift_to_mean(body, mean, keep)

    mask = _rounded_mask(size, radius)
    inner = _rounded_mask((size[0] - 2, size[1] - 2), max(radius - 1, 1))
    inner_full = Image.new('L', size, 0)
    inner_full.paste(inner, (1, 1))
    edge = ImageChops.subtract(mask, inner_full).point(lambda v: int(v * GLASS['edge']))
    body.paste(Image.new('RGB', size, (255, 255, 255)), (0, 0), edge)
    out = body.convert('RGBA')
    out.putalpha(mask)
    return out


def panel_shadow(size, radius, blur=9, alpha=12, spread=10):
    """판 아래에 깔 부드러운 그림자. size 보다 spread 만큼 사방으로 크다 (RGBA)."""
    w, h = size[0] + spread * 2, size[1] + spread * 2
    layer = Image.new('L', (w, h), 0)
    ImageDraw.Draw(layer).rounded_rectangle(
        (spread, spread + 3, spread + size[0] - 1, spread + size[1] + 2), radius, fill=alpha)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new('RGBA', (w, h), (70, 74, 150, 0))
    out.putalpha(layer)
    return out


PANEL_RADIUS = {'top': 32, 'rail': 28, 'body': 28, 'status': 20}


def compose_shell(width, height, tool='sotong'):
    """창 틀 전체 그림 (RGB). Canvas 한 장으로 깔고, 위젯은 판 자리에 올린다."""
    width, height = max(width, 320), max(height, 240)
    layout = shell_layout(width, height)
    back = make_backdrop(width, height, tool)
    out = back.convert('RGBA')
    for name, box in layout.items():
        radius = PANEL_RADIUS[name]
        size = (box[2] - box[0], box[3] - box[1])
        spread = 10
        out.alpha_composite(panel_shadow(size, min(radius, size[1] // 2)),
                            (box[0] - spread, box[1] - spread))
    for name, box in layout.items():
        out.alpha_composite(flat_glass_panel(back, box, PANEL_RADIUS[name]), (box[0], box[1]))
    return out.convert('RGB')


# ── 알약, 칩, 아이콘 ─────────────────────────────────────────────────

def _pill_mask(width, height, radius, scale, sides):
    """알약 모양 마스크 (L, scale 배). 한쪽만 둥근 모양은 둥근 판과 네모 판을 합쳐 만든다.

    PIL 의 rounded_rectangle(corners=...) 는 반지름이 높이의 절반일 때 오류가 나서 쓰지 않는다.
    """
    w, h = width * scale, height * scale
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius * scale, fill=255)
    if sides == 'left':
        draw.rectangle((w // 2, 0, w - 1, h - 1), fill=255)
    elif sides == 'right':
        draw.rectangle((0, 0, w // 2, h - 1), fill=255)
    return mask


def pill(width, height, fill=None, outline=None, outline_width=1, radius=None, scale=SS,
         sides='both'):
    """둥근 알약 모양 (RGBA, 바깥은 투명).

    sides 는 'both', 'left', 'right' 다. 도구 선택처럼 붙어 있는 알약의 한쪽만 둥글게 한다.
    """
    radius = height // 2 if radius is None else radius
    outer = _pill_mask(width, height, radius, scale, sides)
    big = Image.new('RGBA', outer.size, (0, 0, 0, 0))
    if fill:
        big.paste(Image.new('RGBA', outer.size, hex_to_rgb(fill) + (255,)), (0, 0), outer)
    if outline:
        ow = max(1, outline_width)
        inner = Image.new('L', outer.size, 0)
        inner.paste(_pill_mask(width - 2 * ow, height - 2 * ow, max(radius - ow, 1), scale, sides),
                    (ow * scale, ow * scale))
        ring = ImageChops.subtract(outer, inner)
        big.paste(Image.new('RGBA', outer.size, hex_to_rgb(outline) + (255,)), (0, 0), ring)
    return big.resize((width, height), Image.LANCZOS)


def circle(diameter, fill, scale=SS):
    big = Image.new('RGBA', (diameter * scale, diameter * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, diameter * scale - 1, diameter * scale - 1),
                                fill=hex_to_rgb(fill) + (255,))
    return big.resize((diameter, diameter), Image.LANCZOS)


ICON_NAMES = ('menu', 'pin', 'play', 'file', 'help', 'check', 'warn')


def icon(name, size, color, scale=4):
    """작은 선 아이콘 (RGBA). 글꼴이 없어도 같은 모양으로 나오도록 직접 그린다."""
    if name not in ICON_NAMES:
        raise ValueError(f'모르는 아이콘: {name}')
    s = size * scale
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = hex_to_rgb(color) + (255,)
    w = max(2, round(s * 0.09))

    def p(x, y):
        return (x * s, y * s)

    if name == 'menu':
        for y, x1 in ((0.28, 0.80), (0.50, 0.80), (0.72, 0.58)):
            d.line([p(0.20, y), p(x1, y)], fill=c, width=w)
    elif name == 'pin':
        d.ellipse((p(0.24, 0.12), p(0.76, 0.64)), outline=c, width=w)
        d.polygon([p(0.31, 0.55), p(0.69, 0.55), p(0.50, 0.90)], fill=c)
        d.ellipse((p(0.42, 0.30), p(0.58, 0.46)), fill=c)
    elif name == 'play':
        d.polygon([p(0.30, 0.20), p(0.30, 0.80), p(0.78, 0.50)], outline=c, fill=None)
        d.line([p(0.30, 0.20), p(0.78, 0.50), p(0.30, 0.80), p(0.30, 0.20)], fill=c, width=w,
               joint='curve')
    elif name == 'file':
        d.line([p(0.26, 0.12), p(0.60, 0.12), p(0.78, 0.30), p(0.78, 0.88), p(0.26, 0.88),
                p(0.26, 0.12)], fill=c, width=w, joint='curve')
        d.line([p(0.60, 0.12), p(0.60, 0.30), p(0.78, 0.30)], fill=c, width=w, joint='curve')
    elif name == 'help':
        d.ellipse((p(0.12, 0.12), p(0.88, 0.88)), outline=c, width=w)
        d.arc((p(0.36, 0.28), p(0.64, 0.54)), 180, 20, fill=c, width=w)
        d.line([p(0.60, 0.44), p(0.50, 0.56), p(0.50, 0.62)], fill=c, width=w)
        d.ellipse((p(0.46, 0.70), p(0.54, 0.78)), fill=c)
    elif name == 'check':
        d.line([p(0.20, 0.52), p(0.42, 0.74), p(0.82, 0.28)], fill=c, width=w + 1, joint='curve')
    elif name == 'warn':
        d.line([p(0.50, 0.14), p(0.88, 0.82), p(0.12, 0.82), p(0.50, 0.14)], fill=c, width=w,
               joint='curve')
        d.line([p(0.50, 0.40), p(0.50, 0.60)], fill=c, width=w)
        d.ellipse((p(0.46, 0.66), p(0.54, 0.74)), fill=c)
    return img.resize((size, size), Image.LANCZOS)


def paste_center(base, overlay):
    """overlay(RGBA) 를 base(RGBA) 가운데에 얹은 새 그림."""
    out = base.copy()
    x = (base.width - overlay.width) // 2
    y = (base.height - overlay.height) // 2
    out.alpha_composite(overlay, (x, y))
    return out


def png_base64(image, level=6):
    """PIL 그림을 tk.PhotoImage(data=...) 에 넘길 글로. PIL.ImageTk 는 tkinter 를 불러와서 피한다.

    창 바탕처럼 큰 그림은 level 을 낮춰 빨리 만든다.
    """
    import base64
    import io
    buf = io.BytesIO()
    image.save(buf, 'PNG', compress_level=level)
    return base64.b64encode(buf.getvalue()).decode('ascii')
