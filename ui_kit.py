"""신통픽 화면 부품 (Material 3 + 글래스).

알약 단추, 둥근 카드, 칩, 도구 선택, 단계 레일. 모양은 Pillow 로 그려 PNG 글자로 넘기고
(PIL.ImageTk 는 tkinter 를 불러와 테스트 스텁과 부딪힌다), 글자는 tk 가 그대로 그린다.
그래서 한글 입력, 글꼴, 크기 조절은 tk 가 하던 대로 된다.

Pillow 가 없으면 모양 없이 색 면으로만 그려서 앱이 죽지 않게 한다.
tkinter 위젯은 투명할 수 없으므로 판 위 위젯의 바탕은 모두 PANEL_BG 다 (glass.py 참고).
"""

import logging
import weakref

import tkinter as tk

from tkinter import ttk

from theme import COLORS, FONT_FAMILY, FONT_SCALE, PANEL_BG, accent, fs, mix

try:
    import glass
except ImportError:                  # Pillow 가 없다
    glass = None

HAVE_GLASS = glass is not None

FONT = FONT_FAMILY
INNER_BG = mix('#FFFFFF', PANEL_BG, 0.5)           # 판 위의 판
EDGE = mix(COLORS['outline'], '#FFFFFF', 0.22)     # 카드 가장자리

_state = {'tool': 'susin', 'zoom': 1.0}
_fonts = {}                         # (크기, 굵기) -> 이름 붙은 글꼴. 크기를 바꾸면 쓰는 곳이 한꺼번에 바뀐다
_scalables = weakref.WeakSet()      # 창 크기에 따라 다시 그려야 하는 부품 (칩, 도구 선택, 레일)

ZOOM_RANGE = (0.85, 1.6)


def px(n):
    """설계 픽셀을 지금 배율로."""
    return max(1, int(round(n * _state['zoom'])))


def _pt(pt):
    return max(8, int(round(pt * FONT_SCALE * _state['zoom'])))


def font(pt, weight='normal'):
    """배율을 따라 커지고 줄어드는 글꼴. 같은 (크기, 굵기)는 하나를 같이 쓴다.

    이름 붙은 글꼴(tkinter.font.Font)이라 크기를 바꾸면 그 글꼴을 쓰는 글자가 곧바로 바뀐다.
    Tk 가 없는 곳(테스트 스텁)에서는 그냥 (글꼴, 크기, 굵기) 로 돌려준다.
    """
    key = (pt, weight)
    found = _fonts.get(key)
    if found is None:
        try:
            import tkinter.font as tkfont
            found = tkfont.Font(family=FONT, size=_pt(pt), weight=weight)
        except Exception:
            found = (FONT, fs(pt), weight)
        _fonts[key] = found
    return found


ft = font


def zoom():
    return _state['zoom']


def set_zoom(value):
    """배율을 바꾼다. 글꼴은 곧바로 바뀌고, 그림으로 그린 부품은 다시 그린다. 바뀌었으면 True."""
    low, high = ZOOM_RANGE
    value = round(min(max(value, low), high), 2)
    if value == _state['zoom']:
        return False
    _state['zoom'] = value
    for (pt, _weight), found in _fonts.items():
        if hasattr(found, 'configure'):
            try:
                found.configure(size=_pt(pt))
            except Exception as exc:
                logging.debug('글꼴 크기 바꾸기 실패: %s', exc)
    retheme_buttons()
    for widget in list(_scalables):
        refresh_or_defer(widget, widget.rescale)
    return True


_stale = weakref.WeakKeyDictionary()   # 가려져서 다시 그리지 못한 부품 -> 열리면 부를 함수


def refresh_or_defer(widget, action):
    """보이는 부품은 바로 다시 그리고, 가려진 탭의 부품은 탭이 열릴 때 다시 그린다.

    가려진 탭의 부품은 Map 이벤트를 받지 못하므로(윗 틀만 Map 을 받는다), 탭이 바뀔 때
    flush_stale() 로 보이게 된 것들을 다시 그린다.
    """
    try:
        try:
            visible = bool(widget.winfo_viewable())
        except Exception:
            visible = True                      # 알 수 없으면 바로 그린다
        if visible:
            _stale.pop(widget, None)
            action()
        else:
            _stale[widget] = action
    except Exception as exc:
        logging.debug('부품 다시 그리기 실패: %s', exc)


def flush_stale():
    """가려져 있다가 보이게 된 부품을 다시 그린다. 탭이 바뀔 때마다 부른다."""
    for widget, action in list(_stale.items()):
        try:
            if widget.winfo_exists() and widget.winfo_viewable():
                _stale.pop(widget, None)
                action()
        except Exception as exc:
            logging.debug('가려졌던 부품 다시 그리기 실패: %s', exc)
            _stale.pop(widget, None)


def set_tool(tool):
    """도구 강조색을 바꾼다. 'sotong'(소통픽, 남보라) 또는 'susin'(수신픽, 청록)."""
    _state['tool'] = tool if tool in ('sotong', 'susin') else 'sotong'


def current_tool():
    return _state['tool']


def acc():
    """강조색 4종: acc, on_acc, acc_container, on_acc_container."""
    return accent(_state['tool'])


def container_bg(master):
    """위젯이 놓인 곳의 바탕색. 알약 모서리 바깥이 이 색으로 보인다."""
    try:
        value = master.cget('bg')
        if isinstance(value, str) and value:
            return value
    except Exception:
        pass
    return PANEL_BG


def photo(widget, image):
    """PIL 그림을 tk.PhotoImage 로. 돌려받은 것을 위젯이 붙들고 있어야 사라지지 않는다."""
    return tk.PhotoImage(master=widget, data=glass.png_base64(image, level=1))


def autowrap(label, margin=0, minimum=240):
    """라벨의 줄바꿈 폭을 놓인 틀의 폭에 맞춘다. 창을 키우고 줄이면 글이 따라서 다시 줄을 바꾼다."""
    holder = label.master

    def fit(_event=None):
        try:
            width = holder.winfo_width() - margin
            if width > minimum and abs(int(float(label.cget('wraplength') or 0)) - width) > 4:
                label.configure(wraplength=width)
        except Exception as exc:
            logging.debug('줄바꿈 폭 맞추기 실패: %s', exc)

    holder.bind('<Configure>', fit, add='+')
    return label


def measure(widget, font, text):
    """글자 폭(px). 재지 못하면 글자 수로 어림한다."""
    try:
        return int(widget.tk.call('font', 'measure', font, text))
    except Exception as exc:
        logging.debug('글자 폭 재기 실패: %s', exc)
        try:
            size = font.cget('size') if hasattr(font, 'cget') else font[1]
        except Exception:
            size = 10
        return int(len(text) * abs(int(size)) * 1.4)


# ── 단추 ─────────────────────────────────────────────────────────────

VARIANTS = ('filled', 'tonal', 'outlined', 'text', 'danger')

# 예전 화면이 단추마다 직접 넣던 색을 5종 가운데 하나로 옮긴다.
_LEGACY = {
    'danger': {'#B71C1C', '#C62828', '#F44336', '#E53935', '#FF0000', '#EF6C00', '#E65100'},
    'tonal': {'#607D8B', '#546E7A', '#455A64', '#795548', '#37474F'},
    'text': {'#9E9E9E', '#B0BEC5', '#90A4AE', '#757575', '#CFD8DC', '#BDBDBD'},
    'outlined': {'#6A1B9A'},
}


def variant_from_legacy(color):
    color = (color or '').upper()
    for name, colors in _LEGACY.items():
        if color in colors:
            return name
    return 'filled'


def _button_colors(variant, container, state):
    """(바탕, 글자, 테두리). 바탕이나 테두리가 없으면 None."""
    a, on_a, a_c, on_a_c = acc()
    if variant == 'filled':
        fill, text, outline = a, on_a, None
        hover, press = mix('#000000', a, 0.08), mix('#000000', a, 0.16)
    elif variant == 'tonal':
        fill, text, outline = a_c, on_a_c, None
        hover, press = mix('#000000', a_c, 0.06), mix('#000000', a_c, 0.12)
    elif variant == 'danger':
        fill, text, outline = COLORS['error_container'], COLORS['on_error_container'], None
        hover, press = mix('#000000', fill, 0.06), mix('#000000', fill, 0.12)
    elif variant == 'outlined':
        fill, text, outline = None, a, COLORS['outline']
        hover, press = mix(a, container, 0.08), mix(a, container, 0.14)
    else:                                              # text
        fill, text, outline = None, a, None
        hover, press = mix(a, container, 0.08), mix(a, container, 0.14)
    if state == 'disabled':
        ink = COLORS['on_surface']
        return (mix(ink, container, 0.12) if fill else None, mix(ink, container, 0.38),
                mix(ink, container, 0.12) if outline else None)
    if state == 'hover':
        fill = hover
    elif state == 'press':
        fill = press
    return fill, text, outline


class M3Button(tk.Label):
    """알약 단추. tk.Button 처럼 command, state, text 를 받는다.

    예전 단추가 넘기던 bg, fg, relief, font, padx, pady, cursor 같은 모양 옵션은 무시하고,
    bg 색으로 단추 종류(variant)만 짐작한다.
    """

    _images = {}                # 같은 모양은 한 번만 만든다 {(w, h, 바탕, 테두리, 쪽): PNG 글}

    def __init__(self, master, text='', command=None, variant=None, size='md', icon=None,
                 state='normal', **legacy):
        self._variant = variant or variant_from_legacy(legacy.get('bg'))
        self._size = size
        self._icon_name = icon
        self._command = command
        self.state_value = state
        self._hover = False
        self._press = False
        self._text = text
        self._container = container_bg(master)
        self._photo = None
        super().__init__(master, text=text, bd=0, highlightthickness=0, bg=self._container,
                         cursor='hand2', takefocus=1)
        self.bind('<Enter>', lambda _e: self._set_hover(True))
        self.bind('<Leave>', lambda _e: self._set_hover(False))
        self.bind('<ButtonPress-1>', lambda _e: self._set_press(True))
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Return>', lambda _e: self.invoke())
        self.bind('<space>', lambda _e: self.invoke())
        _all_buttons.add(self)
        self.render()

    def _base(self, **kw):
        """tk.Label 의 원래 configure. 테스트 스텁에는 없으므로 있을 때만 부른다."""
        original = getattr(tk.Label, 'configure', None)
        if original is not None and kw:
            original(self, **kw)

    # tk 의 configure/config/cget 을 가로채 state, command, text 를 다룬다
    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        again = False
        if 'state' in kw:
            self.state_value = kw.pop('state')
            again = True
        if 'command' in kw:
            self._command = kw.pop('command')
        if 'text' in kw:
            self._text = kw['text']
            again = True
        if 'variant' in kw:
            self._variant = kw.pop('variant')
            again = True
        for ignored in ('bg', 'fg', 'activebackground', 'activeforeground', 'disabledforeground',
                        'relief', 'font', 'padx', 'pady', 'cursor', 'bd', 'width', 'height',
                        'highlightthickness'):
            kw.pop(ignored, None)
        self._base(**kw)
        if again:
            self.render()

    config = configure

    def cget(self, key):
        if key == 'state':
            return self.state_value
        original = getattr(tk.Label, 'cget', None)
        return original(self, key) if original is not None else ''

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    def invoke(self):
        if self.state_value != 'disabled' and self._command:
            return self._command()

    # 눌림 처리
    def _set_hover(self, on):
        self._hover = on
        if not on:
            self._press = False
        self.render()

    def _set_press(self, on):
        if self.state_value != 'disabled':
            self._press = on
            self.render()

    def _release(self, event):
        was_pressed = self._press
        self._press = False
        self.render()
        try:
            inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        except Exception:
            inside = True
        if was_pressed and inside:
            self.invoke()

    # 그리기
    def _mode(self):
        if self.state_value == 'disabled':
            return 'disabled'
        if self._press:
            return 'press'
        return 'hover' if self._hover else 'normal'

    def render(self):
        fill, text_color, outline = _button_colors(self._variant, self._container, self._mode())
        height = px(40 if self._size == 'md' else 32)
        font = ft(10 if self._size == 'md' else 9, 'bold')
        cursor = 'arrow' if self.state_value == 'disabled' else 'hand2'
        if not HAVE_GLASS:
            self._base(text=self._text, fg=text_color, font=font, cursor=cursor,
                       bg=fill or self._container, padx=14, pady=6)
            return
        pad = px(22 if self._size == 'md' else 16)
        icon_size = height // 2
        icon_w = (icon_size + px(8)) if self._icon_name else 0
        text_w = measure(self, font, self._text)
        width = text_w + pad * 2 + icon_w
        key = (width, height, fill, outline, self._icon_name, text_color if self._icon_name else '')
        if key not in self._images:
            shape = glass.pill(width, height, fill=fill, outline=outline)
            if self._icon_name:
                # 글자는 가운데에 두고, 아이콘은 글자 바로 왼쪽에 놓는다
                mark = glass.icon(self._icon_name, icon_size, text_color)
                x = max(8, (width - text_w) // 2 - icon_size - 6)
                shape.alpha_composite(mark, (x, (height - mark.height) // 2))
            self._images[key] = glass.png_base64(shape, level=1)
        self._photo = tk.PhotoImage(master=self, data=self._images[key])
        self._base(image=self._photo, text=self._text, compound='center', fg=text_color,
                   activeforeground=text_color, activebackground=self._container,
                   font=font, cursor=cursor, bg=self._container, padx=0, pady=0)


# 도구를 바꾸면 단추 색도 바꾼다
_all_buttons = set()


def retheme_buttons():
    for button in list(_all_buttons):
        try:
            if button.winfo_exists():
                refresh_or_defer(button, button.render)
            else:
                _all_buttons.discard(button)
        except Exception:
            _all_buttons.discard(button)


# ── 카드 ─────────────────────────────────────────────────────────────

TONES = {
    'inner': (INNER_BG, COLORS['on_surface']),
    'field': ('#FFFFFF', COLORS['on_surface']),
    'warn': (COLORS['warn_container'], COLORS['on_warn_container']),
    'error': (COLORS['error_container'], COLORS['on_error_container']),
    'ok': (COLORS['ok_container'], COLORS['on_ok_container']),
}


class Card(tk.Frame):
    """둥근 카드. 안에 놓을 위젯은 card.body 에 붙인다.

    tk.Frame 은 모서리를 둥글게 할 수 없어서, 뒤에 둥근 그림 한 장을 깔고 그 위에 안쪽 틀을 올린다.
    안쪽 틀의 바탕이 카드 색(card.fill)이라, 안쪽 위젯은 bg=card.fill 을 쓰면 된다.
    """

    def __init__(self, master, tone='inner', pad=(16, 12), radius=None):
        self.tone = tone
        self.fill, self.ink = TONES.get(tone, TONES['inner'])
        self._radius = radius or (14 if tone == 'field' else 20)
        self._focused = False
        self._container = container_bg(master)
        self._pending = None
        self._drawn = None
        super().__init__(master, bg=self._container)
        self._back = tk.Label(self, bg=self._container, bd=0)
        self._back.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=self.fill)
        self.body.grid(row=0, column=0, sticky='nsew', padx=pad[0], pady=pad[1])
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._back.lower()
        if not HAVE_GLASS:
            self.configure(bg=self.fill)
            self._back.place_forget()
            return
        self.bind('<Configure>', self._on_size)
        self.bind('<Map>', self._on_size)

    def set_tone(self, tone):
        """카드 색을 바꾼다 (경고 배너가 확인 필요에서 오류로 바뀔 때). 안쪽 틀 바탕도 같이 바뀐다."""
        if tone == self.tone:
            return
        self.tone = tone
        self.fill, self.ink = TONES.get(tone, TONES['inner'])
        self.body.configure(bg=self.fill)
        for child in self.body.winfo_children():
            try:
                child.configure(bg=self.fill, fg=self.ink)
            except Exception:
                try:
                    child.configure(bg=self.fill)
                except Exception:
                    pass
        if not HAVE_GLASS:
            self.configure(bg=self.fill)
            return
        self._drawn = None
        self._on_size()

    def set_focus(self, focused):
        """입력칸에 커서가 들어오면 테두리를 강조색 2px 로."""
        if focused != self._focused:
            self._focused = focused
            self._drawn = None
            self._on_size()

    def _on_size(self, _event=None):
        if self._pending is not None:
            try:
                self.after_cancel(self._pending)
            except Exception:
                pass
        self._pending = self.after(8, self._draw)

    def _draw(self):
        self._pending = None
        try:
            if not self.winfo_viewable():        # 안 보이는 탭의 카드는 열릴 때 그린다
                _stale[self] = self._on_size
                return
            w, h = self.winfo_width(), self.winfo_height()
        except Exception:
            return
        if w < 8 or h < 8 or self._drawn == (w, h):
            return
        self._drawn = (w, h)
        if self._focused:
            edge, width = acc()[0], 2
        elif self.tone == 'field':
            edge, width = COLORS['outline'], 1
        elif self.tone == 'inner':
            edge, width = EDGE, 1
        else:
            edge, width = mix('#000000', self.fill, 0.08), 1
        image = glass.card_image(w, h, fill=self.fill, outline=edge, outline_width=width,
                                 radius=min(self._radius, h // 2))
        self._photo = photo(self, image)
        self._back.configure(image=self._photo)


# ── 칩 ───────────────────────────────────────────────────────────────

CHIP_KINDS = {
    'ok': (COLORS['ok_container'], COLORS['on_ok_container'], None),
    'warn': (COLORS['warn_container'], COLORS['on_warn_container'], None),
    'err': (COLORS['error_container'], COLORS['on_error_container'], None),
    'neutral': (None, COLORS['on_surface_variant'], COLORS['outline']),
}


class Chip(tk.Label):
    """작은 상태 칩. 색만으로 알리지 않도록 글자를 꼭 넣는다."""

    _images = {}

    def __init__(self, master, text='', kind='neutral'):
        self._container = container_bg(master)
        self._photo = None
        self._text = text
        self._kind = kind
        super().__init__(master, bd=0, highlightthickness=0, bg=self._container)
        _scalables.add(self)
        self.set(text, kind)

    def rescale(self):
        self.set(self._text, self._kind)

    def set(self, text, kind='neutral'):
        self._text, self._kind = text, kind
        if kind == 'info':
            fill, ink, outline = acc()[2], acc()[3], None
        else:
            fill, ink, outline = CHIP_KINDS.get(kind, CHIP_KINDS['neutral'])
        font = ft(9, 'bold')
        if not HAVE_GLASS:
            self.configure(text=text, fg=ink, font=font, bg=fill or self._container,
                           padx=8, pady=2)
            return
        width, height = measure(self, font, text) + px(20), px(26)
        key = (width, height, fill, outline)
        if key not in self._images:
            self._images[key] = glass.png_base64(
                glass.pill(width, height, fill=fill, outline=outline, radius=px(8)), level=1)
        self._photo = tk.PhotoImage(master=self, data=self._images[key])
        self.configure(image=self._photo, text=text, compound='center', fg=ink, font=font,
                       bg=self._container, padx=0, pady=0)


# ── 도구 선택 (소통픽 / 수신픽) ──────────────────────────────────────

class ToolSwitch(tk.Frame):
    """붙어 있는 두 알약. 고른 쪽이 강조색 연한 바탕에 체크 표시를 단다.

    두 쪽의 폭과 자리는 늘 같다. 체크 표시 자리를 양쪽에 미리 비워 두므로
    도구를 바꿔도 단추가 움직이지 않는다.
    """

    def __init__(self, master, items, on_select, width=0, height=0):
        self._container = container_bg(master)
        super().__init__(master, bg=self._container)
        self.items = {}
        self._keys = [key for key, _text in items]
        self._texts = dict(items)
        self._on_select = on_select
        self._width = width
        self._height = height
        self._selected = None
        for column, (key, _text) in enumerate(items):
            label = tk.Label(self, bd=0, highlightthickness=0, padx=0, pady=0,
                             bg=self._container, cursor='hand2')
            label.grid(row=0, column=column, padx=0, pady=0)
            label.bind('<Button-1>', lambda _e, k=key: self._on_select(k))
            self.items[key] = label
        _scalables.add(self)

    def rescale(self):
        if self._selected is not None:
            self.select(self._selected)

    def _fixed_width(self):
        """두 글자 가운데 긴 쪽에 체크 자리(양쪽)를 더한 폭. 고른 쪽과 상관없다."""
        if self._width:
            return self._width
        first = self.items[self._keys[0]]
        widest = max(measure(first, ft(10, 'bold'), text) for text in self._texts.values())
        return max(px(112), widest + 2 * px(38))

    def select(self, key):
        self._selected = key
        width, height = self._fixed_width(), self._height or px(40)
        a, _on_a, a_c, on_a_c = acc()
        for index, item_key in enumerate(self._keys):
            label = self.items[item_key]
            chosen = item_key == key
            side = 'left' if index == 0 else 'right'
            text = self._texts[item_key]
            font = ft(10, 'bold' if chosen else 'normal')
            ink = on_a_c if chosen else COLORS['on_surface']
            if not HAVE_GLASS:
                # 글자 수로 폭을 고정한다 (체크 자리는 늘 비워 둔다)
                label.configure(text=('\u2713 ' if chosen else '    ') + text, font=font, fg=ink,
                                bg=a_c if chosen else self._container, padx=0, pady=8,
                                width=max(len(t) for t in self._texts.values()) + 6)
                continue
            shape = glass.pill(width, height, fill=a_c if chosen else None,
                               outline=COLORS['outline'], sides=side)
            if chosen:
                mark = glass.icon('check', px(16), on_a_c)
                shape.alpha_composite(mark, (px(14), (height - mark.height) // 2))
            label._photo = photo(label, shape)
            label.configure(image=label._photo, text=text, compound='center', font=font, fg=ink,
                            bg=self._container, padx=0)


# ── 단계 레일 ────────────────────────────────────────────────────────

class RailItem(tk.Frame):
    """레일 한 칸. 아이콘 알약과 이름. 고른 칸은 강조색 연한 알약에 이름이 굵다."""

    def __init__(self, master, text, icon, command):
        self._container = container_bg(master)
        super().__init__(master, bg=self._container, cursor='hand2')
        self._icon = icon
        self._text = text
        self._selected = False
        self._pill = tk.Label(self, bd=0, highlightthickness=0, bg=self._container)
        self._pill.pack(pady=(8, 2))
        self._name = tk.Label(self, text=text, bg=self._container, font=ft(9),
                              fg=COLORS['on_surface_variant'], wraplength=px(80), justify='center')
        self._name.pack(pady=(0, 6))
        for widget in (self, self._pill, self._name):
            widget.bind('<Button-1>', lambda _e: command())
        _scalables.add(self)
        self.set_selected(False)

    def rescale(self):
        self._name.configure(wraplength=px(80))
        self.set_selected(self._selected)

    def set_selected(self, selected):
        self._selected = selected
        a, _on_a, a_c, on_a_c = acc()
        ink = on_a_c if selected else COLORS['on_surface_variant']
        self._name.configure(fg=COLORS['on_surface'] if selected else COLORS['on_surface_variant'],
                             font=ft(9, 'bold' if selected else 'normal'))
        if not HAVE_GLASS:
            self._pill.configure(text=self._text[:1], bg=a_c if selected else self._container,
                                 fg=ink, width=3)
            return
        shape = glass.pill(px(56), px(32), fill=a_c if selected else None)
        shape.alpha_composite(glass.icon(self._icon, px(20), ink), (px(18), px(6)))
        self._photo = photo(self._pill, shape)
        self._pill.configure(image=self._photo)

    def retheme(self):
        self.set_selected(self._selected)


# ── 입력 부품 ────────────────────────────────────────────────────────

def text_field(master, height=8, wrap='word', font=None, width=10, **kw):
    """둥근 입력 판 안의 tk.Text 와 스크롤바. (판, 글 상자) 를 돌려준다.

    판은 grid/pack 으로 놓고, 글 상자는 예전 그대로 get/insert/delete 로 쓴다.
    """
    card = Card(master, tone='field', pad=(8, 6))
    text = tk.Text(card.body, height=height, width=width, wrap=wrap, bd=0, highlightthickness=0,
                   relief='flat', bg='#FFFFFF', fg=COLORS['on_surface'],
                   insertbackground=COLORS['on_surface'], font=font or ft(10),
                   padx=6, pady=4, **kw)
    bar = ttk.Scrollbar(card.body, orient='vertical', command=text.yview)
    text.configure(yscrollcommand=bar.set)
    text.grid(row=0, column=0, sticky='nsew')
    bar.grid(row=0, column=1, sticky='ns')
    card.body.columnconfigure(0, weight=1)
    card.body.rowconfigure(0, weight=1)
    text.bind('<FocusIn>', lambda _e: card.set_focus(True))
    text.bind('<FocusOut>', lambda _e: card.set_focus(False))
    text.scrollbar = bar
    return card, text


def entry_field(master, textvariable=None, width=10, show=None):
    """둥근 한 줄 입력칸. (판, tk.Entry) 를 돌려준다."""
    card = Card(master, tone='field', pad=(12, 7))
    entry = tk.Entry(card.body, textvariable=textvariable, width=width, bd=0,
                     highlightthickness=0, relief='flat', bg='#FFFFFF',
                     fg=COLORS['on_surface'], insertbackground=COLORS['on_surface'],
                     font=ft(10), show=show or '')
    entry.grid(row=0, column=0, sticky='ew')
    card.body.columnconfigure(0, weight=1)
    entry.bind('<FocusIn>', lambda _e: card.set_focus(True))
    entry.bind('<FocusOut>', lambda _e: card.set_focus(False))
    return card, entry


def list_card(master, width=10, **options):
    """둥근 판 안의 tk.Listbox 와 스크롤바. (판, 목록) 을 돌려준다."""
    card = Card(master, tone='inner', pad=(8, 8))
    box = tk.Listbox(card.body, width=width, bd=0, highlightthickness=0, relief='flat', bg=INNER_BG,
                     fg=COLORS['on_surface'], activestyle='none', exportselection=False,
                     selectbackground=acc()[2], selectforeground=acc()[3], **options)
    bar = ttk.Scrollbar(card.body, orient='vertical', command=box.yview)
    box.configure(yscrollcommand=bar.set)
    box.grid(row=0, column=0, sticky='nsew')
    bar.grid(row=0, column=1, sticky='ns')
    card.body.columnconfigure(0, weight=1)
    card.body.rowconfigure(0, weight=1)
    return card, box


def retheme_lists(boxes):
    """도구를 바꾸면 목록의 선택 색도 강조색으로 바꾼다."""
    for box in boxes:
        try:
            box.configure(selectbackground=acc()[2], selectforeground=acc()[3])
        except Exception:
            pass
