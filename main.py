"""신통픽 — 소통메신저·에듀파인 수신자 한 번에

수신 + 소통. 명단을 읽어 충북 기관명으로 정리하는 파이프라인은 하나이고,
두 도구를 합친 것이다.

  수신픽 — 에듀파인 공문 수신그룹 일괄등록 엑셀을 만든다
  소통픽 — 소통메신저 [사용자 선택] 창에서 수신자를 자동으로 골라 담는다
"""

APP_NAME    = '신통픽'
APP_VERSION = '2.2.11'

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import json
import logging
import os
import re
import sys
import shutil
import webbrowser
import urllib.request

from app_config import (
    APP_DATA_DIR,
    Config,
    MAX_ORG_EXTRACT_HISTORY,
    TARGET_EDUFINE,
    TARGET_LABELS,
    TARGET_MESSENGER,
    TARGET_SUMMARIES,
    TARGET_SYSTEMS,
)
import edufine
from automation import (
    FAIL_DUPLICATE,
    FAIL_SAME_NAME_SKIPPED,
    count_message_for,
    search_count_in,
    guess_selected_list,
    pick_selected_list,
    person_rows,
    repeated_containers,
    row_texts,
    find_label,
    has_selected_label,
    selected_person_rows,
    uia_type_name,
    SELECTED_LABEL,
    FAIL_MANUAL_STOP,
    FAIL_NO_USER,
    FAIL_SEARCH_STALE,
    POPUP_WAIT_ADD,
    RESULT_SCAN_HEIGHT,
    RESULT_SCAN_WIDTH,
    RESULT_WAIT_MIN,
    failure_reason_from_error,
    looks_like_duplicate_popup,
    looks_like_result,
)
from hwp_extract import extract_hwp_text
import reconcile
from sotong_parser import (
    AUTO_GRADES,
    GRADE_AMBIGUOUS,
    parse_input,
    parse_orgs,
)
from ui_helpers import format_item_label
import ui_kit as ui
from ui_kit import M3Button, Card, Chip, RailItem, ToolSwitch
from theme import COLORS, FONT_FAMILY as FONT, PANEL_BG, fs, shell_layout

try:
    import glass
except ImportError:               # Pillow 가 없으면 유리 없이 색 면으로 그린다
    glass = None

# 도구마다 강조색이 다르다. 소통픽 = 남보라, 수신픽 = 청록.
THEME_TOOL = {TARGET_MESSENGER: 'sotong', TARGET_EDUFINE: 'susin'}
RAIL_ICONS = {'input': 'menu', 'calib': 'pin', 'auto': 'play', 'excel': 'file', 'help': 'help'}
# 창 틀 안쪽 틀이 둥근 판 모서리 밖으로 나가지 않게 판마다 안쪽으로 들인다 (좌, 상, 우, 하)
SHELL_INSET = {'top': (22, 4, 22, 4), 'rail': (6, 16, 6, 16),
               'body': (6, 16, 6, 16), 'status': (18, 3, 18, 3)}

LOG_FILE = os.path.join(APP_DATA_DIR, 'app.log')
# 소통메신저 [받는사람 추가] 를 누르면 뜨는 창의 제목
MESSENGER_DIALOG_TITLE = '사용자 선택'
LATEST_RELEASE_API = 'https://api.github.com/repos/codersongpro/susin/releases/latest'
RELEASES_PAGE = 'https://github.com/codersongpro/susin/releases/latest'
GUIDE_VIDEO_URLS = {
    TARGET_MESSENGER: 'https://youtu.be/shZnB5NRN5g',
    TARGET_EDUFINE: 'https://youtu.be/IcFX3UKdMEw',
}
try:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO, encoding='utf-8')
except OSError:
    # 로그를 못 써도 앱의 핵심 기능은 실행되어야 한다.
    logging.basicConfig(level=logging.INFO)

try:
    import pyautogui
    pyautogui.PAUSE = 0.3
    pyautogui.FAILSAFE = True
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    # 위치 캡처 때 창 밖에서 누른 Enter 를 받으려면 전역으로 키를 봐야 한다.
    import win32api
except ImportError:
    win32api = None

# 소통메신저가 결과 목록 위에 적어 두는 '검색 결과(2명)' 같은 글.
SEARCH_COUNT_RE = re.compile(r'검색\s*결과\s*\(?\s*(\d+)\s*명')

VK_LBUTTON = 0x01
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B


def key_is_down(vk_code):
    """다른 창이 떠 있어도 그 키가 지금 눌려 있는지 본다 (윈도우 전용)."""
    if win32api is None:
        return False
    try:
        return bool(win32api.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception as exc:
        logging.info('키 상태 확인 실패: %s', exc)
        return False

# ─────────────────────────────────────────────
#  CaptureDialog
# ─────────────────────────────────────────────

# 소통메신저에서 수신자를 담기까지 누르는 차례. 3·4·5 번이 신통픽이 기억해야 할
# 자리다. 사용자가 화면에서 바로 찾을 수 있게 같은 번호로 부른다.
MESSENGER_STEPS = (
    ('1', '편지 버튼', '소통메신저 오른쪽 위에 있습니다. 누르지 말고 마우스만 올리면 '
                      '아래로 메뉴가 펼쳐집니다.'),
    ('2', '[쪽지작성]', '펼쳐진 메뉴에서 누릅니다.'),
    ('3', '[받는사람 추가] 버튼', '누르면 [사용자 선택] 창이 열립니다.'),
    ('4', '검색 입력칸', "'소속+이름 또는 이름 검색' 이라고 적힌 칸입니다."),
    ('5', '검색 결과 첫 줄', "'검색 결과(1명)' 아래 첫 번째 사람입니다."),
    ('6', '오른쪽 화살표 버튼', '결과 목록과 [선택된 사용자] 사이에 있는 버튼입니다.'),
)

CAPTURE_HINTS = {
    'search_field': "4번  검색 입력칸  ('소속+이름 또는 이름 검색' 칸)",
    'result_first': "5번  검색 결과 첫 줄  ('검색 결과(1명)' 아래 첫 사람)",
    'add_button': '6번  오른쪽 화살표 버튼  (결과를 [선택된 사용자] 로 옮기는 버튼)',
}

EDUFINE_UPLOAD_STEPS = (
    ('1', '[개인설정]', '에듀파인 오른쪽 위에 있습니다.'),
    ('2', '[개인수신그룹관리]', '개인설정 화면의 왼쪽 메뉴에서 누릅니다.'),
    ('3', '[일괄등록]', '수신그룹 목록 위에 있습니다.'),
    ('4', '[찾아보기 ...]', '신통픽이 만든 엑셀을 골라 올립니다.'),
)

# 안내 그림 파일 이름. assets/guide/ 에 넣어 두면 화면에 함께 나오고,
# 없으면 글 안내만 나온다. tk 가 읽을 수 있게 PNG 로 둔다.
GUIDE_IMAGES = {
    '1': 'mail_button.png',
    '2': 'write_note.png',
    '3': 'add_recipient.png',
    '4': 'search_box.png',
    '5': 'first_result.png',
    '6': 'arrow_button.png',
}
# 에듀파인에 올리는 차례. 차례 번호가 소통메신저와 겹치므로 따로 둔다.
EDUFINE_GUIDE_IMAGES = {
    '1': 'edufine_settings.png',
    '2': 'edufine_group_menu.png',
    '3': 'edufine_bulk_upload.png',
    '4': 'edufine_browse.png',
}
CAPTURE_STEP_KEYS = {
    'search_field': '4',
    'result_first': '5',
    'add_button': '6',
}
_guide_image_cache = {}


def _load_guide_image(name: str):
    """assets/guide/ 의 PNG 한 장. 파일이 없거나 못 읽으면 None."""
    if not name:
        return None
    if name in _guide_image_cache:
        return _guide_image_cache[name]
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, 'assets', 'guide', name)
    image = None
    if os.path.exists(path):
        try:
            image = tk.PhotoImage(file=path)
        except Exception as exc:
            logging.info('안내 그림을 읽지 못했습니다 (%s): %s', name, exc)
    _guide_image_cache[name] = image
    return image


def guide_image(step: str):
    """소통메신저에서 누르는 차례의 안내 그림."""
    return _load_guide_image(GUIDE_IMAGES.get(step))


def edufine_guide_image(step: str):
    """에듀파인에 올리는 차례의 안내 그림."""
    return _load_guide_image(EDUFINE_GUIDE_IMAGES.get(step))


def make_scrollable(parent):
    """세로로 길어지는 탭을 스크롤할 수 있게 감싼다.

    안내 그림이 들어가면서 [설정 저장] 버튼이 창 밖으로 밀려났다. 창을 키우지
    않아도 아래까지 닿아야 한다. 위젯은 돌려주는 안쪽 틀에 붙인다.
    """
    canvas = tk.Canvas(parent, highlightthickness=0)
    bar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
    inner = tk.Frame(canvas)
    window = canvas.create_window((0, 0), window=inner, anchor='nw')
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side='left', fill='both', expand=True)

    def overflows() -> bool:
        return inner.winfo_reqheight() > canvas.winfo_height()

    def show_bar():
        """넘칠 때만 스크롤바를 내놓는다. 평소에는 자리를 차지하지 않는다."""
        try:
            if overflows():
                if not bar.winfo_ismapped():
                    bar.pack(side='right', fill='y')
            elif bar.winfo_ismapped():
                bar.pack_forget()
        except tk.TclError as exc:
            logging.debug('스크롤바 표시 갱신 실패: %s', exc)

    def fit_scrollregion(_event=None):
        try:
            canvas.configure(scrollregion=canvas.bbox('all'))
        except tk.TclError as exc:
            logging.debug('스크롤 범위 갱신 실패: %s', exc)
        show_bar()

    def fit_size(event):
        try:
            canvas.itemconfigure(window, width=event.width)
            # 내용이 짧으면 캔버스 높이에 맞춰 늘린다. 그래야 명단과 로그가
            # 예전처럼 창 끝까지 찬다. 넘칠 때만 제 높이로 두고 스크롤한다.
            short = inner.winfo_reqheight() < event.height
            canvas.itemconfigure(window, height=event.height if short else 0)
        except tk.TclError as exc:
            logging.debug('스크롤 크기 갱신 실패: %s', exc)
        show_bar()

    def on_wheel(event):
        try:
            if overflows():
                canvas.yview_scroll(int(-event.delta / 120), 'units')
        except tk.TclError as exc:
            logging.debug('휠 스크롤 실패: %s', exc)

    inner.bind('<Configure>', fit_scrollregion)
    canvas.bind('<Configure>', fit_size)
    # 휠은 마우스가 이 탭 위에 있을 때만 받는다. 다른 목록의 휠을 뺏지 않는다.
    canvas.bind('<Enter>', lambda _e: canvas.bind_all('<MouseWheel>', on_wheel))
    canvas.bind('<Leave>', lambda _e: canvas.unbind_all('<MouseWheel>'))
    return inner


class CaptureDialog(tk.Toplevel):
    def __init__(self, parent, on_captured, label='위치', hint='', step=''):
        super().__init__(parent)
        self.on_captured = on_captured
        self._finished = False
        self._enter_released = False
        self._click_released = False
        self.title('위치 캡처')
        # 크기를 못 박지 않는다. 그림이 붙으면 내용이 길어져 버튼이 창 밖으로
        # 밀려났다. 내용에 맞춰 잡고, 사용자가 늘릴 수도 있게 둔다.
        self.resizable(True, True)

        tk.Label(
            self, text=f'캡처 대상: {label}',
            bg=ui.acc()[2], fg=ui.acc()[3], font=ui.font(12, 'bold'), pady=12
        ).pack(fill='x')

        if hint:
            tk.Label(
                self, text=f'소통메신저에서 이 부분을 클릭하세요.\n{hint}',
                bg=ui.acc()[2], fg=ui.acc()[3], font=ui.font(11, 'bold'),
                justify='center', pady=10
            ).pack(fill='x')

        # 그림이 있으면 무엇을 누르는지 눈으로 바로 보여 준다.
        self.hint_image = guide_image(step) if step else None
        if self.hint_image is not None:
            tk.Label(self, image=self.hint_image, bg=ui.acc()[2]).pack(
                fill='x', pady=(0, 6))

        tk.Label(
            self,
            text='[캡처 시작] 을 누른 뒤 위에 적힌 자리를 클릭하면 저장됩니다.\n'
                 '마우스를 옮긴 뒤 Enter 로 확정해도 되고, Esc 로 취소합니다.',
            font=ui.font(10), justify='center', padx=24, pady=10
        ).pack()

        if step == '6':
            # 이 클릭은 소통메신저에서 실제로 사람을 담는다. 그때만 알린다.
            tk.Label(
                self,
                text='이 버튼을 누르면 그 사람이 실제로 추가됩니다.\n'
                     '캡처를 마친 뒤 받는 사람 목록을 확인하세요.',
                font=ui.font(9), justify='center', fg=COLORS['error']
            ).pack()

        self.status = tk.Label(
            self, text='아래 버튼을 클릭하여 캡처를 시작하세요.',
            font=ui.font(11, 'bold'), fg=COLORS['warn']
        )
        self.status.pack(pady=6)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        self.start_btn = M3Button(btn_frame, text='캡처 시작', command=self._begin)
        self.start_btn.pack(side='left', padx=6)
        M3Button(btn_frame, text='취소', command=self.destroy, variant='text').pack(side='left', padx=6)

        # 내용을 다 붙인 뒤 그 크기에 맞춘다. 버튼이 잘리지 않아야 한다.
        try:
            self.update_idletasks()
            self.minsize(max(440, self.winfo_reqwidth()), self.winfo_reqheight())
        except tk.TclError as exc:
            logging.debug('캡처 창 크기 조정 실패: %s', exc)

    def _begin(self):
        self.start_btn.config(state='disabled')
        self.status.config(text='잡을 자리를 클릭하세요.  Enter 로도 확정 / Esc 취소')
        self.bind('<Return>', lambda _e: self._confirm())
        self.bind('<Escape>', lambda _e: self.destroy())

        # 캡처 창은 처음부터 grab_set()을 사용하지 않는다. 사용자가 외부
        # 소통메신저를 눌러야 하기 때문이다. 혹시 이전 이벤트가 grab을 남겼다면
        # 시작 시 한 번 더 해제한다.
        self._release_grab()
        # 소통메신저가 앞에 나와도 좌표는 계속 보여야 한다.
        try:
            self.attributes('-topmost', True)
        except tk.TclError as exc:
            logging.info('캡처 창 항상 위 설정 실패: %s', exc)
        try:
            self.focus_force()
        except tk.TclError as exc:
            logging.info('캡처 창 포커스 실패: %s', exc)

        # 버튼을 Enter 로 눌렀다면 그 Enter 가 아직 눌린 채다. 한 번 떼기 전에는
        # 확정으로 치지 않는다. [캡처 시작] 을 누른 마우스 버튼도 마찬가지다.
        self._enter_released = not key_is_down(VK_RETURN)
        self._click_released = not key_is_down(VK_LBUTTON)
        self._finished = False
        self._poll_position()

    def _release_grab(self):
        try:
            self.grab_release()
        except tk.TclError as exc:
            logging.info('캡처 창 grab 해제 실패: %s', exc)

    def _poll_position(self):
        if self._finished or not self.winfo_exists():
            return
        pos = pyautogui.position()
        self.status.config(
            text=f'현재 위치: ({pos.x}, {pos.y})  클릭하면 확정 / Esc 취소')

        # 소통메신저가 앞에 나와 있어도 클릭과 Enter 가 먹어야 한다.
        if key_is_down(VK_ESCAPE):
            self.destroy()
            return
        if key_is_down(VK_LBUTTON):
            if self._click_released:
                # 누르는 순간의 자리를 잡는다. 떼기를 기다리면 그새 마우스가
                # 움직여 엉뚱한 자리가 저장된다.
                self._done(pos)
                return
        else:
            self._click_released = True
        if key_is_down(VK_RETURN):
            if self._enter_released:
                self._confirm()
                return
        else:
            self._enter_released = True

        # 클릭을 놓치지 않으려면 자주 봐야 한다.
        self.after(40, self._poll_position)

    def _confirm(self):
        if self._finished:
            return
        self._done(pyautogui.position())

    def _done(self, pos):
        self._finished = True
        self._release_grab()
        # 닫는 예약을 먼저 건다. 좌표를 넘기다 에러가 나도 창이 남아서
        # 앱 전체가 멈추는 일이 없어야 한다.
        self.after(1200, self.destroy)
        try:
            self.status.config(text=f'✓ 캡처 완료: ({pos.x}, {pos.y})', fg=COLORS['ok'])
        except tk.TclError as exc:
            logging.info('캡처 완료 표시 실패: %s', exc)
        try:
            self.on_captured(pos.x, pos.y)
        except Exception as exc:
            logging.exception('캡처 좌표 저장 실패: %s', exc)

    def destroy(self):
        self._finished = True
        self._release_grab()
        super().destroy()


# ─────────────────────────────────────────────
#  도움말 텍스트
# ─────────────────────────────────────────────
_HELP_TEXT = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {APP_NAME}  v{APP_VERSION}  (소통메신저와 에듀파인 수신자 선택)
  처음 쓰시는 분도 따라 할 수 있게 순서대로 적었습니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ 이 프로그램이 하는 일
──────────────────────────────────────────────────────
  붙여넣은 명단을 충북 기관명으로 맞춘 뒤, 두 가지 중 하나로 씁니다.

    수신픽   에듀파인 개인수신그룹 일괄등록 엑셀을 만듭니다.
    소통픽   소통메신저 [사용자 선택] 창에서 수신자를 자동으로 담습니다.

  창 맨 위에서 수신픽과 소통픽 중 쓸 쪽을 고릅니다.
  고른 쪽에 필요한 단계만 왼쪽에 남습니다.

  소통픽은 이름마다 아래 세 가지를 반복합니다.

    1. 검색 입력칸에 이름을 넣고 검색합니다.
    2. 검색 결과 첫 번째 줄을 누릅니다.
    3. 오른쪽 화살표 버튼을 눌러 받는 사람에 추가합니다.

  검색 결과가 없는 사람은 빨간 항목으로 남습니다.

  다 끝나면 소통메신저 [선택된 사용자] 를 읽어 소통픽 명단과 맞춰 봅니다.
  들어간 사람, 빠진 사람, 소통메신저에만 있는 사람을 나눠 보여 줍니다.
  스크롤해야 보이는 아래쪽 사람까지 읽습니다.
  빠진 사람이 있으면 [누락된 N명 소통메신저에 추가] 를 누르세요.
  그 사람들만 다시 담고, 다 담은 뒤 다시 맞춰 봅니다.
  [소통메신저와 비교] 를 누르면 언제든 다시 맞춰 볼 수 있습니다.

  소통메신저 목록에는 학교 이름이 나오지 않아서 이름으로 맞춥니다.
  같은 이름이 명단에 여럿인데 일부만 들어 있으면 누가 들어갔는지 알 수 없으므로,
  이름마다 '(동명이인 2명 중 1명만 들어감, 확인 필요)' 를 붙여 따로 보여 줍니다.
  모두 들어 있으면 문제가 없는 것으로 보고 넘어갑니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 시작하기 전에
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. 소통메신저에 로그인합니다.
  2. 오른쪽 위 편지 버튼에 마우스를 올리고 [쪽지작성] 이나 [대화하기] 를 누릅니다.
  3. 메시지 작성 화면에서 [사용자 선택] 버튼을 누릅니다.
  4. 사용자 선택 창 위쪽에서 [전체조직] 탭을 엽니다.
  5. 소통메신저 창과 {APP_NAME} 창을 나란히 놓으면 편합니다.

  실행 중에는 마우스를 움직이지 마세요.
  급히 멈추려면 마우스를 화면 왼쪽 위 모서리로 빠르게 옮기거나 [중지] 를 누릅니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 명단 입력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  명단은 세 가지 방법 중 편한 쪽으로 넣습니다.

  [ 방법 A ]  파일 열기
    1. [엑셀 파일 열기] 나 [한글 파일 열기] 를 누릅니다.
    2. 파일을 고르면 입력창에 내용이 들어옵니다.
    3. [명단 추출] 을 누릅니다.

  [ 방법 B ]  복사해서 붙여넣기
    1. 엑셀이나 한글에서 소속기관과 이름이 있는 칸을 고르고 Ctrl+C 로 복사합니다.
    2. 입력창을 누르고 Ctrl+V 로 붙여넣습니다.
    3. [명단 추출] 을 누릅니다.

  [ 방법 C ]  직접 넣기
    목록 맨 아래 '직접 넣기' 칸에 적고 Enter 를 누르면 명단에 더해집니다.
    소통픽은 '학성초 송동석', 수신픽은 '청주교육지원청 행정과' 처럼 적습니다.
    쉼표로 나누면 여럿을 한 번에 넣을 수 있고, 이미 있는 것은 다시 넣지 않습니다.

  소통픽과 수신픽의 명단은 따로 보관됩니다.
    도구를 바꿔도 각자 넣어 둔 입력 글과 명단이 그대로 남습니다.
    앱을 닫으면 지워집니다. 사람 이름을 PC 에 남기지 않기 위해서입니다.

  추출 결과 목록은 이렇게 고칠 수 있습니다.
    · 항목을 더블클릭하면 소속기관과 이름을 직접 고칩니다.
    · Delete 키나 [선택 항목 삭제] 로 고른 항목을 지웁니다.
    · 빨간 항목은 자동으로 담지 못했거나 확인이 필요한 항목입니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 위치 설정 (처음 한 번만)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  소통메신저에서 클릭할 자리 세 곳을 {APP_NAME}에 알려 주는 단계입니다.
  한 번 저장해 두면 다음에도 그대로 씁니다.

  소통메신저에서 누르는 차례는 아래와 같습니다.
    1번  편지 버튼             오른쪽 위에 있습니다. 누르지 말고 마우스만 올리면
                              아래로 메뉴가 펼쳐집니다.
    2번  [쪽지작성]            펼쳐진 메뉴에서 누릅니다.
    3번  [받는사람 추가] 버튼   누르면 [사용자 선택] 창이 열립니다.
    4번  검색 입력칸            '소속+이름 또는 이름 검색' 칸입니다.
    5번  검색 결과 첫 줄        '검색 결과(1명)' 아래 첫 사람입니다.
    6번  오른쪽 화살표 버튼     결과를 [선택된 사용자] 로 옮기는 버튼입니다.

  이 가운데 4번, 5번, 6번 자리를 신통픽에 알려 주면 됩니다.

  자리를 잡는 방법은 모두 같습니다.
    [다시 잡기] 를 누르고 [캡처 시작] 을 누른 뒤, 소통메신저에서 그 자리를 클릭합니다.
    클릭하는 대신 마우스를 옮기고 Enter 를 눌러도 확정되고, Esc 를 누르면 취소됩니다.
    클릭은 소통메신저에도 전달되므로, 6번을 잡을 때는 그 사람이 실제로 추가됩니다.
    캡처를 마친 뒤 받는 사람 목록을 확인하세요.

  [ 4번 ]  검색 입력칸
    '소속+이름 또는 이름 검색' 칸을 클릭합니다.

  [ 5번 ]  검색 결과 첫 줄
    아무 이름(예: 홍길동)이나 검색해 결과가 뜬 상태에서
    '검색 결과(1명)' 아래 첫 사람을 클릭합니다.

  [ 6번 ]  오른쪽 화살표 버튼
    결과가 보이는 상태에서
    결과 목록과 [선택된 사용자] 사이의 화살표 버튼을 클릭합니다.

  [ 검색 설정 ]
    · 검색 후 대기 시간: 기본값은 0.5초입니다. 화면이 느리면 1.0~2.0초로 늘립니다.
    · 수동 확인 모드: 동명이인이 걱정될 때 켭니다.
      사람마다 검색 결과를 직접 확인하고 [계속] 을 눌러야 다음으로 넘어갑니다.

  마지막에 [설정 저장] 을 눌러 저장하세요.
  세 곳이 모두 '설정됨' 이 되면 [다음, 자동 선택] 이 켜집니다. 이 단추를 눌러도 설정이 저장되고
  바로 자동 선택으로 넘어갑니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 자동 선택
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. 소통메신저 [사용자 선택] 창에서 [전체조직] 탭을 열어 둡니다.
  2. {APP_NAME}의 [자동 선택] 탭에서 [자동 선택 시작] 을 누릅니다.
  3. 명단의 이름마다 검색, 결과 첫 줄 클릭, 화살표 버튼 클릭이 차례로 실행됩니다.
     진행 상황은 로그에 한 줄씩 올라옵니다.
       ✓  추가됨
       이유가 적힌 줄  담지 못함 (검색 결과 없음 등)
  4. 끝나면 담긴 사람 수와 빠진 사람 수가 나옵니다.

  급히 멈추려면 마우스를 화면 왼쪽 위 모서리로 빠르게 옮기거나 [중지] 를 누릅니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 자주 묻는 질문
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Q. 소속기관이 '소속없음'으로 표시돼요.
  A. 소속기관 이름을 알아보지 못한 경우입니다.
     목록에서 그 항목을 더블클릭해 직접 고치세요.

  Q. 프로그램이 엉뚱한 위치를 클릭해요.
  A. 소통메신저 창을 옮기셨을 수 있습니다.
     [위치 설정] 탭에서 세 곳을 다시 잡고 저장하세요.

  Q. 검색은 됐는데 추가가 안 돼요.
  A. 6번 자리(오른쪽 화살표 버튼)가 잘못 잡혔을 수 있습니다.
     그 자리를 다시 잡고 저장하세요.

  Q. 검색 결과가 아예 없어요.
  A. 소통메신저에 등록되지 않은 사용자입니다.
     그 항목은 로그에 '사용자 없음' 으로 남고 목록에서 빨간색이 됩니다.

  Q. 너무 빨라서 오류가 나요.
  A. [위치 설정] 탭에서 '검색 후 대기 시간'을 늘리세요.
     화면이 느린 컴퓨터는 1.0~2.0초를 권합니다.

  Q. 동명이인이 있어서 걱정돼요.
  A. 검색 결과가 두 명을 넘으면 신통픽이 첫 사람을 누르지 않고 멈춥니다.
     화면 왼쪽 위에 뜨는 작은 창을 보고 맞는 분을 직접 골라 화살표를 누른 뒤
     [계속] 을 누르세요. 아무도 담지 않으려면 [건너뛰기] 를 누릅니다.
     모든 사람마다 멈추고 싶으면 '수동 확인 모드'를 켜세요.

  Q. HWP 파일이 안 열려요.
  A. 한/글이 설치되어 있지 않으면 일부 파일이 열리지 않습니다.
     한글에서 표를 Ctrl+C 로 복사해 입력창에 Ctrl+V 로 붙여넣으세요.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 수신픽: 에듀파인 수신그룹 일괄등록
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  공문 수신 기관이 30곳이면 조직도에서 검색하고, 체크하고, [>>] 를 누르는 일을
  30번 반복해야 합니다. 타이핑 1800글자, 클릭 120번입니다.

  에듀파인에는 [개인설정] 의 [개인수신그룹관리] 에 [일괄등록] 이 있습니다.
  엑셀 한 장을 올리면 수신그룹이 한꺼번에 만들어지고,
  다음부터는 기안할 때 [수신자 지정] 의 [개인수신그룹] 에서 그룹 하나만 고르면 됩니다.
  클릭 120번이 2번으로 줄어듭니다.

  {APP_NAME}은 그 엑셀을 만들어 줍니다.


  1. 내 정보 넣기 (처음 한 번만)
  ──────────────────────────────────────────────────────
    [수신그룹 엑셀] 탭의 '내 정보'에 적습니다.

      사용자ID   에듀파인 로그인 ID
      사용자명   결재선에 나오는 이름

    등록교육청은 충청북도교육청으로 자동 적용됩니다.
    한 번 넣으면 저장되어 다음부터는 적지 않아도 됩니다.


  2. 기관 명단 넣기
  ──────────────────────────────────────────────────────
    [명단 입력] 탭에 기관 명단을 붙여넣습니다.
    줄바꿈, 쉼표, 탭 어느 것으로 나눠도 되고 글머리기호와 번호는 떼고 읽습니다.
    몇 곳뿐이면 목록 아래 '직접 넣기' 칸에 기관명을 적고 Enter 를 눌러도 됩니다.

      학성초
      한천초, 백곡초
      1. 충북외고

    [명단 추출] 을 누르면 기관이 네 가지로 나뉩니다.

      확정              그대로 씁니다.
      같은 이름이 여럿  '행정과' 처럼 같은 이름이 여러 곳에 있는 경우입니다.
      추정              이름이 비슷해서 짐작만 한 경우입니다.
      찾지 못함         사전에 없는 이름입니다.

    확정이 아닌 것은 더블클릭해서 후보 중에서 고릅니다.
    추정 상태로는 엑셀에 들어가지 않습니다.
    엑셀은 올리면 그대로 등록되므로, 틀린 기관이 들어가지 않게 막아 둡니다.

    확인이 필요한 기관은 붉은색으로 표시됩니다.
    [확인 필요 기관 일괄 수정] 을 누르면 한 창에서 차례로 고칠 수 있습니다.
    같은 기관을 여러 번 넣으면 기관명과 입력 횟수를 알려 주고 한 번만 남깁니다.
    [추출 기록 보기] 에서는 최근 30회의 추출 결과를 다시 볼 수 있습니다.


  3. 부서에 보내려면
  ──────────────────────────────────────────────────────
    교육청, 교육지원청, 직속기관의 부서도 수신자로 고를 수 있습니다.
    다만 학교와 달리 이름 하나로는 한 곳을 정하지 못할 때가 있습니다.

      정책기획과              한 곳뿐이라 바로 확정됩니다.
      행정과                  11곳에 있어서 확정하지 않고 후보에서 고르게 합니다.
      청주교육지원청 행정과    상위 기관을 같이 적어서 한 곳으로 좁혀집니다.
      단재교육연수원 교육연수부  세 단계로 적어도 됩니다.

    전체 경로를 외울 필요는 없습니다.
    [기관 찾아보기] 를 누르면 770곳을 검색해서 고를 수 있습니다.
    찾을 말을 띄어쓰기로 나눠 적으면 모두 포함된 곳만 보입니다.

      예)  청주 초등학교   ·   행정과   ·   단재 연수부

    부서는 엑셀로 올리는 쪽이 안전합니다.
    좌표로 자동 선택하는 방식은 조직명 칸에 '행정과' 를 쳐서 첫 결과를 고르기 때문에,
    여러 곳에 있는 부서 이름에서는 엉뚱한 곳이 잡힐 수 있습니다.


  4. 엑셀 만들어 올리기
  ──────────────────────────────────────────────────────
    [수신그룹 엑셀] 탭의 '수신그룹 만들기'에 그룹명을 적고
    [수신그룹 엑셀 만들기] 를 누릅니다.

    그룹명은 에듀파인에서 나중에 찾기 쉬운 이름으로 적습니다.
    예) 2026 진천 초등학교, 2학기 업무담당자
    그룹기호는 선택 사항이라 필요 없으면 비워 둡니다.

    코드가 없는 기관이 있으면 목록으로 알려 줍니다. 말없이 빠지는 기관은 없습니다.
    그런 기관은 [코드 없는 기관 순차 복사] 로 조직도에 직접 넣으면 됩니다.

    엑셀을 만들면 파일을 다시 열어서, 추출한 기관 수와 실제로 써진 줄 수를
    맞춰 보여 줍니다. 빠진 기관은 사유와 함께 나옵니다.
    에듀파인에 올린 뒤 수신그룹에 보이는 기관 수를 적으면 모자란지도 알려 줍니다.
    창을 닫았다면 [결과 대조] 로 다시 엽니다.

    만든 엑셀은 에듀파인에 올립니다. 누르는 차례는 아래와 같습니다.

      1) [개인설정]            에듀파인 오른쪽 위에 있습니다.
      2) [개인수신그룹관리]    개인설정 화면의 왼쪽 메뉴입니다.
      3) [일괄등록]            수신그룹 목록 위에 있습니다.
      4) [찾아보기 ...]        신통픽이 만든 엑셀을 골라 올립니다.

    각 버튼의 모양은 [수신그룹 엑셀] 탭 아래쪽에 그림으로 붙여 두었습니다.

    처음에는 기관 두세 곳으로 시험 그룹을 하나 만들어 올려 보세요.

  5. 코드 없는 기관 순차 복사
  ──────────────────────────────────────────────────────
    기관명을 한 건씩 클립보드에 넣어 줍니다.
    조직명 칸에 Ctrl+V 로 붙여넣고 Enter, 체크, [>>] 를 차례로 누르는 일만 반복하면 됩니다.
    Enter 키로 다음 기관으로 넘어갑니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 만든 사람
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Developed by  송동석(Dustin)
  Teacher / App developer / Data analyst
  문의와 의견:  dungst.me@gmail.com

  {APP_NAME}  |  버전 v{APP_VERSION}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


_HELP_EDUFINE_MARKER = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 수신픽: 에듀파인 수신그룹 일괄등록
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
_sotong_help, _susin_help = _HELP_TEXT.split(_HELP_EDUFINE_MARKER, 1)
_SOTONG_HELP_TEXT = _sotong_help.replace(
    f'{APP_NAME}  v{APP_VERSION}  (소통메신저와 에듀파인 수신자 선택)',
    f'소통픽 사용법  v{APP_VERSION}  (소통메신저 수신자 자동 선택)',
    1,
).rstrip()
_SUSIN_HELP_TEXT = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  수신픽 사용법  v{APP_VERSION}  (에듀파인 수신그룹 엑셀 만들기)
  처음 쓰시는 분도 따라 할 수 있게 순서대로 적었습니다.
{_HELP_EDUFINE_MARKER}
{_susin_help.lstrip()}"""

HELP_TEXTS = {
    TARGET_MESSENGER: _SOTONG_HELP_TEXT,
    TARGET_EDUFINE: _SUSIN_HELP_TEXT,
}


GUIDE_STEPS = {
    TARGET_MESSENGER: [
        ('input', 'input_text', '명단을 넣으세요',
         '소속기관과 이름이 들어 있는 표를 이 입력창에 붙여넣으세요.\n'
         '엑셀·HWP 파일을 여는 방법도 사용할 수 있습니다.'),
        ('input', 'parse_button', '명단을 추출하세요',
         '명단을 넣은 뒤 [명단 추출]을 누르세요.\n'
         '표에 섞인 직위·연락처·번호는 자동으로 걸러냅니다.'),
        ('input', 'parsed_list', '추출 결과를 확인하세요',
         '소속없음이나 이름 오류가 있으면 항목을 더블클릭해 고칩니다.\n'
         '동명이인이 있으면 수동 확인 모드를 사용하는 편이 안전합니다.'),
        ('calib', 'calibration_panel', '클릭할 위치 세 곳을 잡으세요',
         '검색 입력창, 결과 첫 번째 행, 사용자 선택 버튼을 차례로 설정합니다.\n'
         '소통메신저 창을 옮겼다면 위치를 다시 잡아야 합니다.'),
        ('auto', 'start_button', '자동 선택을 시작하세요',
         '소통메신저 [사용자 선택] 창에서 [전체조직] 탭을 먼저 열어 두세요.\n'
         '[자동 선택 시작]을 누르면 명단을 한 명씩 검색합니다.\n'
         '처음에는 수동 확인 모드로 2~3명만 시험해 보세요.'),
    ],
    TARGET_EDUFINE: [
        ('input', 'input_text', '기관 명단을 넣으세요',
         '기관명을 이 입력창에 줄바꿈·쉼표·탭으로 구분해 붙여넣습니다.\n'
         '예: 학성초, 충북외고, 청주교육지원청 행정과'),
        ('input', 'parse_button', '기관을 추출하세요',
         '[명단 추출]을 눌러 입력한 기관을 충북 기관명과 맞춥니다.'),
        ('input', 'parsed_list', '추출 결과를 확인하세요',
         '같은 이름이 여럿이거나 추정된 기관을 확인합니다.\n'
         '확인이 필요한 항목은 더블클릭해 정확한 기관을 고르세요.'),
        ('input', 'bulk_fix_button', '붉은 기관을 한 번에 수정하세요',
         '확인이 필요한 기관은 붉은색으로 표시됩니다.\n'
         '[확인 필요 기관 일괄 수정]을 누르면 한 창에서 차례로 확정하거나 제외할 수 있습니다.'),
        ('edufine', 'edufine_me_panel', '내 정보를 한 번만 입력하세요',
         '에듀파인 사용자ID와 사용자명을 입력합니다.\n'
         '등록교육청은 충청북도교육청으로 자동 적용됩니다.'),
        ('edufine', 'edufine_group_panel', '수신그룹 이름을 정하세요',
         '그룹명은 나중에 찾기 쉬운 이름으로 적습니다.\n'
         '예: 2026 진천 초등학교, 2학기 업무담당자\n'
         '그룹기호는 선택 사항이라 비워 둬도 됩니다.'),
        ('edufine', 'edufine_make_button', '엑셀을 만들고 올리세요',
         '[수신그룹 엑셀 만들기]를 눌러 파일을 저장합니다.\n'
         '에듀파인 [개인설정 > 개인수신그룹관리 > 일괄등록]에서 올리면 됩니다.'),
    ],
}


# ─────────────────────────────────────────────
#  App
# ─────────────────────────────────────────────


def _version_parts(version: str) -> tuple:
    version = (version or '').strip().lstrip('vV')
    parts = []
    for part in version.split('.'):
        digits = ''.join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def _is_newer_version(latest: str, current: str) -> bool:
    latest_parts = _version_parts(latest)
    current_parts = _version_parts(current)
    size = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (size - len(latest_parts))
    current_parts += (0,) * (size - len(current_parts))
    return latest_parts > current_parts

def copy_text(widget, text: str) -> bool:
    """클립보드에 넣는다. pyperclip 이 안 되면 tk 클립보드로 넘어간다."""
    try:
        if pyperclip is not None:
            pyperclip.copy(text)
        else:
            raise RuntimeError('pyperclip 없음')
    except Exception as exc:
        logging.info('명단 복사에 tk 클립보드를 씁니다: %s', exc)
        try:
            widget.clipboard_clear()
            widget.clipboard_append(text)
        except tk.TclError as tcl_exc:
            logging.warning('명단 복사 실패: %s', tcl_exc)
            return False
    return True


class ResultReport(tk.Toplevel):
    """추출한 수와 실제로 들어간 수를 나란히 보여 주고, 빠진 것을 알려 주는 창.

    소통픽은 소통메신저 [선택된 사용자] 목록을 센 수와, 수신픽은 에듀파인 수신그룹에 보이는
    기관 수와 한 번 더 맞춰 볼 수 있다. 그 수를 앱이 읽었으면 미리 채워 둔다.
    """

    def __init__(self, parent, tally, *, unit, who, where, count_label, into,
                 shown_count=None, base_count=0, note='', on_retry=None,
                 title='결과 대조'):
        super().__init__(parent)
        self.tally = tally
        self.unit = unit
        self.who = who
        self.where = where
        self.base_count = base_count or 0
        self.on_retry = on_retry
        self.title(title)
        self.geometry(f'{ui.px(600)}x{ui.px(660)}')
        ok = tally.short == 0
        bg = PANEL_BG
        self.configure(bg=bg)

        head = (f'✓  {tally.total}{unit}이 {into} 모두 들어갔습니다' if ok else
                f'{tally.total}{unit} 중 {tally.short}{unit}이 {into} 들어가지 않았습니다')
        tk.Label(
            self, text=head, bg=COLORS['ok_container'] if ok else COLORS['error_container'],
            fg=COLORS['on_ok_container'] if ok else COLORS['on_error_container'],
            font=ui.font(12, 'bold'), pady=10
        ).pack(fill='x')

        tk.Label(
            self, text=reconcile.summary_line(tally, unit), bg=bg, fg=COLORS['on_surface'],
            font=ui.font(10, 'bold'), justify='left'
        ).pack(anchor='w', padx=12, pady=(10, 2))
        if note:
            tk.Label(self, text=note, bg=bg, fg='#555', font=ui.font(9),
                     justify='left', wraplength=ui.px(520)).pack(anchor='w', padx=12)

        # 받는 쪽 화면의 수와 대조
        check = tk.Frame(self, bg=bg)
        check.pack(fill='x', padx=12, pady=(10, 2))
        tk.Label(check, text=count_label, bg=bg, font=ui.font(9)).pack(side='left')
        self.count_var = tk.StringVar(
            value='' if shown_count is None else str(shown_count))
        entry = tk.Entry(check, textvariable=self.count_var, width=6,
                         font=ui.font(10), justify='center')
        entry.pack(side='left', padx=6)
        entry.bind('<Return>', lambda _e: self.check_count())
        M3Button(check, text='대조', command=self.check_count).pack(side='left')
        self.verdict = tk.Label(self, text='', bg=bg, fg='#555',
                                font=ui.font(9), justify='left',
                                wraplength=ui.px(520))
        self.verdict.pack(anchor='w', padx=12, pady=(2, 6))

        box, self.text = ui.text_field(self, height=12, wrap='word')
        box.pack(fill='both', expand=True, padx=12, pady=4)
        self.text.insert('1.0', self.missing_text() or f'빠진 {who}이 없습니다.')
        self.text.config(state='disabled', fg=COLORS['error'] if not ok else COLORS['ok'])

        row = tk.Frame(self, bg=bg)
        row.pack(fill='x', padx=12, pady=10)
        if not ok:
            M3Button(
                row,
                text='빠진 명단 복사',
                command=self._copy_missing,
                variant='danger'
            ).pack(side='left', padx=4)
        M3Button(row, text='들어간 명단 복사', command=self._copy_placed, variant='tonal').pack(side='left', padx=4)
        if on_retry and not ok:
            M3Button(row, text='빠진 것만 다시 실행', command=self._retry, variant='tonal').pack(side='left', padx=4)
        M3Button(row, text='닫기', command=self.destroy, variant='text').pack(side='right', padx=4)

        self.status = tk.Label(self, text='', bg=bg, fg=COLORS['ok'], font=ui.font(9))
        self.status.pack(pady=(0, 8))

        if shown_count is not None:
            self.check_count()

    def expected_count(self) -> int:
        """받는 쪽 화면에 보여야 할 수. 시작 전부터 있던 수에 새로 넣은 수를 더한다."""
        return self.base_count + len(self.tally.placed)

    def check_count(self):
        """적힌 수를 대조한다. 돌려주는 값은 match / short / over, 못 읽으면 None."""
        raw = (self.count_var.get() or '').strip()
        try:
            shown = int(raw)
        except ValueError:
            self.verdict.config(text='숫자만 적어 주세요.', fg=COLORS['warn'])
            return None
        kind, message = reconcile.compare_count(
            self.expected_count(), shown, self.where, self.unit, self.who)
        color = {'match': COLORS['ok'], 'short': COLORS['error'], 'over': COLORS['warn']}[kind]
        self.verdict.config(text=message, fg=color)
        return kind

    def missing_text(self) -> str:
        return reconcile.missing_text(self.tally, self.unit)

    def _copy_missing(self):
        if copy_text(self, self.missing_text()):
            self.status.config(text='✓ 빠진 명단을 복사했습니다')

    def _copy_placed(self):
        if copy_text(self, reconcile.placed_text(self.tally)):
            self.status.config(text='✓ 들어간 명단을 복사했습니다')

    def _retry(self):
        self.destroy()
        if self.on_retry:
            self.on_retry()


class MessengerCompareReport(tk.Toplevel):
    """소통메신저 [선택된 사용자] 와 소통픽 명단을 맞춰 본 결과 창."""

    def __init__(self, parent, result, total, on_add=None, note=''):
        super().__init__(parent)
        self.result = result
        self.on_add = on_add
        # 담을 사람: 빠진 사람과, 동명이인이라 들어갔는지 모르는 사람.
        # 이미 들어 있는 사람을 또 담으면 소통메신저가 '선택된 사용자' 안내만 띄운다.
        self.addable = list(result.missing) + [
            item for _name, people, _have in result.unsure for item in people]
        self.title('소통메신저와 비교')
        self.geometry(f'{ui.px(600)}x{ui.px(660)}')
        unsure = sum(len(people) for _n, people, _h in result.unsure)
        short = len(result.missing) + unsure
        ok = short == 0 and not result.no_name
        bg = PANEL_BG
        self.configure(bg=bg)

        head = (f'O  소통픽 명단 {total}명이 모두 소통메신저에 있습니다' if ok else
                f'X  소통픽 명단 {total}명 중 {short}명이 소통메신저에 없거나 확인이 필요합니다')
        tk.Label(self, text=head, bg=COLORS['ok_container'] if ok else COLORS['error_container'],
            fg=COLORS['on_ok_container'] if ok else COLORS['on_error_container'],
                 font=ui.font(12, 'bold'), pady=10, wraplength=ui.px(540)).pack(fill='x')
        summary = (f'소통메신저에서 읽은 사람 {result.rows}명  ·  들어감 {len(result.inside)}명  ·  '
                   f'빠짐 {len(result.missing)}명  ·  확인 필요 {unsure}명  ·  '
                   f'소통메신저에만 있음 {len(result.extra)}명')
        tk.Label(self, text=summary, bg=bg, fg=COLORS['on_surface'], font=ui.font(9, 'bold'),
                 wraplength=ui.px(530), justify='left').pack(anchor='w', padx=12, pady=(10, 2))
        tk.Label(
            self,
            text=('소통메신저 목록에는 학교 이름이 나오지 않아 이름으로 맞췄습니다. '
                  '같은 이름이 명단에 여럿이면 누가 들어갔는지 가릴 수 없어 확인 필요로 둡니다. '
                  '읽은 사람 수가 소통메신저에 보이는 수와 다르면 결과를 믿지 마세요.'),
            bg=bg, fg='#555', font=ui.font(9), wraplength=ui.px(530), justify='left'
        ).pack(anchor='w', padx=12)
        if note:
            tk.Label(self, text=note, bg=bg, fg=COLORS['warn'], font=ui.font(9, 'bold'),
                     wraplength=ui.px(530), justify='left').pack(anchor='w', padx=12, pady=(4, 0))

        box, self.text = ui.text_field(self, height=14, wrap='word')
        box.pack(fill='both', expand=True, padx=12, pady=8)
        self.text.insert('1.0', reconcile.compare_text(result) or '읽은 사람이 없습니다.')
        self.text.config(state='disabled')

        row = tk.Frame(self, bg=bg)
        row.pack(fill='x', padx=12, pady=(0, 10))
        if self.addable and on_add:
            M3Button(
                row,
                text=f'누락된 {len(self.addable)}명 소통메신저에 추가',
                command=self._add
            ).pack(side='left', padx=4)
        M3Button(row, text='닫기', command=self.destroy, variant='text').pack(side='right', padx=4)
        self.status = tk.Label(self, text='', bg=bg, fg=COLORS['ok'], font=ui.font(9))
        self.status.pack(pady=(0, 8))

    def _add(self):
        # 이 창이 소통메신저를 가리면 엉뚱한 곳을 누르므로 먼저 닫는다
        self.destroy()
        if self.on_add:
            self.on_add(self.addable)


class ClipboardWalker(tk.Toplevel):
    """기관명을 한 건씩 클립보드에 넣어 주는 창.

    기관코드가 없어도 쓸 수 있는 경로다. 에듀파인 [수신자 지정] 조직명 칸에
    Ctrl+V 로 붙여넣고 Enter, 체크, >> 를 차례로 누르는 일만 반복하면 된다.
    """

    def __init__(self, parent, items):
        super().__init__(parent)
        self.items = list(items)
        self.idx = 0
        self.title('클립보드 순차 복사')
        self.geometry(f'{ui.px(560)}x{ui.px(250)}')
        self.resizable(False, False)
        self.configure(bg=PANEL_BG)
        self.transient(parent)

        tk.Label(
            self, text='에듀파인 조직명 칸에 붙여넣고(Ctrl+V) Enter 를 누른 뒤,\n체크하고 [>>] 를 누르는 일을 반복하세요.',
            bg=PANEL_BG, fg=COLORS['on_surface_variant'], font=ui.font(9), justify='center'
        ).pack(pady=(14, 6))

        self.name_var = tk.StringVar()
        tk.Label(
            self, textvariable=self.name_var, bg=PANEL_BG, fg=ui.acc()[0],
            font=ui.font(18, 'bold'), wraplength=ui.px(480)
        ).pack(pady=6)

        self.progress_var = tk.StringVar()
        tk.Label(self, textvariable=self.progress_var, bg=PANEL_BG,
                 fg='#555', font=ui.font(9)).pack()

        row = tk.Frame(self, bg=PANEL_BG)
        row.pack(pady=14)

        M3Button(row, text='← 이전', command=self.prev, variant='text').pack(side='left', padx=4)

        self.next_btn = M3Button(row, text='복사하고 다음  (Enter)', command=self.advance, variant='outlined')
        self.next_btn.pack(side='left', padx=4)

        M3Button(row, text='닫기', command=self.destroy, variant='text').pack(side='left', padx=4)

        self.note = tk.Label(self, text='', bg=PANEL_BG, fg=COLORS['error'],
                             font=ui.font(8))
        self.note.pack()

        self.bind('<Return>', lambda e: self.advance())
        self.bind('<space>', lambda e: self.advance())
        self.bind('<Escape>', lambda e: self.destroy())
        self.next_btn.focus_set()
        self._render()
        self._copy_current()

    def _render(self):
        if self.idx >= len(self.items):
            self.name_var.set('끝났습니다')
            self.progress_var.set(f'{len(self.items)} / {len(self.items)}  모두 복사함')
            self.next_btn.config(state='disabled')
            return
        self.next_btn.config(state='normal')
        self.name_var.set(self.items[self.idx])
        self.progress_var.set(f'{self.idx + 1} / {len(self.items)}')

    def _copy_current(self):
        if self.idx >= len(self.items):
            return
        text = self.items[self.idx]
        try:
            if pyperclip is not None:
                pyperclip.copy(text)
            else:
                raise RuntimeError('pyperclip 없음')
            self.note.config(text='')
        except Exception as exc:
            # pyperclip 이 없거나 실패해도 tk 자체 클립보드로 넘어간다
            logging.info('pyperclip 복사 실패, tk 클립보드 사용: %s', exc)
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
                self.update_idletasks()
                self.note.config(text='')
            except Exception as exc2:
                logging.warning('클립보드 복사 실패: %s', exc2)
                self.note.config(text='클립보드 복사에 실패했습니다. 위 이름을 직접 복사하세요.')

    def advance(self):
        if self.idx >= len(self.items):
            return
        self.idx += 1
        self._render()
        self._copy_current()

    def prev(self):
        if self.idx == 0:
            return
        self.idx -= 1
        self._render()
        self._copy_current()


def _grab_window(win):
    """창 안쪽을 그대로 찍는다 (PIL 이미지). 못 찍으면 None. 화면에 남기지 않고 메모리에서만 쓴다."""
    try:
        win.update_idletasks()
        x, y = win.winfo_rootx(), win.winfo_rooty()
        w, h = win.winfo_width(), win.winfo_height()
        if w < 50 or h < 50:
            return None
        try:
            import pyautogui
            shot = pyautogui.screenshot(region=(x, y, w, h))
        except Exception:
            from PIL import ImageGrab
            shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        shot = shot.convert('RGB')
        if shot.size != (w, h):
            shot = shot.resize((w, h))
        return shot
    except Exception as exc:
        logging.info('가이드용 화면을 찍지 못했습니다: %s', exc)
        return None


class WalkthroughDialog:
    """Iorad 처럼 화면을 어둡게 하고 조작할 자리만 밝게 비춘 채 한 단계씩 안내한다.

    창 안쪽을 한 번 찍어 어둡게 만든 그림을 덮고, 조작할 곳만 원래 화면으로 오려 낸다.
    말풍선은 그 곁에 놓는다. 화면을 못 찍으면 어둡게 하지 않고 테두리 네 줄로만 가리킨다.
    덮개가 클릭을 막으므로 안내 중에는 말풍선의 단추로만 넘어간다.
    """

    DIM = 0.58
    PAD = 7                  # 밝게 비출 자리가 대상보다 넉넉한 만큼
    INSET = 14               # 말풍선 안쪽 여백
    EDGE = 9                 # 말풍선 틀을 바탕 그림보다 이만큼 들여 올린다 (둥근 모서리가 보이도록)

    def __init__(self, parent, title, steps, on_step, on_close):
        self.parent = parent
        self.guide_title = title
        self.steps = list(steps)
        self.on_step = on_step
        self.on_close = on_close
        self.idx = 0
        self._closed = False
        self.highlight_target = None
        self.highlight_frames = []      # 화면을 못 찍을 때만 만든다
        self._snap = None
        self._snap_key = None
        self._photo = None
        self._resize_after = None

        self.overlay = tk.Canvas(parent, highlightthickness=0, bd=0, bg='#10122A', cursor='arrow',
                                 takefocus=1)
        self.overlay.bind('<Button-1>', lambda _e: 'break')

        # 말풍선 바탕(둥근 모서리, 그림자)은 덮개 그림에 그리고, 이 틀은 그 안쪽에 올린다.
        self.bubble = tk.Frame(parent, bg='#FFFFFF', highlightthickness=0,
                               highlightbackground=ui.EDGE)
        self.bubble.fill = '#FFFFFF'
        body = tk.Frame(self.bubble, bg='#FFFFFF')
        body.pack(fill='both', expand=True, padx=self.INSET, pady=self.INSET)
        fill = '#FFFFFF'
        head = tk.Frame(body, bg=fill)
        head.pack(fill='x')
        self.progress_chip = Chip(head, text='', kind='info')
        self.progress_chip.pack(side='left')
        self.heading_var = tk.StringVar()
        tk.Label(head, textvariable=self.heading_var, bg=fill, fg=COLORS['on_surface'],
                 font=ui.font(13, 'bold'), anchor='w', justify='left',
                 wraplength=ui.px(360)).pack(side='left', padx=(10, 0))
        self.body_var = tk.StringVar()
        tk.Label(body, textvariable=self.body_var, bg=fill, fg=COLORS['on_surface_variant'],
                 font=ui.font(11), justify='left', anchor='nw',
                 wraplength=ui.px(440)).pack(fill='x', pady=(12, 8))
        tk.Label(body, text='밝게 보이는 곳에서 이 단계를 진행하세요.', bg=fill, fg=ui.acc()[0],
                 font=ui.font(9, 'bold'), anchor='w').pack(fill='x')
        buttons = tk.Frame(body, bg=fill)
        buttons.pack(fill='x', pady=(14, 0))
        self.next_btn = M3Button(buttons, text='다음', command=self.next, size='sm')
        self.next_btn.pack(side='right')
        self.prev_btn = M3Button(buttons, text='이전', command=self.prev, variant='text',
                                 size='sm')
        self.prev_btn.pack(side='right', padx=(0, 6))
        M3Button(buttons, text='건너뛰기', command=self.finish, variant='text', size='sm').pack(
            side='left')

        for widget in (self.overlay, self.bubble):
            widget.bind('<Left>', lambda _e: self.prev())
            widget.bind('<Right>', lambda _e: self.next())
            widget.bind('<Escape>', lambda _e: self.finish())
        self._render()
        try:
            self.overlay.focus_set()
        except tk.TclError:
            pass

    # ── 창 관리 (예전 대화상자와 같은 이름) ──
    def winfo_exists(self):
        return 0 if self._closed else 1

    def lift(self):
        for widget in (self.overlay, self.bubble):
            try:
                widget.lift()
            except tk.TclError:
                pass

    # ── 한 단계 그리기 ──
    def _render(self, same_tab=False):
        tab_key, widget_key, heading, body = self.steps[self.idx]
        total = len(self.steps)
        self.progress_chip.set(f'{self.idx + 1} / {total}', 'info')
        self.heading_var.set(heading)
        self.body_var.set(body)
        self.prev_btn.config(state='normal' if self.idx else 'disabled')
        self.next_btn.config(text='끝내기' if self.idx == total - 1 else '다음')
        target = self.on_step(tab_key, widget_key)
        self.highlight_target = target
        self.parent.update_idletasks()
        self._draw(tab_key, target)

    def _target_box(self, target):
        """대상의 자리 (x0, y0, x1, y1), 창 안쪽 기준. 알 수 없으면 None."""
        if target is None:
            return None
        try:
            x = target.winfo_rootx() - self.parent.winfo_rootx()
            y = target.winfo_rooty() - self.parent.winfo_rooty()
            width, height = target.winfo_width(), target.winfo_height()
        except tk.TclError:
            return None
        if width <= 1 or height <= 1:
            return None
        pad = self.PAD
        return (x - pad, y - pad, x + width + pad, y + height + pad)

    def _snapshot(self, key):
        """덮개와 말풍선이 없는 깨끗한 화면. 같은 탭이면 다시 찍지 않는다."""
        if self._snap is not None and self._snap_key == key:
            return self._snap
        for widget in (self.overlay, self.bubble):
            widget.place_forget()
        self._clear_frames()
        self.parent.update()
        ui.flush_stale()                      # 방금 열린 탭의 단추와 카드를 그려 둔다
        end = time.time() + 0.08              # 카드 바탕이 다시 그려지고 화면에 반영될 틈
        while time.time() < end:
            self.parent.update()
            time.sleep(0.01)
        self._snap = _grab_window(self.parent) if glass is not None else None
        self._snap_key = key
        return self._snap

    def _draw(self, tab_key, target):
        width, height = self.parent.winfo_width(), self.parent.winfo_height()
        box = self._target_box(target)
        snap = self._snapshot((tab_key, width, height, ui.zoom(), ui.current_tool()))
        self.bubble.place_forget()
        dim = snap is not None and snap.size == (width, height)
        # 말풍선 크기와 자리를 먼저 정한다 (그림에 바탕과 꼬리를 그려야 해서)
        self.bubble.configure(highlightthickness=0 if dim else 1)
        self.bubble.update_idletasks()
        edge = self.EDGE if dim else 0
        bw = self.bubble.winfo_reqwidth() + 2 * edge
        bh = self.bubble.winfo_reqheight() + 2 * edge
        bx, by, side = self._bubble_position(box, width, height, bw, bh)
        if dim:
            image = glass.spotlight(snap, box, radius=ui.px(14), dim=self.DIM, ring=ui.acc()[0])
            arrow = self._arrow_points(box, side, bx, by, bw, bh) if box is not None else None
            image = glass.callout(image, (bx, by, bx + bw, by + bh), radius=ui.px(18),
                                  arrow=arrow)
            try:
                self._photo = tk.PhotoImage(master=self.overlay, data=glass.ppm_bytes(image),
                                            format='ppm')
            except Exception:
                self._photo = tk.PhotoImage(master=self.overlay,
                                            data=glass.png_base64(image, level=1))
            self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
            self.overlay.delete('all')
            self.overlay.create_image(0, 0, image=self._photo, anchor='nw')
            self._clear_frames()
        else:
            self.overlay.place_forget()
            self._draw_frames(box)
        self.bubble.place(x=bx + edge, y=by + edge, width=bw - 2 * edge, height=bh - 2 * edge)
        self.lift()

    def _bubble_position(self, box, width, height, bw, bh):
        """말풍선 자리 (x, y, 놓인 쪽). 대상을 가리지 않도록 오른쪽, 왼쪽, 아래, 위 순으로 찾는다."""
        gap = ui.px(24)
        margin = ui.px(16)
        side = None
        if box is None:
            x, y = (width - bw) // 2, (height - bh) // 2
        else:
            x0, y0, x1, y1 = box
            cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
            if x1 + gap + bw + margin <= width:
                side, x, y = 'right', x1 + gap, cy - bh // 2
            elif x0 - gap - bw - margin >= 0:
                side, x, y = 'left', x0 - gap - bw, cy - bh // 2
            elif y1 + gap + bh + margin <= height:
                side, x, y = 'below', cx - bw // 2, y1 + gap
            elif y0 - gap - bh - margin >= 0:
                side, x, y = 'above', cx - bw // 2, y0 - gap - bh
            else:
                x, y = (width - bw) // 2, margin
        x = max(margin, min(x, width - bw - margin))
        y = max(margin, min(y, height - bh - margin))
        return x, y, side

    def _arrow_points(self, box, side, x, y, bw, bh):
        """말풍선에서 대상 쪽으로 뻗는 꼬리 삼각형. 놓인 쪽이 없으면 꼬리를 그리지 않는다."""
        if side is None:
            return None
        half, length, keep = ui.px(11), ui.px(15), ui.px(30)
        x0, y0, x1, y1 = box
        if side in ('right', 'left'):
            py = max(y + keep, min((y0 + y1) // 2, y + bh - keep))
            if side == 'right':
                return [(x + 2, py - half), (x - length, py), (x + 2, py + half)]
            return [(x + bw - 2, py - half), (x + bw + length, py), (x + bw - 2, py + half)]
        px_ = max(x + keep, min((x0 + x1) // 2, x + bw - keep))
        if side == 'below':
            return [(px_ - half, y + 2), (px_, y - length), (px_ + half, y + 2)]
        return [(px_ - half, y + bh - 2), (px_, y + bh + length), (px_ + half, y + bh - 2)]

    # ── 화면을 못 찍을 때의 테두리 ──
    def _draw_frames(self, box):
        self._clear_frames()
        if box is None:
            return
        x0, y0, x1, y1 = box
        thickness = 4
        self.highlight_frames = [tk.Frame(self.parent, bg=ui.acc()[0]) for _ in range(4)]
        top, bottom, left, right = self.highlight_frames
        top.place(x=x0, y=y0, width=x1 - x0, height=thickness)
        bottom.place(x=x0, y=y1 - thickness, width=x1 - x0, height=thickness)
        left.place(x=x0, y=y0, width=thickness, height=y1 - y0)
        right.place(x=x1 - thickness, y=y0, width=thickness, height=y1 - y0)
        for border in self.highlight_frames:
            border.lift()

    def _clear_frames(self):
        for border in self.highlight_frames:
            try:
                border.place_forget()
                border.destroy()
            except tk.TclError:
                pass
        self.highlight_frames = []

    # ── 창 크기가 바뀌면 다시 찍어서 맞춘다 ──
    def parent_resized(self):
        """앱이 창 크기가 바뀔 때마다 알려 준다."""
        if self._closed:
            return
        if self._resize_after is not None:
            try:
                self.parent.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._resize_after = self.parent.after(120, self._after_resize)

    def _after_resize(self):
        self._resize_after = None
        if self._closed:
            return
        self._snap = None
        self._render()

    def next(self):
        if self.idx >= len(self.steps) - 1:
            self.finish()
            return
        self.idx += 1
        self._render()

    def prev(self):
        if self.idx == 0:
            return
        self.idx -= 1
        self._render()

    def finish(self):
        if self._closed:
            return
        self._closed = True
        if self._resize_after is not None:
            try:
                self.parent.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._clear_frames()
        for widget in (self.bubble, self.overlay):
            try:
                widget.place_forget()
                widget.destroy()
            except tk.TclError:
                pass
        self.on_close()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f'{APP_NAME}  v{APP_VERSION}')
        # 글자를 키웠으므로 창도 키운다. 작은 화면(1366x768)에서는 화면에 맞춘다.
        width = min(1360, max(960, self.root.winfo_screenwidth() - 40))
        height = min(860, max(640, self.root.winfo_screenheight() - 90))
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(ui.px(960), ui.px(640))

        self.config = Config()
        self.codes = edufine.load_codes()
        self.names_list: list = []
        self.last_org_duplicates: list = []
        self.stop_flag = threading.Event()
        self.continue_event = threading.Event()
        self.continue_event.set()
        self.worker_thread = None
        self.guide_dialog = None
        # 지난 수신그룹 엑셀 결과. 결과 대조 창을 닫았다가 다시 열 수 있게 둔다.
        self.last_excel_result = None
        self.compare_note = ''
        # 도구를 바꾸면 쓰던 입력과 명단을 여기 맡겨 둔다 {도구: {...}}
        self.tool_states = {}

        self._apply_theme()
        self._build_ui()
        self._refresh_calib_labels()
        self._check_deps()
        self._check_for_update_async()

    # ── 테마 (Material 3 글래스) ───────────────
    def _apply_theme(self):
        ui.set_tool(THEME_TOOL.get(self.config.target, 'sotong'))
        # 이름을 안 붙인 tk 위젯도 판 위 색을 따르게 기본값을 깐다
        for pattern, value in (('*Frame.background', PANEL_BG), ('*Label.background', PANEL_BG),
                               ('*Toplevel.background', PANEL_BG), ('*Canvas.background', PANEL_BG),
                               ('*Checkbutton.background', PANEL_BG),
                               ('*Radiobutton.background', PANEL_BG),
                               ('*Entry.relief', 'flat'), ('*Entry.highlightThickness', 1),
                               ('*Entry.highlightBackground', COLORS['outline']),
                               ('*Entry.highlightColor', COLORS['primary']),
                               ('*Entry.background', '#FFFFFF'),
                               ('*Listbox.relief', 'flat'), ('*Listbox.highlightThickness', 1),
                               ('*Listbox.highlightBackground', COLORS['outline']),
                               ('*Listbox.highlightColor', COLORS['primary']),
                               ('*Listbox.background', '#FFFFFF'),
                               ('*Label.foreground', COLORS['on_surface']),
                               ('*Checkbutton.foreground', COLORS['on_surface']),
                               ('*Radiobutton.foreground', COLORS['on_surface'])):
            self.root.option_add(pattern, value)
        # 이름을 따로 안 준 글자(체크 상자, 메뉴 등)도 같은 글꼴과 크기로
        try:
            import tkinter.font as tkfont
            for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont',
                         'TkCaptionFont', 'TkSmallCaptionFont', 'TkTooltipFont', 'TkIconFont'):
                tkfont.nametofont(name).configure(family=FONT, size=fs(9))
        except Exception as exc:
            logging.info('기본 글꼴 지정 실패: %s', exc)
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception as exc:
            logging.info("Tk 테마 적용 실패: %s", exc)
        # 탭 줄은 숨기고 왼쪽 레일이 대신 고른다. 탭 이름과 순서는 그대로 등록한다.
        style.layout('Hidden.TNotebook.Tab', [])
        style.layout('Hidden.TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
        style.configure('Hidden.TNotebook', background=PANEL_BG, borderwidth=0, tabmargins=0,
                        bordercolor=PANEL_BG, lightcolor=PANEL_BG, darkcolor=PANEL_BG)
        style.configure('TFrame', background=PANEL_BG)
        style.configure('TLabelframe', background=PANEL_BG)
        style.configure('TLabelframe.Label', background=PANEL_BG,
                        font=ui.font(10, 'bold'), foreground=COLORS['on_surface'])
        thumb = '#C9CBDD'
        style.configure('Accent.Horizontal.TProgressbar', background=ui.acc()[0],
                        troughcolor='#E4E5F0', borderwidth=0, thickness=12,
                        bordercolor=PANEL_BG, lightcolor=ui.acc()[0], darkcolor=ui.acc()[0])
        style.configure('Vertical.TScrollbar', background=thumb, troughcolor=PANEL_BG,
                        bordercolor=PANEL_BG, lightcolor=thumb, darkcolor=thumb,
                        arrowcolor=COLORS['on_surface_variant'], relief='flat')
        style.map('Vertical.TScrollbar', background=[('active', '#B5B8D0')])
        style.configure('Horizontal.TScrollbar', background=thumb, troughcolor=PANEL_BG,
                        bordercolor=PANEL_BG, lightcolor=thumb, darkcolor=thumb,
                        arrowcolor=COLORS['on_surface_variant'], relief='flat')

    # ── UI 빌드 ────────────────────────────────
    def _build_ui(self):
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=PANEL_BG)
        self.canvas.pack(fill='both', expand=True)
        # 바탕 그림은 맨 아래에 깔고, 판마다 틀을 올린다. 틀은 크기가 바뀌면 다시 놓는다.
        self._bg_item = self.canvas.create_image(0, 0, anchor='nw')
        self._shell = {'size': (0, 0), 'after': None, 'drawn': None, 'photo': None,
                       'settle': None, 'zoom_ok': 0.0}
        self._shell_windows = {}
        frames = {}
        for name in ('top', 'rail', 'body', 'status'):
            frames[name] = tk.Frame(self.canvas, bg=PANEL_BG)
            self._shell_windows[name] = self.canvas.create_window(
                0, 0, window=frames[name], anchor='nw')
        self.top_frame, self.rail_frame = frames['top'], frames['rail']
        self.body_frame, self.status_frame = frames['body'], frames['status']
        self.canvas.bind('<Configure>', self._on_shell_resize)

        self._build_top_bar()
        self._build_status_bar()
        self.rail_items = {}

        # 탭 노트북. 탭 줄은 숨겨져 있고 왼쪽 레일이 같은 탭을 고른다.
        nb = ttk.Notebook(self.body_frame, style='Hidden.TNotebook')
        nb.pack(fill='both', expand=True, padx=14, pady=(12, 8))
        nb.bind('<<NotebookTabChanged>>', lambda _e: self._on_tab_changed())

        self.nb = nb
        f1 = ttk.Frame(nb)
        f2 = ttk.Frame(nb)
        f3 = ttk.Frame(nb)
        f4 = ttk.Frame(nb)
        f5 = ttk.Frame(nb)
        f6 = ttk.Frame(nb)

        # 고른 도구에 따라 넣고 빼므로 순서와 이름을 기억해 둔다
        self.tab_input = f1
        self.messenger_tabs = [(f2, '  2. 위치 설정  '), (f3, '  3. 자동 선택  ')]
        self.edufine_tabs = [(f4, '  2. 수신그룹 엑셀  ')]
        self.help_tabs = {
            TARGET_MESSENGER: (f5, '  📖 소통픽 사용법  '),
            TARGET_EDUFINE: (f6, '  📖 수신픽 사용법  '),
        }

        # 탭 등록은 _apply_target 이 한다. 고른 도구에 따라 매번 다시 구성한다.

        # 화면을 넘치면 스크롤이 생기도록 감싼다. 사용법 탭은 글 상자가
        # 스스로 스크롤하므로 그대로 둔다.
        self._tab_input(make_scrollable(f1))
        self._tab_calib(make_scrollable(f2))
        self._tab_auto(make_scrollable(f3))
        self._tab_edufine(make_scrollable(f4))
        self._tab_help(f5, TARGET_MESSENGER)
        self._tab_help(f6, TARGET_EDUFINE)
        self._apply_target()

        self._refresh_ready_status()

    def _build_top_bar(self):
        """상단바. 신통픽 이름, 소통픽/수신픽 고르기, 사용 가이드."""
        bar = self.top_frame
        bar.columnconfigure(1, weight=1)
        tk.Label(bar, text=APP_NAME, font=ui.font(15, 'bold'),
                 fg=COLORS['on_surface']).grid(row=0, column=0, sticky='w', padx=(4, 8))
        tk.Label(bar, text='수신픽 + 소통픽', font=ui.font(9),
                 fg=COLORS['on_surface_variant']).grid(row=0, column=1, sticky='w')

        self.target_var = tk.StringVar(value=self.config.target)
        # 신통픽은 수신픽 + 소통픽이다. 이름 순서대로 수신픽을 왼쪽에 둔다.
        self.tool_switch = ToolSwitch(
            bar, [(TARGET_EDUFINE, TARGET_LABELS[TARGET_EDUFINE]),
                  (TARGET_MESSENGER, TARGET_LABELS[TARGET_MESSENGER])],
            on_select=self._choose_target)
        self.tool_switch.grid(row=0, column=2, padx=(8, 8))
        # 예전 이름을 그대로 둔다. 도구마다 (카드, 제목, 설명) 이었는데 이제 한 위젯이다.
        self.target_cards = {key: (label, label, label)
                             for key, label in self.tool_switch.items.items()}
        M3Button(
            bar,
            text='사용 가이드',
            variant='text',
            size='sm',
            command=lambda: self._show_onboarding(self.config.target)
        ).grid(row=0, column=3, padx=(0, 4))

    def _build_status_bar(self):
        """상태줄. 왼쪽은 지금 하는 일, 오른쪽은 쓰는 도구와 버전."""
        bar = self.status_frame
        bar.columnconfigure(1, weight=1)
        self.status_var = tk.StringVar(value='준비')
        self.status_dot = tk.Label(bar, text='●', font=ui.font(8), fg=COLORS['ok'])
        self.status_dot.grid(row=0, column=0, sticky='w', padx=(2, 6))
        tk.Label(bar, textvariable=self.status_var, anchor='w', font=ui.font(9),
                 fg=COLORS['on_surface_variant']).grid(row=0, column=1, sticky='ew')
        self.target_hint = tk.Label(
            bar, text='', anchor='e', font=ui.font(9), fg=COLORS['on_surface_variant'])
        self.target_hint.grid(row=0, column=2, sticky='e', padx=(8, 4))

    # ── 창 틀 그리기 ───────────────────────────
    BASE_SIZE = (1280, 820)         # 이 크기에서 글자 배율이 1이다

    def _on_shell_resize(self, event):
        if event.widget is not self.canvas:
            return
        self._shell['size'] = (event.width, event.height)
        self._place_shell()
        self._note_resizing()
        self._maybe_apply_zoom()
        self._schedule_backdrop(delay=40)      # 이벤트가 몰려도 초당 20번만 그린다
        if self.guide_dialog is not None:
            self.guide_dialog.parent_resized()

    def _note_resizing(self):
        """끌어서 크기를 바꾸는 중임을 알린다. 조용해지면(0.14초) 제대로 다시 그린다."""
        ui.set_live(True)
        if self._shell['settle'] is not None:
            try:
                self.root.after_cancel(self._shell['settle'])
            except Exception:
                pass
        self._shell['settle'] = self.root.after(140, self._settle_resize)

    def _settle_resize(self):
        self._shell['settle'] = None
        self._maybe_apply_zoom(force=True)
        ui.set_live(False)                 # 미뤄 둔 카드 바탕을 그린다
        self._shell['drawn'] = None
        self._schedule_backdrop(delay=1)

    def _wanted_zoom(self):
        width, height = self._shell['size']
        base_w, base_h = self.BASE_SIZE
        return round(min(width / base_w, height / base_h) / 0.04) * 0.04

    def _maybe_apply_zoom(self, force=False):
        """글자 배율을 맞춘다. 끌어 바꾸는 동안에는 지난번에 걸린 시간의 세 배 뒤에야 다시 바꾼다.

        배율을 바꾸면 모든 글자와 단추를 다시 배치해서 느리다. 매번 바꾸면 끌기가 버벅이므로,
        컴퓨터가 느릴수록 덜 자주 바꾸고 끌기가 끝나면 마지막 배율로 맞춘다.
        """
        now = time.time()
        if not force and now < self._shell['zoom_ok']:
            return
        start = now
        if ui.set_zoom(self._wanted_zoom()):
            self._shell['drawn'] = None
            self._place_shell()
            self._shell['zoom_ok'] = time.time() + 3 * (time.time() - start)

    def _place_shell(self):
        """판 자리에 틀을 놓는다. 크기를 바꾸는 동안에도 바로 따라가야 한다."""
        width, height = self._shell['size']
        if width < 50 or height < 50:
            return
        layout = shell_layout(max(width, 320), max(height, 240), zoom=ui.zoom())
        for name, box in layout.items():
            left, top, right, bottom = SHELL_INSET[name]
            self.canvas.coords(self._shell_windows[name], box[0] + left, box[1] + top)
            self.canvas.itemconfigure(
                self._shell_windows[name],
                width=max(box[2] - box[0] - left - right, 10),
                height=max(box[3] - box[1] - top - bottom, 10))

    def _schedule_backdrop(self, delay=10):
        """창 바탕 그림을 다시 그린다. 이미 예약돼 있으면 그대로 두어도 된다 (그릴 때 최신 크기를 쓴다)."""
        if glass is None or self._shell['after'] is not None:
            return
        self._shell['after'] = self.root.after(delay, self._render_backdrop)

    DRAFT_SHRINK = 4         # 끌어 바꾸는 동안 바탕을 이만큼 작게 그려 키워서 깐다

    def _render_backdrop(self):
        self._shell['after'] = None
        width, height = self._shell['size']
        if glass is None or width < 50 or height < 50:
            return
        draft = bool(getattr(ui, '_state', {}).get('live'))
        key = (width, height, ui.current_tool(), ui.zoom())
        if not draft and self._shell['drawn'] == key:
            return
        shrink = self.DRAFT_SHRINK if draft else 1
        try:
            image = glass.compose_shell(width, height, ui.current_tool(), zoom=ui.zoom(),
                                        shrink=shrink)
            try:
                photo = tk.PhotoImage(master=self.canvas, data=glass.ppm_bytes(image),
                                      format='ppm')
            except Exception:
                photo = tk.PhotoImage(master=self.canvas, data=glass.png_base64(image, level=1))
            if shrink > 1:
                small, photo = photo, photo.zoom(shrink)
                self._shell['small'] = small
            self._shell['photo'] = photo
            self.canvas.itemconfigure(self._bg_item, image=photo)
            self._shell['drawn'] = None if draft else key
        except Exception as exc:
            logging.warning('창 바탕을 그리지 못했습니다: %s', exc)
            return
        # 그리는 동안 창 크기가 또 바뀌었으면 한 번 더
        if self._shell['size'] != (width, height):
            self._schedule_backdrop(1)

    # ── 레일 ───────────────────────────────────
    def _rebuild_rail(self, order):
        """고른 도구의 단계만 레일에 놓는다. 도움말은 맨 아래."""
        for child in self.rail_frame.winfo_children():
            child.destroy()
        self.rail_items = {}
        steps = [(tab, label) for tab, label in order if tab is not self._help_tab()]
        kinds = {self.tab_input: 'input', self.messenger_tabs[0][0]: 'calib',
                 self.messenger_tabs[1][0]: 'auto', self.edufine_tabs[0][0]: 'excel'}
        for tab, label in steps:
            name = re.sub(r'^\W*\d+\.\s*', '', label.strip())
            item = RailItem(self.rail_frame, name, RAIL_ICONS[kinds[tab]],
                            command=lambda t=tab: self.nb.select(t))
            item.pack(fill='x')
            self.rail_items[str(tab)] = item
        help_tab = self._help_tab()
        item = RailItem(self.rail_frame, '도움말', RAIL_ICONS['help'],
                        command=lambda t=help_tab: self.nb.select(t))
        item.pack(side='bottom', fill='x')
        self.rail_items[str(help_tab)] = item
        self._sync_rail()

    def _help_tab(self):
        return self.help_tabs[self.config.target][0]

    def _on_tab_changed(self):
        self._sync_rail()
        # 가려져 있어서 못 그린 단추와 카드를 지금 그린다 (도구 색, 창 배율이 바뀐 뒤에 열린 탭)
        try:
            # 탭이 실제로 열린 다음에 그려야 하므로 한 박자 늦춰서 두 번 부른다
            self.root.after(15, ui.flush_stale)
            self.root.after(120, ui.flush_stale)
        except Exception as exc:
            logging.debug('가려진 부품 그리기 예약 실패: %s', exc)

    def _sync_rail(self):
        try:
            current = str(self.nb.select())
        except Exception:
            return
        for key, item in getattr(self, 'rail_items', {}).items():
            item.set_selected(key == current)

    # ── 탭 1: 명단 입력 ────────────────────────
    def _tab_input(self, frame: ttk.Frame):
        """화면 1. 왼쪽에 붙여넣기 칸, 오른쪽에 추출 결과 (소통픽 수신픽 공통)."""
        frame.columnconfigure(0, weight=0, minsize=372)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(2, weight=1)

        # ① 제목, 설명, 파일 열기
        head = tk.Frame(frame, bg=PANEL_BG)
        head.grid(row=0, column=0, columnspan=2, sticky='ew', padx=14, pady=(10, 2))
        head.columnconfigure(0, weight=1)
        self.guide_title = tk.Label(head, text='', font=ui.font(18, 'bold'),
                                    fg=COLORS['on_surface'], anchor='w')
        self.guide_title.grid(row=0, column=0, sticky='w')
        self.guide_body = tk.Label(head, text='', font=ui.font(9), justify='left',
                                   fg=COLORS['on_surface_variant'], anchor='w', wraplength=560)
        self.guide_body.grid(row=1, column=0, sticky='w', pady=(2, 0))
        ui.autowrap(self.guide_body, margin=ui.px(340))      # 오른쪽 파일 열기 단추 자리를 비워 둔다
        files = tk.Frame(head, bg=PANEL_BG)
        files.grid(row=0, column=1, rowspan=2, sticky='e')
        M3Button(
            files,
            text='엑셀 파일 열기',
            command=self._open_excel,
            variant='outlined',
            size='sm'
        ).pack(side='left', padx=3)
        M3Button(
            files,
            text='한글 파일 열기',
            command=self._open_hwp,
            variant='outlined',
            size='sm'
        ).pack(side='left', padx=3)
        self.ready_status = tk.Label(frame, text='', font=ui.font(9),
                                     fg=COLORS['on_surface_variant'], anchor='w')
        self.ready_status.grid(row=1, column=0, columnspan=2, sticky='w', padx=16, pady=(0, 6))

        # ② 왼쪽: 붙여넣기 칸
        left = tk.Frame(frame, bg=PANEL_BG)
        left.grid(row=2, column=0, sticky='nsew', padx=(14, 8), pady=(0, 6))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        tk.Label(left, text='명단 붙여넣기', font=ui.font(12, 'bold'),
                 fg=COLORS['on_surface'], anchor='w').grid(row=0, column=0, sticky='w', pady=(0, 6))
        input_card, self.input_text = ui.text_field(left, height=7, wrap='none')
        input_card.grid(row=1, column=0, sticky='nsew')
        self.input_card = input_card
        tk.Label(left, text='한 줄에 한 사람(기관), 줄 순서대로 들어갑니다.',
                 font=ui.font(8), fg=COLORS['on_surface_variant'], anchor='w'
                 ).grid(row=2, column=0, sticky='w', padx=6, pady=(4, 6))
        action_frame = tk.Frame(left, bg=PANEL_BG)
        action_frame.grid(row=3, column=0, sticky='w')
        self.parse_button = M3Button(action_frame, text='명단 추출', command=self._parse)
        self.parse_button.pack(side='left', padx=(0, 6))
        M3Button(action_frame, text='비우기', command=self._clear_input, variant='text').pack(side='left')

        # ③ 오른쪽: 추출 결과
        right = tk.Frame(frame, bg=PANEL_BG)
        right.grid(row=2, column=1, sticky='nsew', padx=(8, 14), pady=(0, 6))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)
        title_row = tk.Frame(right, bg=PANEL_BG)
        title_row.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        tk.Label(title_row, text='추출 결과', font=ui.font(12, 'bold'),
                 fg=COLORS['on_surface']).pack(side='left', padx=(0, 10))
        self.summary_row = tk.Frame(title_row, bg=PANEL_BG)
        self.summary_row.pack(side='left')
        self.parse_status = tk.Label(right, text='', fg=COLORS['on_surface_variant'],
                                     font=ui.font(9), anchor='w')
        self.parse_status.grid(row=1, column=0, sticky='w', padx=2, pady=(0, 4))

        # 확인이 필요한 것을 알리는 배너. 있을 때만 보인다.
        self.org_issue_card = Card(right, tone='warn', pad=(14, 9))
        self.org_issue_card.grid(row=2, column=0, sticky='ew', pady=(0, 6))
        self.org_issue_summary = tk.Label(
            self.org_issue_card.body, text='', fg=COLORS['on_warn_container'],
            bg=self.org_issue_card.fill, font=ui.font(9, 'bold'), justify='left',
            anchor='w', wraplength=520)
        self.org_issue_summary.pack(anchor='w', fill='x')
        ui.autowrap(self.org_issue_summary, margin=4)
        self.org_issue_card.grid_remove()

        list_card, self.parsed_list = ui.list_card(
            right, font=ui.font(10), selectmode='extended', height=6)
        list_card.grid(row=3, column=0, sticky='nsew')
        self.list_card = list_card

        # 아래 줄: 수신픽에서만 쓰는 단추들과 다음 단계
        bottom = tk.Frame(right, bg=PANEL_BG)
        bottom.grid(row=4, column=0, sticky='ew', pady=(8, 0))
        bottom.columnconfigure(0, weight=1)
        # 아래 단추들은 수신픽에서만 쓴다. _apply_target 이 보이고 감춘다.
        # 부서는 전체경로를 외울 수 없으니 목록에서 고르게 한다
        tools = tk.Frame(bottom, bg=PANEL_BG)
        tools.grid(row=0, column=0, columnspan=2, sticky='w')
        self.bulk_fix_btn = M3Button(
            tools,
            text='확인 필요 기관 일괄 수정',
            command=self._open_bulk_org_editor,
            variant='tonal',
            state='disabled'
        )
        self.browse_btn = M3Button(
            tools,
            text='기관 찾아보기',
            command=self._open_org_picker,
            variant='outlined'
        )
        self.org_history_btn = M3Button(tools, text='추출 기록 보기', command=self._open_org_history, variant='text')
        self.delete_btn = M3Button(
            bottom,
            text='선택 항목 삭제',
            command=self._delete_selected,
            variant='danger',
            size='sm'
        )
        self.next_btn = M3Button(bottom, text='다음', command=self._go_next_step)
        self.next_btn.grid(row=1, column=1, sticky='e', padx=(8, 0), pady=(6, 0))
        # 단추들을 놓는 틀. 수신픽 단추는 _apply_target 이 pack/pack_forget 한다.
        self.input_tools = tools
        self.delete_btn.grid(row=1, column=0, sticky='w', pady=(6, 0))
        tk.Label(right, text='더블클릭으로 수정  ·  Delete 키로 삭제  ·  붉은 줄은 확인이나 선택이 필요합니다',
                 font=ui.font(8), fg=COLORS['on_surface_variant'], anchor='w'
                 ).grid(row=5, column=0, sticky='w', padx=4, pady=(4, 0))

        # ④ 직접 넣기. 파일을 열거나 붙여넣지 않고 한 사람(한 기관)씩 넣는다.
        direct = tk.Frame(frame, bg=PANEL_BG)
        direct.grid(row=3, column=0, columnspan=2, sticky='ew', padx=14, pady=(2, 10))
        direct.columnconfigure(1, weight=1)
        tk.Label(direct, text='직접 넣기', font=ui.font(10, 'bold'),
                 fg=COLORS['on_surface']).grid(row=0, column=0, sticky='w', padx=(2, 10))
        self.direct_var = tk.StringVar()
        direct_card, self.direct_entry = ui.entry_field(direct, textvariable=self.direct_var)
        direct_card.grid(row=0, column=1, sticky='ew')
        self.direct_entry.bind('<Return>', lambda _e: self._add_direct())
        M3Button(
            direct,
            text='명단에 넣기',
            command=self._add_direct,
            variant='tonal',
            size='sm'
        ).grid(row=0, column=2, padx=(8, 0))
        self.direct_hint = tk.Label(direct, text='', fg=COLORS['on_surface_variant'],
                                    font=ui.font(8), anchor='w')
        self.direct_hint.grid(row=1, column=0, columnspan=3, sticky='w', padx=4, pady=(3, 0))

        ctx = tk.Menu(self.root, tearoff=0)
        ctx.add_command(label='수정', command=self._edit_item)
        ctx.add_command(label='삭제', command=self._delete_selected)
        self.parsed_list.bind('<Button-3>', lambda e: ctx.tk_popup(e.x_root, e.y_root))
        self.parsed_list.bind('<Double-Button-1>', self._edit_item)
        self.parsed_list.bind('<Delete>', lambda e: self._delete_selected())

    def _go_next_step(self):
        """레일의 다음 단계로. 마지막이 도움말이므로 도움말 앞까지만 간다."""
        try:
            tabs = list(self.nb.tabs())
            current = str(self.nb.select())
            keys = [str(t) for t in tabs]
            index = keys.index(current)
            if index + 1 < len(tabs) - 1:
                self.nb.select(tabs[index + 1])
        except Exception as exc:
            logging.debug('다음 단계로 가지 못했습니다: %s', exc)

    def _refresh_summary_chips(self):
        """추출 결과 위의 요약 칩. 개수, 확실한 것, 확인이 필요한 것, 빠진 것."""
        row = getattr(self, 'summary_row', None)
        if row is None:
            return
        for child in row.winfo_children():
            child.destroy()
        total = len(self.names_list)
        if not total:
            return
        unit = '곳' if self.is_edufine() else '명'
        if self.is_edufine():
            review = sum(1 for i in self.names_list if self._org_needs_review(i))
        else:
            review = sum(1 for i in self.names_list if not i.get('org'))
        failed = sum(1 for i in self.names_list if i.get('failure_reason'))
        chips = [(f'{total}{unit}', 'neutral'), (f'확실 {total - review}', 'ok')]
        if review:
            chips.append((f'확인 필요 {review}', 'warn'))
        if failed:
            chips.append((f'빠짐 {failed}', 'err'))
        for text, kind in chips:
            Chip(row, text=text, kind=kind).pack(side='left', padx=(0, 6))

    # ── 탭 2: 위치 설정 ────────────────────────
    def _section_title(self, parent, text, bg=None):
        """카드나 화면 안 작은 제목."""
        return tk.Label(parent, text=text, font=ui.font(12, 'bold'),
                        fg=COLORS['on_surface'], bg=bg or PANEL_BG, anchor='w')

    def _screen_header(self, frame, title, columnspan=1):
        """화면 위쪽 제목과 설명. (제목, 설명) 라벨을 돌려준다. 설명 글은 _apply_target 이 채운다."""
        head = tk.Frame(frame, bg=PANEL_BG)
        head.grid(row=0, column=0, columnspan=columnspan, sticky='ew', padx=14, pady=(10, 8))
        head.columnconfigure(0, weight=1)
        title_label = tk.Label(head, text=title, font=ui.font(18, 'bold'),
                               fg=COLORS['on_surface'], anchor='w')
        title_label.grid(row=0, column=0, sticky='w')
        sub = tk.Label(head, text='', font=ui.font(9), fg=COLORS['on_surface_variant'],
                       justify='left', anchor='w', wraplength=780)
        sub.grid(row=1, column=0, sticky='w', pady=(2, 0))
        ui.autowrap(sub, margin=260)           # 오른쪽 단추 자리를 비워 둔다
        return title_label, sub

    def _tab_calib(self, frame: ttk.Frame):
        """화면 2. 소통메신저에서 잡을 자리 세 곳 (소통픽만)."""
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2, minsize=430)
        _title, self.calib_intro = self._screen_header(frame, '위치 설정', columnspan=2)

        # 왼쪽: 소통메신저에서 누르는 차례. 4, 5, 6 번이 오른쪽에서 잡을 자리다.
        order = Card(frame, tone='inner', pad=(16, 12))
        order.grid(row=1, column=0, sticky='nsew', padx=(14, 7), pady=(0, 8))
        self._section_title(order.body, '소통메신저에서 누르는 차례', order.fill).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))
        order.body.columnconfigure(1, weight=1)
        self.step_images = []
        for row_i, (number, title, desc) in enumerate(MESSENGER_STEPS, start=1):
            mine = number in CAPTURE_STEP_KEYS.values()
            badge = Chip(order.body, text=number, kind='info' if mine else 'neutral')
            badge.grid(row=row_i, column=0, padx=(0, 10), pady=6, sticky='nw')
            cell = tk.Frame(order.body, bg=order.fill)
            cell.grid(row=row_i, column=1, pady=6, sticky='w')
            tail = '  아래에서 이 자리를 잡습니다' if mine else ''
            tk.Label(
                cell, text=f'{title}\n{desc}{tail}', bg=order.fill,
                font=ui.font(9), fg=COLORS['on_surface_variant'], justify='left',
                anchor='w', wraplength=330
            ).pack(anchor='w')
            picture = guide_image(number)
            if picture is not None:
                self.step_images.append(picture)
                tk.Label(cell, image=picture, bg=order.fill).pack(anchor='w', pady=(4, 0))

        right = tk.Frame(frame, bg=PANEL_BG)
        right.grid(row=1, column=1, sticky='nsew', padx=(7, 14), pady=(0, 8))
        right.columnconfigure(0, weight=1)

        # 오른쪽 위: 잡아 둘 자리 세 곳
        pos = Card(right, tone='inner', pad=(16, 12))
        pos.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.calibration_panel = pos
        self._section_title(pos.body, '잡아 둘 자리 세 곳', pos.fill).grid(
            row=0, column=0, columnspan=4, sticky='w', pady=(0, 6))
        pos.body.columnconfigure(1, weight=1)
        for row_i, (label_text, key) in enumerate([
            ('4번  검색 입력칸', 'search_field'),
            ('5번  검색 결과 첫 줄', 'result_first'),
            ('6번  오른쪽 화살표 버튼', 'add_button'),
        ], start=1):
            tk.Label(pos.body, text=label_text, bg=pos.fill, font=ui.font(10, 'bold'),
                     fg=COLORS['on_surface']).grid(row=row_i, column=0, sticky='w', pady=6)
            lbl = tk.Label(pos.body, text='', bg=pos.fill, font=ui.font(9),
                           fg=COLORS['on_surface_variant'])
            lbl.grid(row=row_i, column=1, sticky='w', padx=10)
            setattr(self, f'lbl_{key}', lbl)
            chip = Chip(pos.body, text='미설정', kind='err')
            chip.grid(row=row_i, column=2, padx=(0, 8))
            setattr(self, f'chip_{key}', chip)
            btn = M3Button(
                pos.body,
                text='캡처 시작',
                variant='outlined',
                size='sm',
                command=lambda k=key: self._do_capture(k)
            )
            btn.grid(row=row_i, column=3)
            setattr(self, f'btn_{key}', btn)

        # 세 곳을 모두 잡으면 켜진다. 누르면 설정을 저장하고 자동 선택으로 넘어간다.
        self.calib_hint = tk.Label(pos.body, text='', bg=pos.fill, font=ui.font(9),
                                   fg=COLORS['on_surface_variant'], anchor='w')
        self.calib_hint.grid(row=4, column=0, columnspan=3, sticky='w', pady=(8, 0))
        self.calib_next_btn = M3Button(pos.body, text='다음, 자동 선택', command=self._calib_next,
                                       state='disabled', size='sm')
        self.calib_next_btn.grid(row=4, column=3, sticky='e', pady=(8, 0))

        # 오른쪽 아래: 검색 설정
        setting = Card(right, tone='inner', pad=(16, 12))
        setting.grid(row=1, column=0, sticky='ew')
        self._section_title(setting.body, '검색 설정', setting.fill).grid(
            row=0, column=0, columnspan=3, sticky='w', pady=(0, 6))
        tk.Label(setting.body, text='검색 후 대기 시간(초)', bg=setting.fill,
                 font=ui.font(10), fg=COLORS['on_surface']).grid(
            row=1, column=0, sticky='w', pady=4)
        self.delay_var = tk.DoubleVar(value=self.config.data.get('search_delay', 0.5))
        ttk.Spinbox(setting.body, from_=0.3, to=5.0, increment=0.1,
                    textvariable=self.delay_var, width=6, font=ui.font(10)
                    ).grid(row=1, column=1, padx=8, sticky='w')
        delay_hint = tk.Label(
            setting.body, text='느리면 값을 낮추세요, 단 소통메신저 최소 검색 시간이 필요합니다.',
            bg=setting.fill, fg=COLORS['on_surface_variant'], font=ui.font(9), justify='left',
            anchor='w', wraplength=ui.px(420))
        delay_hint.grid(row=2, column=0, columnspan=3, sticky='w')
        ui.autowrap(delay_hint, margin=4)
        self.manual_var = tk.BooleanVar(value=self.config.data.get('manual_confirm', False))
        tk.Checkbutton(
            setting.body, variable=self.manual_var, bg=setting.fill, activebackground=setting.fill,
            text='수동 확인 모드 (권장)\n검색한 뒤 [계속] 을 눌러야 다음으로 넘어갑니다. 동명이인이나 '
                 '검색 오탐이\n걱정될 때 안전합니다. 모든 사람마다 멈추므로 느립니다.',
            font=ui.font(9), fg=COLORS['on_surface'], justify='left', anchor='w'
        ).grid(row=3, column=0, columnspan=3, sticky='w', pady=(8, 0))

        # 아래: 저장
        bottom = tk.Frame(frame, bg=PANEL_BG)
        bottom.grid(row=2, column=0, columnspan=2, sticky='ew', padx=14, pady=(2, 8))
        bottom.columnconfigure(0, weight=1)
        self.calib_msg = tk.Label(bottom, text='', fg=COLORS['ok'], font=ui.font(9))
        self.calib_msg.grid(row=0, column=0, sticky='e', padx=8)
        M3Button(bottom, text='설정 저장', command=self._save_calib).grid(row=0, column=1, sticky='e')

    # ── 탭 4: 수신그룹 엑셀 (에듀파인 전용) ────
    def _field_row(self, parent, bg, items, row=1):
        """라벨 + 둥근 입력칸 묶음을 가로로 놓는다. items 는 [(키, 이름, 도움말)]."""
        for column, (key, label, hint) in enumerate(items):
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=row, column=column, sticky='ew', padx=(0 if column == 0 else 10, 0),
                      pady=(0, 4))
            cell.columnconfigure(0, weight=1)
            parent.columnconfigure(column, weight=1)
            tk.Label(cell, text=label, bg=bg, font=ui.font(9, 'bold'),
                     fg=COLORS['on_surface_variant'], anchor='w').grid(row=0, column=0, sticky='w')
            var = tk.StringVar(value=self.config.edufine.get(key, ''))
            self.edufine_vars[key] = var
            card, entry = ui.entry_field(cell, textvariable=var)
            card.grid(row=1, column=0, sticky='ew', pady=(3, 0))
            entry.bind('<FocusOut>', lambda _e: self._save_edufine_fields())

    def _tab_edufine(self, frame: ttk.Frame):
        """화면 4. 수신그룹 엑셀 (수신픽만). 왼쪽에 내 정보와 만들기, 오른쪽에 결과."""
        frame.columnconfigure(0, weight=1, uniform='excel')
        frame.columnconfigure(1, weight=1, uniform='excel')
        _title, sub = self._screen_header(frame, '에듀파인에 올릴 수신그룹 엑셀', columnspan=2)
        sub.config(text='에듀파인 [개인설정 > 개인수신그룹관리 > 일괄등록] 에 올릴 엑셀을 만듭니다.\n'
                        '한 번 등록해 두면 다음부터는 기안할 때 [수신자 지정 > 개인수신그룹] 에서 '
                        '그룹만 고르면 됩니다.')
        self.codes_status = tk.Label(frame, text='', anchor='w', font=ui.font(9, 'bold'),
                                     fg=COLORS['ok'])
        self.codes_status.grid(row=1, column=0, columnspan=2, sticky='w', padx=16, pady=(0, 6))

        self.edufine_vars = {
            '등록교육청코드': tk.StringVar(value=edufine.REGISTERING_OFFICE_CODE),
        }

        # 왼쪽: 1 내 정보, 2 수신그룹 만들기
        left = tk.Frame(frame, bg=PANEL_BG)
        left.grid(row=2, column=0, sticky='nsew', padx=(14, 7), pady=(0, 8))
        left.columnconfigure(0, weight=1)

        me = Card(left, tone='inner', pad=(18, 14))
        me.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.edufine_me_panel = me
        head = tk.Frame(me.body, bg=me.fill)
        head.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
        Chip(head, text='1', kind='info').pack(side='left', padx=(0, 8))
        self._section_title(head, '내 정보 (한 번만 입력)', me.fill).pack(side='left')
        self._field_row(me.body, me.fill, [('사용자ID', '사용자 ID', ''), ('사용자명', '사용자명', '')])
        tk.Label(me.body, text='등록교육청은 충청북도교육청으로 자동 적용됩니다.', bg=me.fill,
                 fg=COLORS['on_surface_variant'], font=ui.font(8), anchor='w'
                 ).grid(row=2, column=0, columnspan=2, sticky='w', pady=(4, 0))

        group = Card(left, tone='inner', pad=(18, 14))
        group.grid(row=1, column=0, sticky='ew')
        self.edufine_group_panel = group
        head = tk.Frame(group.body, bg=group.fill)
        head.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
        Chip(head, text='2', kind='info').pack(side='left', padx=(0, 8))
        self._section_title(head, '수신그룹 만들기', group.fill).pack(side='left')
        self._field_row(group.body, group.fill,
                        [('그룹명', '그룹명', ''), ('그룹기호', '그룹기호 (선택)', '')])
        tk.Label(group.body, bg=group.fill, fg=COLORS['on_surface_variant'],
                 font=ui.font(8), anchor='w', justify='left',
                 text='그룹명은 에듀파인에서 찾기 쉬운 이름으로 적으세요. 예) 2026 진천 초등학교\n'
                      '그룹기호는 선택 사항이니 필요 없으면 비워 두세요.'
                 ).grid(row=2, column=0, columnspan=2, sticky='w', pady=(4, 8))
        btn_row = tk.Frame(group.body, bg=group.fill)
        btn_row.grid(row=3, column=0, columnspan=2, sticky='w')
        self.edufine_make_button = M3Button(btn_row, text='수신그룹 엑셀 만들기', command=self._build_group_excel)
        self.edufine_make_button.pack(side='left')
        self.excel_result_btn = M3Button(
            btn_row,
            text='결과 대조',
            variant='tonal',
            command=self._show_excel_result,
            state='disabled'
        )
        self.excel_result_btn.pack(side='left', padx=(8, 0))
        M3Button(
            btn_row,
            text='빈 양식 받기',
            variant='text',
            command=self._save_blank_template
        ).pack(side='left', padx=(4, 0))

        # 오른쪽: 만들어진 결과
        result = Card(frame, tone='inner', pad=(18, 14))
        result.grid(row=2, column=1, sticky='nsew', padx=(7, 14), pady=(0, 8))
        top = tk.Frame(result.body, bg=result.fill)
        top.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        result.body.columnconfigure(0, weight=1)
        self._section_title(top, '만들어질 결과', result.fill).pack(side='left')
        self.edufine_chips = tk.Frame(top, bg=result.fill)
        self.edufine_chips.pack(side='right')
        self.edufine_msg = tk.Label(
            result.body, text='명단을 추출하면 여기에 엑셀에 들어갈 기관이 나옵니다.',
            bg=result.fill, fg=COLORS['on_surface_variant'], font=ui.font(9),
            justify='left', anchor='w', wraplength=380)
        self.edufine_msg.grid(row=1, column=0, sticky='ew')
        # 엑셀에서 빠지는 기관은 반드시 사유와 함께 보여 준다
        self.edufine_left_out = Card(result.body, tone='error', pad=(12, 9))
        self.edufine_left_out.grid(row=2, column=0, sticky='ew', pady=(8, 0))
        self.edufine_left_out_text = tk.Label(
            self.edufine_left_out.body, text='', bg=self.edufine_left_out.fill,
            fg=COLORS['on_error_container'], font=ui.font(9), justify='left', anchor='w',
            wraplength=360)
        self.edufine_left_out_text.pack(anchor='w')
        self.edufine_left_out.grid_remove()
        self.walker_btn = M3Button(
            result.body,
            text='코드 없는 기관 순차 복사',
            variant='outlined',
            size='sm',
            command=self._open_clipboard_walker
        )
        self.walker_btn.grid(row=3, column=0, sticky='w', pady=(8, 0))
        tk.Label(result.body, text='코드가 없는 기관은 순차 복사로 조직도에 직접 붙여넣으세요.',
                 bg=result.fill, fg=COLORS['on_surface_variant'], font=ui.font(8),
                 anchor='w').grid(row=4, column=0, sticky='w', pady=(3, 0))

        # 아래: 3 에듀파인에 올리기. 어디를 누르는지 그림으로 보여 준다.
        upload = Card(frame, tone='inner', pad=(18, 14))
        upload.grid(row=3, column=0, columnspan=2, sticky='ew', padx=14, pady=(0, 8))
        self.edufine_upload_panel = upload
        head = tk.Frame(upload.body, bg=upload.fill)
        head.grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 8))
        Chip(head, text='3', kind='info').pack(side='left', padx=(0, 8))
        self._section_title(head, '에듀파인에 올리기', upload.fill).pack(side='left')
        self.edufine_step_images = []
        for col, (number, title, desc) in enumerate(EDUFINE_UPLOAD_STEPS):
            upload.body.columnconfigure(col, weight=1, uniform='up')
            cell = tk.Frame(upload.body, bg=upload.fill)
            cell.grid(row=1, column=col, sticky='nw', padx=(0 if col == 0 else 8, 0))
            Chip(cell, text=number, kind='neutral').pack(anchor='w')
            tk.Label(cell, text=title, bg=upload.fill, font=ui.font(10, 'bold'),
                     fg=COLORS['on_surface'], anchor='w').pack(anchor='w', pady=(4, 0))
            tk.Label(cell, text=desc, bg=upload.fill, font=ui.font(8),
                     fg=COLORS['on_surface_variant'], justify='left', anchor='w',
                     wraplength=190).pack(anchor='w')
            picture = edufine_guide_image(number)
            if picture is not None:
                self.edufine_step_images.append(picture)
                tk.Label(cell, image=picture, bg=upload.fill).pack(anchor='w', pady=(4, 0))
        tk.Label(
            upload.body, bg=upload.fill, fg=COLORS['on_surface_variant'], font=ui.font(9),
            justify='left', anchor='w', wraplength=860,
            text='처음에는 기관 2~3곳짜리 시험 그룹으로 한 번 올려 보세요. '
                 '등록된 곳이 생각한 기관과 맞는지 확인하고 나서 실제 공문에 쓰시면 됩니다.'
        ).grid(row=2, column=0, columnspan=4, sticky='w', pady=(10, 0))

    def _open_org_picker(self):
        """기관 찾아보기 — 770곳에서 골라 명단에 넣는다.

        '충청북도청주교육지원청 행정과' 같은 전체경로를 외울 수는 없다.
        """
        if not self.codes.get('기관'):
            messagebox.showwarning(
                '기관코드가 없습니다',
                '앱에 기관코드 파일이 없습니다. 프로그램을 다시 받아 주세요.')
            return

        dlg = tk.Toplevel(self.root)
        dlg.title('기관 찾아보기')
        dlg.geometry(f'{ui.px(780)}x{ui.px(680)}')
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.configure(bg=PANEL_BG)

        tk.Label(dlg, text='찾을 말을 띄어쓰기로 나눠 적으면 모두 포함된 기관만 보입니다.\n'
                           '예)  청주 초등학교   ·   행정과   ·   단재 연수부',
                 bg=PANEL_BG, fg=COLORS['on_surface_variant'], font=ui.font(9),
                 justify='left').pack(anchor='w', padx=16, pady=(14, 6))

        query = tk.StringVar()
        entry = ttk.Entry(dlg, textvariable=query, font=ui.font(11))
        entry.pack(fill='x', padx=16)
        entry.focus_set()

        # 분류 버튼 — 초등학교만, 교육지원청만 처럼 한 번에 좁힌다
        self.picker_category = None
        cat_row = tk.Frame(dlg, bg=PANEL_BG)
        cat_row.pack(fill='x', padx=16, pady=(8, 2))
        counts = edufine.category_counts(self.codes)
        cat_buttons = {}

        def choose_category(name):
            self.picker_category = None if self.picker_category == name else name
            for key, btn in cat_buttons.items():
                on = key == self.picker_category
                btn.config(variant='tonal' if on else 'outlined')
            refresh()

        for name in edufine.CATEGORIES:
            if not counts.get(name):
                continue
            btn = M3Button(
                cat_row,
                text=f'{name} {counts[name]}',
                command=lambda n=name: choose_category(n),
                variant='text',
                size='sm'
            )
            btn.pack(side='left', padx=2)
            cat_buttons[name] = btn

        count_label = tk.Label(dlg, text='', bg=PANEL_BG, fg='#555',
                               font=ui.font(9), anchor='w')
        count_label.pack(fill='x', padx=16, pady=(6, 2))

        list_wrap = tk.Frame(dlg)
        list_wrap.pack(fill='both', expand=True, padx=16)
        box = tk.Listbox(list_wrap, font=ui.font(10), selectmode='extended',
                         activestyle='none', exportselection=False,
                         selectbackground=ui.acc()[2], selectforeground=ui.acc()[3])
        box.pack(side='left', fill='both', expand=True)
        bar = ttk.Scrollbar(list_wrap, orient='vertical', command=box.yview)
        bar.pack(side='right', fill='y')
        box.config(yscrollcommand=bar.set)

        shown = []

        def refresh(*_):
            nonlocal shown
            shown = edufine.search_orgs(self.codes, query.get(),
                                        category=self.picker_category)
            box.delete(0, 'end')
            for full in shown:
                box.insert('end', full)
            total = len(self.codes.get('기관', {}))
            count_label.config(text=f'{len(shown)}곳 표시  /  전체 {total}곳'
                                    f'      (Ctrl 클릭·Shift 클릭으로 여러 개 선택)')

        def add(full_names):
            existing = {i.get('org') for i in self.names_list}
            index = edufine.index_by_short_name(self.codes)
            added = 0
            for full in full_names:
                if full in existing:
                    continue
                self.names_list.append({
                    'org': full,
                    'name': '',
                    'search': edufine.display_name(self.codes, full, index),
                    'grade': 'exact',
                    'raw': full,
                    'candidates': [],
                })
                existing.add(full)
                added += 1
            self._rebuild_parsed_list()
            self._after_list_edit()
            count_label.config(
                text=f'{added}곳을 명단에 넣었습니다.  (명단 {len(self.names_list)}곳)')
            return added

        def add_selected():
            picked = [shown[i] for i in box.curselection()]
            if picked:
                add(picked)

        def add_all_shown():
            if not shown:
                return
            if len(shown) > 50 and not messagebox.askyesno(
                    '한꺼번에 넣을까요?',
                    f'지금 보이는 {len(shown)}곳을 모두 명단에 넣습니다. 계속할까요?'):
                return
            add(shown)

        query.trace_add('write', refresh)
        box.bind('<Double-Button-1>', lambda e: add_selected())
        entry.bind('<Return>', lambda e: box.focus_set())

        btns = tk.Frame(dlg, bg=PANEL_BG)
        btns.pack(pady=12)
        M3Button(btns, text='선택한 것 넣기', command=add_selected).pack(side='left', padx=4)
        M3Button(btns, text='보이는 것 전부 넣기', command=add_all_shown).pack(side='left', padx=4)
        M3Button(btns, text='닫기', command=dlg.destroy, variant='text').pack(side='left', padx=4)

        refresh()

    def _save_blank_template(self):
        """에듀파인 일괄등록 빈 양식을 저장한다.

        앱에 동봉된 원본 그대로다. 결과 엑셀도 이 파일을 열어 값만 채워 만든다.
        """
        source = edufine.TEMPLATE_FILE
        if not os.path.exists(source):
            messagebox.showerror(
                '양식을 찾을 수 없습니다',
                f'동봉된 양식 파일이 없습니다.\n\n{source}')
            return

        path = filedialog.asksaveasfilename(
            title='빈 양식 저장',
            defaultextension='.xlsx',
            initialfile='개인수신그룹_일괄등록_양식.xlsx',
            filetypes=[('엑셀 파일', '*.xlsx')]
        )
        if not path:
            return
        try:
            shutil.copyfile(source, path)
        except Exception as exc:
            logging.exception('양식 저장 실패')
            messagebox.showerror('저장 실패', f'양식을 저장하지 못했습니다.\n\n{exc}')
            return

        self.status_var.set(f'빈 양식 저장 완료: {path}')
        messagebox.showinfo(
            '저장했습니다',
            f'빈 양식을 저장했습니다.\n\n{path}\n\n'
            '이 서식 그대로 [수신그룹 엑셀 만들기] 가 결과를 만들어 줍니다.')

    def _save_edufine_fields(self):
        for key, var in getattr(self, 'edufine_vars', {}).items():
            self.config.edufine[key] = var.get().strip()
        self.config.edufine['등록교육청코드'] = edufine.REGISTERING_OFFICE_CODE
        self.config.save()
        self._refresh_edufine_status()

    def _refresh_edufine_status(self):
        label = getattr(self, 'codes_status', None)
        orgs = self.codes.get('기관', {})
        if label:
            if orgs:
                label.config(
                    text=f'충청북도교육청으로 고정  ·  기관코드 {len(orgs)}곳 기본 제공',
                    fg=COLORS['ok'])
            else:
                label.config(text='내장 기관코드 파일을 찾을 수 없습니다', fg=COLORS['error'])

        msg = getattr(self, 'edufine_msg', None)
        chips = getattr(self, 'edufine_chips', None)
        banner = getattr(self, 'edufine_left_out', None)
        if chips is not None:
            for child in chips.winfo_children():
                child.destroy()
        if not msg:
            return
        if not self.names_list:
            msg.config(text='명단을 추출하면 여기에 엑셀에 들어갈 기관이 나옵니다.')
            if banner is not None:
                banner.grid_remove()
            return
        ready, missing = self._split_confirmed()
        pending = [i for i in self.names_list if i.get('grade') not in AUTO_GRADES]
        msg.config(text=f'엑셀에 들어갈 기관 {len(ready)}곳')
        if chips is not None:
            Chip(chips, text=f'들어감 {len(ready)}곳', kind='ok').pack(side='left')
            left_out = len(missing) + len(pending)
            if left_out:
                Chip(chips, text=f'빠짐 {left_out}곳', kind='err').pack(side='left', padx=(6, 0))
        # 빠지는 기관은 조용히 넘기지 않는다. 이름과 사유를 바로 보여 준다.
        lines = [f"{r.get('name') or r.get('raw')}  ({r.get('reason', '코드 없음')})" for r in missing]
        lines += [f"{i.get('raw', '')}  (확정되지 않음)" for i in pending]
        if banner is not None:
            if lines:
                shown = '\n'.join(lines[:5])
                more = f'\n외 {len(lines) - 5}곳' if len(lines) > 5 else ''
                self.edufine_left_out_text.config(
                    text=f'{len(lines)}곳은 엑셀에서 빠집니다.\n{shown}{more}')
                banner.grid()
            else:
                banner.grid_remove()

    def _confirmed_orgs(self) -> list:
        """확정된 기관만. 추정·실패 항목은 엑셀로 내보내지 않는다."""
        return [item for item in self.names_list
                if item.get('org') and item.get('grade') in AUTO_GRADES]

    def _split_confirmed(self):
        rows = [{'name': item['org']} for item in self._confirmed_orgs()]
        return edufine.split_by_code(rows, self.codes)

    def _build_group_excel(self):
        self._save_edufine_fields()

        if not self.codes.get('기관'):
            messagebox.showwarning(
                '기관코드를 찾을 수 없습니다',
                '앱에 포함된 기관코드 파일이 없습니다. 프로그램을 다시 받아주세요.')
            return
        if not self.config.edufine_ready():
            messagebox.showwarning(
                '내 정보가 비었습니다',
                "[수신그룹 엑셀] 탭의 '내 정보'에 사용자 ID와 사용자명을 적어 주세요.")
            return

        group_name = self.config.edufine.get('그룹명', '').strip()
        if not group_name:
            messagebox.showwarning('그룹명이 필요합니다', "[수신그룹 엑셀] 탭의 '수신그룹 만들기'에 그룹명을 적어 주세요.")
            return

        pending = [i for i in self.names_list if i.get('grade') not in AUTO_GRADES]
        if pending:
            names = ', '.join(i.get('raw', '') for i in pending[:5])
            more = ' …' if len(pending) > 5 else ''
            if not messagebox.askyesno(
                    '확인이 안 된 기관이 있습니다',
                    f'{len(pending)}곳이 아직 확정되지 않았습니다. 이대로 빼고 만들까요?\n\n'
                    f'{names}{more}\n\n'
                    '[명단 입력] 탭에서 더블클릭하면 후보 중에서 고를 수 있습니다.'):
                return

        ready, missing = self._split_confirmed()
        if not ready:
            messagebox.showwarning(
                '등록할 기관이 없습니다',
                '확정된 기관 중 코드를 가진 곳이 하나도 없습니다.')
            return
        if missing:
            lines = '\n'.join(
                f"· {r.get('name') or r.get('raw')} ({r.get('reason', '코드 없음')})"
                for r in missing[:10])
            more = f'\n… 외 {len(missing) - 10}곳' if len(missing) > 10 else ''
            if not messagebox.askyesno(
                    '코드가 없는 기관이 있습니다',
                    f'{len(missing)}곳은 엑셀에 들어가지 않습니다. 계속할까요?\n\n'
                    f'{lines}{more}\n\n'
                    '이 기관들은 [코드 없는 기관 순차 복사] 로 조직도에 직접 넣으면 됩니다.'):
                return

        path = filedialog.asksaveasfilename(
            title='수신그룹 엑셀 저장',
            defaultextension='.xlsx',
            initialfile=edufine.default_output_name(group_name),
            filetypes=[('엑셀 파일', '*.xlsx')]
        )
        if not path:
            return

        try:
            edufine.build_workbook(ready, dict(self.config.edufine), path)
        except Exception as exc:
            logging.exception('수신그룹 엑셀 생성 실패')
            messagebox.showerror('저장 실패', f'엑셀을 만들지 못했습니다.\n\n{exc}')
            return

        # 만들려던 목록이 아니라 파일에 실제로 써진 줄과 맞춰 본다.
        try:
            written = edufine.read_written_codes(path)
        except Exception as exc:
            logging.exception('수신그룹 엑셀 다시 읽기 실패')
            self.status_var.set(f'수신그룹 엑셀 저장 완료: {len(ready)}곳')
            messagebox.showwarning(
                '저장은 했지만 확인하지 못했습니다',
                f'{len(ready)}곳을 넣어 엑셀을 만들었지만, 다시 열어 확인하지 못했습니다.\n\n'
                f'{path}\n\n{exc}\n\n'
                '올리기 전에 엑셀을 열어 줄 수가 맞는지 한 번 보세요.')
            return

        tally = reconcile.edufine_tally(self.names_list, self.codes, written)
        self.last_excel_result = {'tally': tally, 'path': path, 'rows': len(written)}
        self._refresh_excel_result_state()
        logging.info('수신그룹 엑셀 결과: 추출 %s, 들어감 %s, 빠짐 %s, 줄 %s',
                     tally.total, len(tally.placed), tally.short, len(written))
        self.status_var.set(
            f'수신그룹 엑셀 저장 완료  ·  {reconcile.summary_line(tally, "곳")}')
        self._show_excel_result()

    def _show_excel_result(self):
        """추출한 기관 수와 엑셀에 실제로 써진 수를 대조하는 창."""
        result = self.last_excel_result
        if not result:
            messagebox.showinfo('알림', '아직 만든 수신그룹 엑셀이 없습니다.')
            return
        tally = result['tally']
        note = (f'엑셀을 다시 열어 {result["rows"]}줄을 확인했습니다.\n{result["path"]}\n\n'
                '에듀파인 [개인설정 > 개인수신그룹관리 > 일괄등록] 에서 이 파일을 올리세요. '
                '올린 뒤 수신그룹에 보이는 기관 수를 아래에 적으면 빠진 곳이 있는지 알려 드립니다.')
        if any(reason == reconcile.NO_CODE for _item, reason in tally.missing):
            note += '\n코드가 없는 기관은 [코드 없는 기관 순차 복사] 로 조직도에 직접 넣으면 됩니다.'
        ResultReport(
            self.root, tally, unit='곳', who='기관',
            where='에듀파인 수신그룹', into='엑셀에',
            count_label='에듀파인 수신그룹에 보이는 기관 수:',
            note=note, title='수신픽 결과 대조')

    def _refresh_excel_result_state(self):
        btn = getattr(self, 'excel_result_btn', None)
        if btn:
            btn.config(state='normal' if self.last_excel_result else 'disabled')

    # ── 클립보드 순차 복사 ─────────────────────
    def _open_clipboard_walker(self):
        _, missing = self._split_confirmed()
        items = [i.get('name') or i.get('raw', '') for i in missing
                 if i.get('reason') == '코드 없음']
        if not items:
            messagebox.showinfo(
                '코드 없는 기관이 없습니다',
                '확정된 기관 가운데 기관코드가 없어 직접 넣어야 할 곳이 없습니다.')
            return
        ClipboardWalker(self.root, items)

    # ── 탭 3: 자동 선택 ────────────────────────
    def _tab_auto(self, frame: ttk.Frame):
        """화면 3. 자동 선택 (소통픽만). 위쪽에 진행 판, 가운데 단추, 아래에 진행 기록."""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        _title, self.auto_intro = self._screen_header(frame, '자동으로 골라 담습니다')

        # 진행 판: 큰 숫자, 담김/빠짐 칩, 진행 막대
        panel = Card(frame, tone='inner', pad=(18, 12))
        panel.grid(row=1, column=0, sticky='ew', padx=14, pady=(0, 8))
        panel.body.columnconfigure(0, weight=1)
        top = tk.Frame(panel.body, bg=panel.fill)
        top.grid(row=0, column=0, sticky='ew')
        self.prog_label = tk.Label(top, text='0 / 0', font=ui.font(20, 'bold'),
                                   bg=panel.fill, fg=COLORS['on_surface'])
        self.prog_label.pack(side='left')
        self.auto_chips = tk.Frame(top, bg=panel.fill)
        self.auto_chips.pack(side='left', padx=14)
        self.progress = ttk.Progressbar(panel.body, mode='determinate',
                                        style='Accent.Horizontal.TProgressbar')
        self.progress.grid(row=1, column=0, sticky='ew', pady=(8, 2))

        # 단추 줄
        btn_frame = tk.Frame(frame, bg=PANEL_BG)
        btn_frame.grid(row=2, column=0, sticky='ew', padx=14, pady=(0, 8))
        self.start_btn = M3Button(btn_frame, text='자동 선택 시작', icon='play', command=self._start)
        self.start_btn.pack(side='left', padx=(0, 6))
        self.continue_btn = M3Button(
            btn_frame,
            text='계속',
            variant='tonal',
            state='disabled',
            command=self._resume
        )
        self.continue_btn.pack(side='left', padx=3)
        self.stop_btn = M3Button(
            btn_frame,
            text='중지',
            variant='danger',
            state='disabled',
            command=self._stop
        )
        self.stop_btn.pack(side='left', padx=3)
        self.retry_failed_btn = M3Button(
            btn_frame,
            text='실패 항목만 다시 실행',
            variant='tonal',
            state='disabled',
            command=self._retry_failed
        )
        self.retry_failed_btn.pack(side='left', padx=3)
        self.compare_btn = M3Button(
            btn_frame,
            text='소통메신저와 비교',
            variant='outlined',
            command=self._compare_with_messenger
        )
        self.compare_btn.pack(side='left', padx=3)
        M3Button(
            btn_frame,
            text='로그 지우기',
            variant='text',
            size='sm',
            command=self._log_clear
        ).pack(side='right')

        # 진행 기록
        log_card, self.log = ui.text_field(frame, height=12, wrap='none',
                                           font=ui.font(9))
        self.log.configure(state='disabled')
        self.log.tag_config('ok', foreground=COLORS['ok'])
        self.log.tag_config('fail', foreground=COLORS['error'])
        log_card.grid(row=3, column=0, sticky='nsew', padx=14, pady=(0, 10))

    def _refresh_auto_chips(self):
        """진행 판의 담김/빠짐 칩."""
        row = getattr(self, 'auto_chips', None)
        if row is None:
            return
        for child in row.winfo_children():
            child.destroy()
        added = sum(1 for i in self.names_list if i.get('added'))
        failed = sum(1 for i in self.names_list if i.get('failure_reason'))
        if added:
            Chip(row, text=f'담김 {added}', kind='ok').pack(side='left', padx=(0, 6))
        if failed:
            Chip(row, text=f'빠짐 {failed}', kind='err').pack(side='left')

    # ── 제품별 사용 방법 ────────────────────────
    def _tab_help(self, frame: ttk.Frame, target: str):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        label = TARGET_LABELS[target]
        head = tk.Frame(frame, bg=PANEL_BG)
        head.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 4))
        head.columnconfigure(0, weight=1)
        tk.Label(head, text=f'{label} 사용법', font=ui.font(18, 'bold'),
                 fg=COLORS['on_surface'], anchor='w').grid(row=0, column=0, sticky='w')
        video_btn = M3Button(
            head,
            text='사용법 영상 보기 (YouTube)',
            icon='play',
            command=lambda selected=target: webbrowser.open(GUIDE_VIDEO_URLS[selected]),
            variant='tonal'
        )
        video_btn.grid(row=0, column=1, sticky='e')
        if target == TARGET_MESSENGER:
            self.sotong_video_btn = video_btn
        else:
            self.susin_video_btn = video_btn

        txt_card, txt = ui.text_field(frame, height=12, wrap='word', width=40)
        txt_card.grid(row=1, column=0, sticky='nsew', padx=14, pady=(4, 10))
        self._fill_help(txt, HELP_TEXTS[target])
        txt.config(state='disabled')

    @staticmethod
    def _fill_help(txt, content):
        """도움말 글을 넣는다. 글 모양 장식선(━ ─)은 빼고, ■ 로 시작하는 큰 제목은 굵게 한다."""
        txt.tag_config('h', font=ui.font(12, 'bold'), foreground=COLORS['on_surface'],
                       spacing1=8, spacing3=4)
        previous_blank = True
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped and set(stripped) <= set('━─═-'):
                continue
            if not stripped:
                if previous_blank:
                    continue
                previous_blank = True
                txt.insert('end', '\n')
                continue
            previous_blank = False
            if stripped.startswith('■'):
                txt.insert('end', stripped.lstrip('■ ').strip() + '\n', 'h')
            else:
                txt.insert('end', line.rstrip() + '\n')

    def _format_item_label(self, item: dict) -> str:
        return format_item_label(item)

    def _refresh_ready_status(self):
        label = getattr(self, 'ready_status', None)
        if not label:
            return
        count = len(self.names_list)
        where = TARGET_LABELS[self.config.target]
        if self.is_edufine():
            # 좌표·대기시간은 에듀파인과 무관하다. 대신 엑셀에 필요한 것을 보여준다.
            me = '입력됨' if self.config.edufine_ready() else '필요'
            codes = len(self.codes.get('기관', {}))
            label.config(
                text=f'{where}  |  명단 {count}곳  ·  기관코드 {codes}곳 보유  ·  내 정보 {me}'
            )
        else:
            positions = '완료' if self.config.is_calibrated() else '미설정'
            manual = '켜짐' if self.config.data.get('manual_confirm', False) else '꺼짐'
            delay = self.config.data.get('search_delay', 0.5)
            label.config(
                text=f'{where}  |  명단 {count}명  ·  위치 {positions}  ·  '
                     f'수동 확인 {manual}  ·  대기 {delay}초'
            )

    def _refresh_failed_retry_state(self):
        retryable = any(item.get('failure_reason')
                        and item.get('failure_reason') != FAIL_DUPLICATE
                        for item in self.names_list)
        states = {'retry_failed_btn': retryable}
        for name, on in states.items():
            btn = getattr(self, name, None)
            if btn:
                btn.config(state='normal' if on else 'disabled')

    @staticmethod
    def _org_needs_review(item: dict) -> bool:
        """사람이 확정하거나 바로잡아야 하는 수신픽 항목인가."""
        return (item.get('grade') not in AUTO_GRADES
                or bool(item.get('code_missing')))

    def _summarize_org_rows(self, rows: list, index: dict) -> tuple:
        """중복 입력을 최종 기관 기준으로 묶어 (항목, 중복 요약)을 만든다."""
        grouped = {}
        ordered_keys = []
        for row in rows:
            auto = row.get('grade') in AUTO_GRADES
            name = row.get('name') or ''
            raw = (row.get('raw') or row.get('line') or '').strip()
            if auto and name:
                key = ('confirmed', name)
            else:
                key = ('pending', row.get('grade'), ''.join(raw.split()).casefold())

            if key in grouped:
                grouped[key]['source_count'] += 1
                continue

            search = edufine.display_name(self.codes, name, index) if name else raw
            code_missing = False
            if auto and name:
                entry, _ = edufine.lookup_code(self.codes, name, index)
                code_missing = entry is None
            grouped[key] = {
                'org': name,
                'name': '',
                'search': search,
                'grade': row.get('grade'),
                'raw': raw,
                'candidates': list(row.get('candidates') or []),
                'source_count': 1,
                'code_missing': code_missing,
            }
            ordered_keys.append(key)

        items = [grouped[key] for key in ordered_keys]
        duplicates = [
            {
                'name': item.get('search') or item.get('org') or item.get('raw'),
                'count': item['source_count'],
            }
            for item in items if item.get('source_count', 1) > 1
        ]
        return items, duplicates

    def _refresh_org_review_state(self):
        """중복과 확인 필요 항목을 명단 화면에 계속 보여준다."""
        summary = getattr(self, 'org_issue_summary', None)
        card = getattr(self, 'org_issue_card', None)
        button = getattr(self, 'bulk_fix_btn', None)
        if summary is None or button is None:
            return
        if not self.is_edufine():
            if card is not None:
                card.grid_remove()
            button.config(state='disabled')
            return

        review = [item for item in self.names_list if self._org_needs_review(item)]
        button.config(state='normal' if review else 'disabled')
        lines = []
        if self.last_org_duplicates:
            shown = ', '.join(
                f"{item['name']} {item['count']}회 입력 (중복 {item['count'] - 1}건)"
                for item in self.last_org_duplicates[:8]
            )
            more = f' 외 {len(self.last_org_duplicates) - 8}종' \
                if len(self.last_org_duplicates) > 8 else ''
            lines.append(f'중복 입력: {shown}{more} · 목록에는 한 번만 남겼습니다.')
        if review:
            lines.append(
                f'확인 필요 {len(review)}곳입니다. 붉은 항목은 '
                '[확인 필요 기관 일괄 수정]에서 한 번에 처리하세요.'
            )

        if lines:
            if card is not None:
                card.set_tone('warn')
                card.grid()
            summary.config(text='\n'.join(lines), bg=card.fill if card else PANEL_BG,
                           fg=COLORS['on_warn_container'])
        else:
            summary.config(text='')
            if card is not None:
                card.grid_remove()

    def _record_org_extraction(self):
        """개인정보 없이 최근 수신픽 추출 결과를 설정 파일에 보관한다."""
        confirmed = sum(
            1 for item in self.names_list if item.get('grade') in AUTO_GRADES)
        review = sum(1 for item in self.names_list if self._org_needs_review(item))
        entry = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'confirmed': confirmed,
            'review': review,
            'duplicates': [dict(item) for item in self.last_org_duplicates],
            'items': [
                {
                    'name': item.get('search') or item.get('org') or item.get('raw', ''),
                    'status': item.get('grade', ''),
                    'source_count': int(item.get('source_count') or 1),
                    'code_missing': bool(item.get('code_missing')),
                }
                for item in self.names_list
            ],
        }
        self.config.org_extract_history.append(entry)
        self.config.org_extract_history = self.config.org_extract_history[
            -MAX_ORG_EXTRACT_HISTORY:
        ]
        try:
            self.config.save()
        except Exception:
            logging.exception('수신픽 추출 기록 저장 실패')
        duplicate_log = ', '.join(
            f"{item['name']}={item['count']}회" for item in self.last_org_duplicates)
        logging.info(
            '수신픽 추출: 확정=%s, 확인필요=%s, 중복=%s',
            confirmed, review, duplicate_log or '없음')

    def _open_org_history(self):
        """최근 수신픽 추출 기록을 읽기 전용 창으로 보여준다."""
        history = list(getattr(self.config, 'org_extract_history', []))
        if not history:
            messagebox.showinfo('추출 기록', '아직 저장된 수신픽 추출 기록이 없습니다.')
            return

        dlg = tk.Toplevel(self.root)
        dlg.title('수신픽 추출 기록')
        dlg.geometry(f'{ui.px(800)}x{ui.px(620)}')
        dlg.transient(self.root)
        dlg.configure(bg=PANEL_BG)

        tk.Label(
            dlg,
            text=f'최근 {len(history)}회 기록 · 기관명과 상태만 저장하며 원문과 파일 경로는 저장하지 않습니다.',
            bg=ui.acc()[2], fg=ui.acc()[3], font=ui.font(9, 'bold'),
            anchor='w', padx=12, pady=8
        ).pack(fill='x')
        text_card, text = ui.text_field(dlg, height=14, wrap='word', font=ui.font(9))
        text_card.pack(fill='both', expand=True, padx=12, pady=10)

        status_names = {
            'exact': '확정', 'abbr': '확정', 'prefix': '확정',
            'fuzzy': '추정·확인 필요', 'ambiguous': '동명 기관·확인 필요',
            'none': '찾지 못함',
        }
        for record in reversed(history):
            text.insert(
                'end',
                f"[{record.get('timestamp', '-')}]  확정 {record.get('confirmed', 0)}곳"
                f" · 확인 필요 {record.get('review', 0)}곳\n",
                'heading',
            )
            duplicates = record.get('duplicates') or []
            if duplicates:
                text.insert('end', '  중복: ' + ', '.join(
                    f"{item.get('name', '')} {item.get('count', 0)}회 입력 "
                    f"(중복 {max(0, item.get('count', 0) - 1)}건)"
                    for item in duplicates) + '\n')
            for item in record.get('items') or []:
                status = status_names.get(item.get('status'), item.get('status') or '-')
                if item.get('code_missing'):
                    status = '기관코드 없음'
                count = int(item.get('source_count') or 1)
                repeat = f' · 입력 {count}회' if count > 1 else ''
                text.insert('end', f"  · {item.get('name', '')} ({status}{repeat})\n")
            text.insert('end', '\n')
        text.tag_config('heading', foreground=ui.acc()[0], font=ui.font(10, 'bold'))
        text.config(state='disabled')
        M3Button(dlg, text='닫기', command=dlg.destroy, variant='tonal').pack(pady=(0, 12))

    def _confirm_org_item(self, item: dict, full_name: str):
        """후보에서 고른 기관을 확정하고 코드 보유 여부까지 다시 확인한다."""
        full_name = (full_name or '').strip()
        if not full_name:
            return False
        index = edufine.index_by_short_name(self.codes)
        entry, _ = edufine.lookup_code(self.codes, full_name, index)
        item['org'] = full_name
        item['search'] = edufine.display_name(self.codes, full_name, index)
        item['grade'] = 'exact'
        item['candidates'] = []
        item['code_missing'] = entry is None
        item.pop('failure_reason', None)
        self._rebuild_parsed_list()
        self._after_list_edit()
        return True

    def _open_bulk_org_editor(self):
        """확인 필요 기관을 한 창에서 차례로 확정하거나 제외한다."""
        if self._block_while_running():
            return
        if not any(self._org_needs_review(item) for item in self.names_list):
            messagebox.showinfo('확인 완료', '확인이 필요한 기관이 없습니다.')
            return

        dlg = tk.Toplevel(self.root)
        dlg.title('확인 필요 기관 일괄 수정')
        dlg.geometry(f'{ui.px(900)}x{ui.px(660)}')
        dlg.minsize(ui.px(800), ui.px(600))
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.configure(bg=PANEL_BG)
        dlg.columnconfigure(0, weight=1)
        dlg.columnconfigure(1, weight=2)
        dlg.rowconfigure(2, weight=1)

        tk.Label(
            dlg,
            text='같은 이름이 여럿이면 신통픽은 아무것도 고르지 않습니다.\n'
                 '공문이 엉뚱한 곳으로 가지 않도록 직접 골라 주세요.\n'
                 '1. 왼쪽에서 기관을 하나 고릅니다   2. 오른쪽 목록에서 맞는 기관을 고릅니다\n'
                 '3. [선택 기관으로 확정] 을 누릅니다',
            bg=COLORS['warn_container'], fg=COLORS['on_warn_container'],
            font=ui.font(9, 'bold'), justify='left', wraplength=ui.px(780),
            anchor='w', padx=14, pady=10
        ).grid(row=0, column=0, columnspan=2, sticky='ew')

        tk.Label(dlg, text='확인 필요 기관', bg=PANEL_BG, fg=COLORS['on_surface_variant'],
                 font=ui.font(10, 'bold')).grid(
                     row=1, column=0, sticky='w', padx=12, pady=(10, 4))
        detail_var = tk.StringVar(value='기관을 선택하세요.')
        tk.Label(dlg, textvariable=detail_var, bg=PANEL_BG, fg=COLORS['on_surface_variant'],
                 font=ui.font(10, 'bold'), anchor='w').grid(
                     row=1, column=1, sticky='ew', padx=12, pady=(10, 4))

        # exportselection 을 끄지 않으면, 오른쪽 검색창에 글자를 넣는 순간
        # 이 목록의 선택이 풀린다. 그러면 어느 기관을 고치는 중인지 잃어버려
        # 검색 결과가 비고 [선택 기관으로 확정] 도 듣지 않는다.
        pending_box = tk.Listbox(
            dlg, font=ui.font(9), activestyle='none', exportselection=False,
            fg=COLORS['error'], selectbackground=COLORS['error'], selectforeground='white')
        pending_box.grid(row=2, column=0, sticky='nsew', padx=(12, 6), pady=(0, 8))

        right = tk.Frame(dlg, bg=PANEL_BG)
        right.grid(row=2, column=1, sticky='nsew', padx=(6, 12), pady=(0, 8))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)
        tk.Label(right, text='기관 검색', bg=PANEL_BG, fg='#555',
                 font=ui.font(9)).grid(row=0, column=0, sticky='w')
        query = tk.StringVar()
        hint_var = tk.StringVar(value='')
        search_entry = ttk.Entry(right, textvariable=query, font=ui.font(10))
        search_entry.grid(row=1, column=0, sticky='ew', pady=(2, 2))
        tk.Label(right, textvariable=hint_var, bg=PANEL_BG, fg=ui.acc()[0],
                 font=ui.font(9), anchor='w').grid(
                     row=2, column=0, sticky='ew', pady=(0, 4))
        result_box = tk.Listbox(
            right, font=ui.font(9), activestyle='none', exportselection=False,
            selectbackground=ui.acc()[2], selectforeground=ui.acc()[3])
        result_box.grid(row=3, column=0, sticky='nsew')

        pending_indices = []
        shown = []

        def current_pair():
            selected = pending_box.curselection()
            if not selected or selected[0] >= len(pending_indices):
                return None, None
            idx = pending_indices[selected[0]]
            return idx, self.names_list[idx]

        def refresh_results(*_):
            nonlocal shown
            _, item = current_pair()
            result_box.delete(0, 'end')
            if item is None:
                shown = []
                return
            found = []
            for candidate in item.get('candidates') or []:
                found.extend(edufine.search_orgs(self.codes, candidate, limit=20))
            found.extend(edufine.search_orgs(self.codes, query.get(), limit=200))
            shown = list(dict.fromkeys(found))
            for full in shown:
                result_box.insert('end', full)
            if shown:
                result_box.selection_set(0)
                result_box.activate(0)
                hint_var.set(f'{len(shown)}곳을 찾았습니다. 맞는 곳을 고르세요.')
            else:
                # 빈 상자만 보여 주면 무엇을 해야 할지 알 수 없다.
                hint_var.set('찾지 못했습니다. 검색어를 줄여 보세요 (예: 원남초).')

        def load_selected(*_):
            _, item = current_pair()
            if item is None:
                return
            detail_var.set(f"입력값: {item.get('raw', '')}")
            query.set(item.get('search') or item.get('org') or item.get('raw', ''))
            refresh_results()

        def refresh_pending(select_at=0):
            nonlocal pending_indices
            pending_indices = [
                i for i, item in enumerate(self.names_list)
                if self._org_needs_review(item)
            ]
            pending_box.delete(0, 'end')
            for idx in pending_indices:
                pending_box.insert('end', self._format_item_label(self.names_list[idx]))
            if not pending_indices:
                detail_var.set('모든 기관을 확인했습니다.')
                result_box.delete(0, 'end')
                hint_var.set('')
                query.set('')
                return
            position = min(select_at, len(pending_indices) - 1)
            pending_box.selection_set(position)
            pending_box.activate(position)
            load_selected()

        def confirm_selected():
            selected = result_box.curselection()
            idx, item = current_pair()
            if idx is None or not selected or selected[0] >= len(shown):
                messagebox.showwarning(
                    '기관을 선택하세요', '오른쪽 검색 결과에서 정확한 기관을 선택하세요.',
                    parent=dlg)
                return
            self._confirm_org_item(item, shown[selected[0]])
            refresh_pending()

        def remove_selected():
            idx, item = current_pair()
            if idx is None:
                return
            if not messagebox.askyesno(
                    '명단에서 제외할까요?',
                    f"{item.get('raw') or item.get('search', '')}\n\n이 항목을 명단에서 제외합니다.",
                    parent=dlg):
                return
            del self.names_list[idx]
            self._rebuild_parsed_list()
            self._after_list_edit()
            refresh_pending()

        pending_box.bind('<<ListboxSelect>>', load_selected)
        result_box.bind('<Double-Button-1>', lambda _e: confirm_selected())
        query.trace_add('write', refresh_results)

        buttons = tk.Frame(dlg, bg=PANEL_BG)
        buttons.grid(row=3, column=0, columnspan=2, pady=(2, 12))
        M3Button(buttons, text='선택 기관으로 확정', command=confirm_selected).pack(side='left', padx=4)
        M3Button(buttons, text='명단에서 제외', command=remove_selected, variant='danger').pack(side='left', padx=4)
        M3Button(buttons, text='완료', command=dlg.destroy, variant='tonal').pack(side='left', padx=4)

        refresh_pending()
        search_entry.focus_set()

    def _rebuild_parsed_list(self):
        self.parsed_list.delete(0, 'end')
        for item in self.names_list:
            self.parsed_list.insert('end', self._format_item_label(item))
            if item.get('failure_reason'):
                self.parsed_list.itemconfig('end', {'bg': COLORS['error_container'],
                                                    'fg': COLORS['on_error_container']})
            elif self.is_edufine() and self._org_needs_review(item):
                self.parsed_list.itemconfig('end', {'bg': COLORS['warn_container'],
                                                    'fg': COLORS['on_warn_container']})
            elif not item.get('org'):
                self.parsed_list.itemconfig('end', {'bg': '#ECECF2',
                                                    'fg': COLORS['on_surface_variant']})
        self._refresh_summary_chips()
        self._refresh_ready_status()
        self._refresh_failed_retry_state()
        self._refresh_org_review_state()

    # ── 의존성 확인 ────────────────────────────

    # update check
    def _check_for_update_async(self):
        threading.Thread(target=self._check_for_update_worker, daemon=True).start()

    def _check_for_update_worker(self):
        try:
            req = urllib.request.Request(
                LATEST_RELEASE_API,
                headers={'User-Agent': f'{APP_NAME}/{APP_VERSION}'}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            latest = (data.get('tag_name') or data.get('name') or '').strip().lstrip('vV')
            url = data.get('html_url') or RELEASES_PAGE
            if latest and _is_newer_version(latest, APP_VERSION):
                self.root.after(0, lambda: self._show_update_notice(latest, url))
        except Exception as exc:
            logging.info("업데이트 확인 실패: %s", exc)

    def _show_update_notice(self, latest: str, url: str):
        open_page = messagebox.askyesno(
            '새 버전 알림',
            f'{APP_NAME} 새 버전이 나왔습니다.\n\n'
            f'현재 버전: {APP_VERSION}\n'
            f'최신 버전: {latest}\n\n'
            '다운로드 페이지를 열까요?'
        )
        if open_page:
            webbrowser.open(url)

    def _check_deps(self):
        missing = []
        if pyautogui is None:
            missing.append('pyautogui')
        if pyperclip is None:
            missing.append('pyperclip')
        if missing:
            messagebox.showerror(
                '패키지 누락',
                f'필수 패키지 미설치: {", ".join(missing)}\n\n'
                '시작.bat 을 실행하면 자동으로 설치됩니다.'
            )

    # ── 엑셀 열기 ──────────────────────────────
    def _open_excel(self):
        if openpyxl is None:
            messagebox.showerror('오류', 'pip install openpyxl 필요')
            return
        path = filedialog.askopenfilename(
            filetypes=[('Excel', '*.xlsx'), ('모든 파일', '*.*')]
        )
        if not path:
            return
        try:
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            lines = []
            for row in ws.iter_rows():
                cells = [str(c.value).strip() if c.value is not None else '' for c in row]
                if any(cells):
                    lines.append('\t'.join(cells))
            wb.close()
            self.input_text.delete('1.0', 'end')
            self.input_text.insert('1.0', '\n'.join(lines))
            self.status_var.set(f'엑셀 로드: {os.path.basename(path)}')
        except Exception as e:
            messagebox.showerror('파일 읽기 실패', f'파일 읽기 실패:\n{e}')

    # ── HWP 열기 ───────────────────────────────
    def _open_hwp(self):
        path = filedialog.askopenfilename(
            filetypes=[('HWP', '*.hwp *.hwpx'), ('모든 파일', '*.*')]
        )
        if not path:
            return
        self.status_var.set('HWP 파일 읽는 중...')
        self.root.update()
        text = extract_hwp_text(path)
        if text:
            self.input_text.delete('1.0', 'end')
            self.input_text.insert('1.0', text)
            self.status_var.set(f'HWP 로드: {os.path.basename(path)}')
        else:
            messagebox.showwarning(
                'HWP 읽기 실패',
                'HWP 파일을 자동으로 읽지 못했습니다.\n\n'
                '한글에서 표를 직접 복사(Ctrl+C)해서\n'
                '입력창에 붙여넣어 주세요.'
            )
            self.status_var.set('HWP 읽기 실패. 직접 복사해서 붙여넣어 주세요')

    # ── 명단 추출 ──────────────────────────────
    # ── 도구 전환 ──────────────────────────────
    def is_edufine(self) -> bool:
        return self.config.target == TARGET_EDUFINE

    def _guide_target_map(self) -> dict:
        """가이드 단계 이름과 화면의 실제 조작 대상을 연결한다."""
        return {
            'input_text': self.input_text,
            'parse_button': self.parse_button,
            'parsed_list': self.parsed_list,
            'bulk_fix_button': self.bulk_fix_btn,
            'calibration_panel': self.calibration_panel,
            'start_button': self.start_btn,
            'edufine_me_panel': self.edufine_me_panel,
            'edufine_group_panel': self.edufine_group_panel,
            'edufine_make_button': self.edufine_make_button,
        }

    def _show_onboarding(self, target: str):
        current = self.guide_dialog
        if current is not None:
            try:
                if current.winfo_exists():
                    current.lift()
                    return
            except tk.TclError:
                self.guide_dialog = None

        tab_map = {
            'input': self.tab_input,
            'calib': self.messenger_tabs[0][0],
            'auto': self.messenger_tabs[1][0],
            'edufine': self.edufine_tabs[0][0],
        }

        def show_target(tab_key, widget_key):
            tab = tab_map.get(tab_key)
            if tab is not None:
                self.nb.select(tab)
            self.root.update_idletasks()
            return self._guide_target_map().get(widget_key)

        def close_guide():
            self.guide_dialog = None

        self.guide_dialog = WalkthroughDialog(
            self.root,
            f'{TARGET_LABELS[target]} 사용 가이드',
            GUIDE_STEPS[target],
            show_target,
            close_guide,
        )

    def _automation_is_running(self) -> bool:
        """소통픽 자동화 워커가 아직 움직이고 있는가."""
        return bool(self.worker_thread and self.worker_thread.is_alive())

    def _block_while_running(self) -> bool:
        """실행 중 명단이나 도구가 바뀌지 않도록 막는다."""
        if not self._automation_is_running():
            return False
        messagebox.showwarning(
            '자동 선택 실행 중',
            '자동 선택이 끝나거나 중지될 때까지 명단과 도구를 바꿀 수 없습니다.')
        return True

    def _choose_target(self, target: str):
        if target == self.config.target:
            return
        if self._block_while_running():
            self.target_var.set(self.config.target)
            return
        if self.guide_dialog is not None:
            self.guide_dialog.finish()
        # 소통픽은 사람, 수신픽은 기관을 다룬다. 한쪽 명단이 다른 쪽에 넘어가면
        # 헷갈리므로, 도구마다 입력 글과 명단을 따로 보관했다가 돌아오면 되살린다.
        self._stash_tool_state(self.config.target)
        self.target_var.set(target)
        self.config.use_target(target)
        self.config.save()
        self._restore_tool_state(target)
        self._apply_target()

    def _stash_tool_state(self, target: str):
        """지금 도구의 입력 글, 명단, 상태 글을 보관한다 (앱을 켜 둔 동안)."""
        try:
            status = (self.parse_status.cget('text'), self.parse_status.cget('fg'))
        except Exception:
            status = ('', '#555')
        self.tool_states[target] = {
            'input': self.input_text.get('1.0', 'end').rstrip('\n'),
            'names': self.names_list,
            'duplicates': self.last_org_duplicates,
            'status': status,
            'direct': self.direct_var.get() if hasattr(self, 'direct_var') else '',
        }

    def _restore_tool_state(self, target: str):
        """그 도구에서 쓰던 입력 글과 명단을 되살린다. 처음이면 빈 채로 시작한다."""
        state = self.tool_states.pop(target, None) or {}
        self.input_text.delete('1.0', 'end')
        if state.get('input'):
            self.input_text.insert('1.0', state['input'])
        self.names_list = state.get('names') or []
        self.last_org_duplicates = state.get('duplicates') or []
        text, fg = state.get('status') or ('', '#555')
        self._set_parse_status(text, fg)
        if hasattr(self, 'direct_var'):
            self.direct_var.set(state.get('direct', ''))
        self._rebuild_parsed_list()

    def _on_target_change(self):
        """target_var 에 들어 있는 값으로 전환한다."""
        self._choose_target(self.target_var.get())

    def _paint_target_cards(self):
        """고른 쪽을 눈에 띄게. 어느 쪽인지 헷갈리면 안 된다."""
        ui.set_tool(THEME_TOOL.get(self.config.target, 'sotong'))
        switch = getattr(self, 'tool_switch', None)
        if switch is not None:
            switch.select(self.config.target)
        ui.retheme_buttons()
        for item in getattr(self, 'rail_items', {}).values():
            item.retheme()
        try:
            accent_color = ui.acc()[0]
            ttk.Style().configure('Accent.Horizontal.TProgressbar', background=accent_color,
                                  lightcolor=accent_color, darkcolor=accent_color)
        except Exception as exc:
            logging.debug('진행 막대 색 바꾸기 실패: %s', exc)
        ui.retheme_lists([getattr(self, 'parsed_list', None)])
        if getattr(self, '_shell', None) and self._shell['size'][0] > 50:
            self._schedule_backdrop(delay=10)

    def _apply_target(self):
        edufine_on = self.is_edufine()
        self._paint_target_cards()
        self._refresh_direct_hint()

        # 고른 도구에 필요한 탭만 남긴다. 수신픽은 엑셀을 만들어 올리는 방식이라
        # 마우스 위치를 잡을 일이 없다.
        # hide() 로 감추고 insert() 로 끼워 넣는 방식을 썼더니, insert 가 감춘 탭을
        # 되살려서 에듀파인인데 위치 설정·자동 선택이 같이 보였다.
        # forget() 으로 전부 떼고 필요한 것만 순서대로 add() 하면 결과가 분명하다.
        # (forget 은 탭 목록에서 빼는 것일 뿐 위젯은 그대로 살아 있다.)
        order = [(self.tab_input, '  1. 명단 입력  ')]
        order += self.edufine_tabs if edufine_on else self.messenger_tabs
        order += [self.help_tabs[self.config.target]]

        try:
            for tab in list(self.nb.tabs()):
                self.nb.forget(tab)
        except Exception as exc:
            logging.info('탭 정리 실패: %s', exc)
        for tab, label in order:
            try:
                self.nb.add(tab, text=label)
            except Exception as exc:
                logging.info('탭 배치 실패 (%s): %s', label.strip(), exc)

        for name in ('browse_btn', 'bulk_fix_btn', 'org_history_btn'):
            btn = getattr(self, name, None)
            if not btn:
                continue
            if edufine_on:
                btn.pack(side='left', padx=3)
            else:
                btn.pack_forget()

        self._rebuild_rail(order)
        try:
            self.nb.select(self.tab_input)
        except Exception as exc:
            logging.debug('첫 화면 고르기 실패: %s', exc)

        hint = getattr(self, 'target_hint', None)
        if hint:
            hint.config(text=(
                f'v{APP_VERSION}  ·  송동석(Dustin)  ·  Teacher / App developer / Data analyst'
                '  ·  dungst.me@gmail.com'
            ))

        title = getattr(self, 'guide_title', None)
        body = getattr(self, 'guide_body', None)
        if title and body:
            if edufine_on:
                title.config(text='기관 명단을 넣으세요')
                body.config(text=(
                    '엑셀이나 한글에서 기관명을 복사해 붙여넣거나 파일을 바로 여세요.\n'
                    '줄바꿈, 쉼표, 탭 어느 것으로 나눠도 됩니다.\n'
                    '예) 학성초, 충북외고, 청주교육지원청 행정과'
                ))
            else:
                title.config(text='소속기관과 이름을 넣으세요')
                body.config(text=(
                    '소통메신저에서 고를 사람의 명단입니다.\n'
                    '엑셀이나 한글에서 소속기관과 이름 두 열을 복사해 붙여넣거나 파일을 바로 여세요.\n'
                    '예) 충주중학교  홍길동 (소속기관, 이름 순서)'
                ))
        nxt = getattr(self, 'next_btn', None)
        if nxt:
            nxt.config(text='다음, 수신그룹 엑셀' if edufine_on else '다음, 위치 설정')

        # 좌표 안내는 소통메신저 전용이다
        intro = getattr(self, 'calib_intro', None)
        if intro:
            intro.config(text=(
                '소통메신저에서 편지 버튼에 마우스를 올려 [쪽지작성] 을 누르고,\n'
                '[받는사람 추가] 로 [사용자 선택] 창을 열어 두세요.\n'
                '아래 차례에서 4번 검색 입력칸, 5번 검색 결과 첫 줄, 6번 화살표 버튼을 잡습니다.\n'
                '[캡처 시작] 을 누른 뒤 잡을 자리를 클릭하면 그 자리가 저장됩니다. '
                'Enter 로도 확정되고 Esc 는 취소입니다.'
            ))
        auto_intro = getattr(self, 'auto_intro', None)
        if auto_intro:
            auto_intro.config(text=(
                '소통메신저 [사용자 선택] 창을 열고 [전체조직] 탭을 켜 두세요.\n'
                '이름마다 검색하고, 결과 첫 줄을 누르고, 오른쪽 화살표 버튼으로 담습니다.\n'
                '진행 중에는 마우스를 건드리지 마세요. 마우스를 화면 왼쪽 위 모서리로 옮기면 긴급 중지됩니다.'
            ))

        self._refresh_calib_labels()
        self._refresh_ready_status()
        self._refresh_edufine_status()
        self._refresh_org_review_state()

    def _parse(self):
        if self._block_while_running():
            return
        if self.is_edufine():
            return self._parse_orgs()
        raw = self.input_text.get('1.0', 'end')
        parsed = parse_input(raw)
        self.names_list.clear()
        self.parsed_list.delete(0, 'end')

        ok = fail = no_org = 0
        valid = []
        for item in parsed:
            org = item.get('org', '').replace(' ', '')
            name = item.get('name', '').replace(' ', '')
            if not name:
                fail += 1
                continue
            valid.append({'org': org, 'name': name})

        valid.sort(key=lambda x: x['name'])

        warn_items = []
        for entry in valid:
            org, name = entry['org'], entry['name']
            if not org:
                no_org += 1
                warn_items.append(name)
            self.names_list.append({'org': org, 'name': name})
            ok += 1
        self._rebuild_parsed_list()

        color = COLORS['ok'] if ok > 0 else COLORS['error']
        parts = [f'명단 추출 완료: {ok}명']
        if fail:
            parts.append(f'인식실패 {fail}')
        if no_org:
            parts.append(f'소속없음 {no_org}')
            if warn_items:
                parts.append(f'({", ".join(warn_items[:5])}{"..." if len(warn_items) > 5 else ""})')
        self._set_parse_status('  /  제외: '.join(parts) if (fail or no_org) else parts[0], color)
        self.status_var.set(f'명단 추출 완료: {ok}명')
        self._refresh_ready_status()

    def _parse_orgs(self):
        """에듀파인용: 기관명만 뽑는다.

        퍼지 추정(grade='fuzzy')과 실패(grade='none')는 확정하지 않는다.
        엑셀로 나가면 그대로 등록되므로 사람이 후보를 골라야 한다.
        """
        raw = self.input_text.get('1.0', 'end')

        # 명단을 읽고 코드 사전으로 다시 본다.
        # 부서는 org_db 만으로는 못 좁힌다. '행정과' 는 11곳이고
        # '청주교육지원청 행정과' 처럼 상위조직과 맞물려야 한 곳이 된다.
        index = edufine.index_by_short_name(self.codes)
        rows = edufine.parse_and_resolve(
            raw, self.codes, index, deduplicate=False)

        self.names_list.clear()
        self.parsed_list.delete(0, 'end')
        items, duplicates = self._summarize_org_rows(rows, index)
        self.names_list.extend(items)
        self.last_org_duplicates = duplicates

        confirmed = sum(
            1 for item in self.names_list if item.get('grade') in AUTO_GRADES)
        pending = sum(1 for item in self.names_list if self._org_needs_review(item))
        self._rebuild_parsed_list()
        self._record_org_extraction()

        # 확정 수와 확인 필요 수는 위의 칩과 배너가 이미 보여 준다. 여기에는 따로 알릴 것만 적는다.
        self._set_parse_status(f'같은 기관 {len(duplicates)}종은 한 번만 남겼습니다' if duplicates else '',
                               COLORS['on_surface_variant'])
        self.status_var.set(f'기관 {confirmed}곳 확정, 확인 필요 {pending}곳')
        self._refresh_ready_status()
        self._refresh_edufine_status()

    def _add_direct(self):
        """직접 넣기 칸의 글을 명단에 더한다. 명단 추출과 같은 규칙으로 읽는다.

        소통픽은 '학성초 송동석', 수신픽은 '청주교육지원청 행정과' 처럼 적는다.
        쉼표로 여럿을 한 번에 넣을 수 있다. 이미 있는 것은 다시 넣지 않는다.
        수신픽에서 짐작으로 찾은 기관은 지금처럼 빨갛게 남아 사람이 골라야 한다.
        """
        if self._block_while_running():
            return 0
        text = (self.direct_var.get() or '').strip()
        if not text:
            return 0
        text = re.sub(r'\s*[,;]\s*', '\n', text)
        if self.is_edufine():
            index = edufine.index_by_short_name(self.codes)
            rows = edufine.parse_and_resolve(text, self.codes, index, deduplicate=False)
            items, _duplicates = self._summarize_org_rows(rows, index)
            have = {(i.get('org') or i.get('raw')) for i in self.names_list}
            fresh = [i for i in items if (i.get('org') or i.get('raw')) not in have]
            unit = '곳'
        else:
            have = {(i.get('org'), i.get('name')) for i in self.names_list}
            fresh = []
            for item in parse_input(text):
                org = (item.get('org') or '').replace(' ', '')
                name = (item.get('name') or '').replace(' ', '')
                if name and (org, name) not in have:
                    fresh.append({'org': org, 'name': name})
                    have.add((org, name))
            unit = '명'
        if not fresh:
            self.direct_hint.config(
                text=('이미 명단에 있습니다.' if text and self.names_list else
                      '알아보지 못했습니다. 예시처럼 적어 주세요.'), fg=COLORS['error'])
            return 0
        self.names_list.extend(fresh)
        self._rebuild_parsed_list()
        self._after_list_edit()
        self.direct_var.set('')
        shown = ', '.join(i.get('search') or f"{i.get('org', '')} {i.get('name', '')}".strip()
                          for i in fresh[:3])
        more = f' 외 {len(fresh) - 3}{unit}' if len(fresh) > 3 else ''
        self.direct_hint.config(text=f'넣었습니다: {shown}{more}', fg=COLORS['ok'])
        return len(fresh)

    def _refresh_direct_hint(self):
        hint = getattr(self, 'direct_hint', None)
        if hint is None:
            return
        if self.is_edufine():
            text = ('기관명을 적고 Enter. 예) 학성초  ·  청주교육지원청 행정과  ·  쉼표로 여러 곳')
        else:
            text = ('소속과 이름을 적고 Enter. 예) 학성초 송동석  ·  쉼표로 여러 명')
        hint.config(text=text, fg='#555')

    def _clear_input(self):
        if self._block_while_running():
            return
        self.input_text.delete('1.0', 'end')
        self.parsed_list.delete(0, 'end')
        self.names_list.clear()
        self.last_org_duplicates = []
        self._set_parse_status('')
        self._refresh_summary_chips()
        self._refresh_ready_status()
        self._refresh_failed_retry_state()
        self._refresh_org_review_state()

    def _delete_selected(self):
        if self._block_while_running():
            return
        for i in reversed(self.parsed_list.curselection()):
            del self.names_list[i]
        self._rebuild_parsed_list()
        self._after_list_edit()

    def _set_parse_status(self, text, fg=None):
        """추출 결과 위의 한 줄. 적을 말이 없으면 줄 자리까지 없앤다 (목록이 그만큼 넓어진다)."""
        if fg is None:
            self.parse_status.config(text=text)
        else:
            self.parse_status.config(text=text, fg=fg)
        try:
            if text:
                self.parse_status.grid()
            else:
                self.parse_status.grid_remove()
        except Exception as exc:
            logging.debug('추출 결과 줄 보이기 실패: %s', exc)

    def _after_list_edit(self):
        """목록을 손본 뒤 상태를 다시 맞춘다. 이 목록이 그대로 엑셀로 간다."""
        total = len(self.names_list)
        if self.is_edufine():
            self._set_parse_status('')
        else:
            self._set_parse_status(f'명단 추출 완료: {total}명', COLORS['ok'])
        self._refresh_ready_status()
        self._refresh_edufine_status()
        self._refresh_org_review_state()

    def _edit_item(self, event=None):
        if self._block_while_running():
            return
        sel = self.parsed_list.curselection()
        if not sel:
            return
        idx = sel[0]
        item = self.names_list[idx]

        if self.is_edufine():
            return self._edit_org_item(idx, item)

        dlg = tk.Toplevel(self.root)
        dlg.title('항목 수정')
        dlg.geometry(f'{ui.px(440)}x{ui.px(230)}')
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)

        tk.Label(dlg, text='소속기관:', font=ui.font(10)).grid(
            row=0, column=0, padx=14, pady=(18, 6), sticky='e')
        org_var = tk.StringVar(value=item.get('org', ''))
        org_entry = tk.Entry(dlg, textvariable=org_var, font=ui.font(10), width=22)
        org_entry.grid(row=0, column=1, padx=8, pady=(18, 6), sticky='w')

        tk.Label(dlg, text='이름:', font=ui.font(10)).grid(
            row=1, column=0, padx=14, pady=6, sticky='e')
        name_var = tk.StringVar(value=item.get('name', ''))
        tk.Entry(dlg, textvariable=name_var, font=ui.font(10), width=22).grid(
            row=1, column=1, padx=8, pady=6, sticky='w')

        def apply():
            new_org = org_var.get().strip().replace(' ', '')
            new_name = name_var.get().strip().replace(' ', '')
            if not new_name:
                messagebox.showwarning('알림', '이름을 입력하세요.', parent=dlg)
                return
            self.names_list[idx] = {'org': new_org, 'name': new_name}
            self._rebuild_parsed_list()
            dlg.destroy()

        btn_frame = tk.Frame(dlg)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=14)
        M3Button(btn_frame, text='저장', command=apply).pack(side='left', padx=6)
        M3Button(btn_frame, text='취소', command=dlg.destroy, variant='text').pack(side='left', padx=6)

        dlg.bind('<Return>', lambda e: apply())
        dlg.bind('<Escape>', lambda e: dlg.destroy())
        org_entry.focus_set()

    # ── 위치 캡처 ──────────────────────────────
    def _do_capture(self, key: str):
        if pyautogui is None:
            messagebox.showerror('오류', 'pyautogui 미설치')
            return

        def on_captured(x, y):
            self.config.data[key + '_x'] = x
            self.config.data[key + '_y'] = y
            # 어느 크기의 화면에서 잡았는지 남긴다. 해상도나 배율이 바뀌면
            # 좌표가 어긋나는데, 그걸 시작할 때 알려 주기 위해서다.
            size = self._screen_size()
            if size:
                self.config.data['screen_w'], self.config.data['screen_h'] = size
            # 잡자마자 저장한다. [설정 저장] 을 누르지 않고 앱을 닫아
            # 다시 잡아야 하는 일이 없도록.
            self.config.save()
            self._refresh_calib_labels()

        labels = {
            'search_field': '검색 입력창',
            'result_first': '결과 첫 번째 행',
            'add_button':   '사용자 선택 버튼',
        }
        CaptureDialog(self.root, on_captured, label=labels.get(key, key),
                      hint=CAPTURE_HINTS.get(key, ''),
                      step=CAPTURE_STEP_KEYS.get(key, ''))

    def _save_calib(self):
        self.config.data['search_delay'] = round(self.delay_var.get(), 1)
        self.config.data['manual_confirm'] = self.manual_var.get()
        self.config.save()
        self.calib_msg.config(text='설정을 저장했습니다')
        self.root.after(2000, lambda: self.calib_msg.config(text=''))
        self._refresh_ready_status()

    def _edit_org_item(self, idx, item):
        """에듀파인 기관 항목 고치기 — 후보에서 고르거나 직접 적는다."""
        dlg = tk.Toplevel(self.root)
        dlg.title('기관 확인')
        dlg.geometry(f'{ui.px(500)}x{ui.px(440)}')
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.configure(bg=PANEL_BG)

        tk.Label(dlg, text=f"입력한 값:  {item.get('raw', '')}", bg=PANEL_BG,
                 fg=COLORS['on_surface_variant'], font=ui.font(10, 'bold')).pack(pady=(16, 2))
        tk.Label(dlg, text='아래 후보에서 고르거나, 정확한 기관명을 직접 적으세요.',
                 bg=PANEL_BG, fg='#555', font=ui.font(9)).pack(pady=(0, 8))

        box = tk.Listbox(dlg, font=ui.font(10), height=9,
                         activestyle='none', exportselection=False,
                         selectbackground=ui.acc()[2], selectforeground=ui.acc()[3])
        box.pack(fill='both', expand=True, padx=16)

        candidates = list(item.get('candidates') or [])
        if item.get('org') and item['org'] not in candidates:
            candidates.insert(0, item['org'])
        for c in candidates:
            box.insert('end', c)
        if candidates:
            box.selection_set(0)

        typed = tk.StringVar(value=item.get('org') or item.get('raw', ''))
        entry_row = tk.Frame(dlg, bg=PANEL_BG)
        entry_row.pack(fill='x', padx=16, pady=(10, 4))
        tk.Label(entry_row, text='직접 입력', bg=PANEL_BG,
                 font=ui.font(9)).pack(side='left', padx=(0, 6))
        entry = ttk.Entry(entry_row, textvariable=typed)
        entry.pack(side='left', fill='x', expand=True)

        def confirm(value):
            value = (value or '').strip()
            if not value:
                return
            if self._confirm_org_item(item, value):
                dlg.destroy()

        def take_selected():
            sel = box.curselection()
            if sel:
                confirm(box.get(sel[0]))
            else:
                confirm(typed.get())

        box.bind('<Double-Button-1>', lambda e: take_selected())
        entry.bind('<Return>', lambda e: confirm(typed.get()))

        btns = tk.Frame(dlg, bg=PANEL_BG)
        btns.pack(pady=12)
        M3Button(btns, text='확정', command=take_selected).pack(side='left', padx=4)
        M3Button(btns, text='취소', command=dlg.destroy, variant='text').pack(side='left', padx=4)

    def _refresh_calib_labels(self):
        for key in ('search_field', 'result_first', 'add_button'):
            x = self.config.data.get(key + '_x')
            y = self.config.data.get(key + '_y')
            lbl = getattr(self, f'lbl_{key}', None)
            chip = getattr(self, f'chip_{key}', None)
            btn = getattr(self, f'btn_{key}', None)
            done = x is not None and y is not None
            if lbl:
                lbl.config(text=f'({x}, {y})' if done else '아직 잡지 않았습니다')
            if chip:
                chip.set('설정됨' if done else '미설정', 'ok' if done else 'err')
            if btn:
                btn.config(text='다시 잡기' if done else '캡처 시작')
        self._refresh_calib_next()
        self._refresh_ready_status()

    def _refresh_calib_next(self):
        """세 곳을 모두 잡았을 때만 [다음, 자동 선택] 을 켠다."""
        button = getattr(self, 'calib_next_btn', None)
        hint = getattr(self, 'calib_hint', None)
        if button is None:
            return
        ready = self.config.is_calibrated()
        button.config(state='normal' if ready else 'disabled')
        if hint is not None:
            left = sum(1 for key in ('search_field', 'result_first', 'add_button')
                       if self.config.data.get(key + '_x') is None
                       or self.config.data.get(key + '_y') is None)
            hint.config(text='세 곳을 모두 잡았습니다' if ready
                        else f'아직 잡지 않은 자리가 {left}곳 있습니다',
                        fg=COLORS['ok'] if ready else COLORS['on_surface_variant'])

    def _calib_next(self):
        """위치 설정을 저장하고 자동 선택으로 넘어간다. 세 곳이 다 잡혀 있을 때만 된다."""
        if not self.config.is_calibrated():
            self._refresh_calib_next()
            return
        self._save_calib()
        self._go_next_step()

    # ── 자동 선택 시작/중지/계속 ───────────────
    def _start(self, items=None):
        """자동 선택을 시작한다. items 를 주면 명단은 그대로 두고 그 사람들만 담는다."""
        if self._automation_is_running():
            messagebox.showwarning('이미 실행 중입니다', '진행 중인 자동 선택을 먼저 끝내세요.')
            return
        if pyautogui is None or pyperclip is None:
            messagebox.showerror('오류', '필수 패키지 미설치')
            return
        if not self.names_list:
            messagebox.showwarning('알림', '먼저 명단을 추출해 주세요.')
            return
        if not self.config.is_calibrated():
            messagebox.showwarning(
                '알림', '위치 설정 탭에서 검색창·결과·선택 버튼 위치를 모두 설정하세요.'
            )
            return
        if not self._confirm_screen_unchanged():
            return
        if not self._confirm_dialog_not_moved():
            return
        run_items = tuple(self.names_list if items is None else items)
        if not run_items:
            messagebox.showinfo('알림', '담을 사람이 없습니다.')
            return
        self.stop_flag.clear()
        self.continue_event.set()
        for item in run_items:
            item.pop('failure_reason', None)
            item.pop('added', None)
        self._rebuild_parsed_list()
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.continue_btn.config(state='disabled')
        total = len(run_items)
        self.progress.config(maximum=total, value=0)
        self.prog_label.config(text=f'0 / {total}명')
        started_at = time.strftime('%Y-%m-%d %H:%M:%S')
        what = '자동 선택 시작' if items is None else '누락된 사람 추가 시작'
        self._log(f'\n{"─" * 44}\n{started_at}  {what}  ·  총 {total}명\n\n')
        logging.info('%s: 총 %s명', what, total)
        self.worker_thread = threading.Thread(
            target=self._worker, args=(run_items,), daemon=True)
        self.worker_thread.start()

    def _confirm_screen_unchanged(self) -> bool:
        """위치를 잡을 때와 화면 크기가 같은지 보고, 다르면 물어본다.

        해상도나 배율을 바꾸면 저장된 좌표가 엉뚱한 곳을 가리킨다. 그대로
        돌리면 다른 사람을 받는 사람에 넣을 수 있어서 먼저 알린다.
        """
        saved_w = self.config.data.get('screen_w')
        saved_h = self.config.data.get('screen_h')
        current = self._screen_size()
        if not (saved_w and saved_h and current):
            return True
        if (saved_w, saved_h) == current:
            return True
        return messagebox.askyesno(
            '화면 크기가 달라졌습니다',
            f'위치를 잡을 때 화면은 {saved_w}×{saved_h} 였고, 지금은 '
            f'{current[0]}×{current[1]} 입니다.\n\n'
            f'해상도나 확대 배율이 바뀌면 저장해 둔 위치가 어긋나서 엉뚱한 곳을 '
            f'누를 수 있습니다. [위치 설정] 탭에서 세 곳을 다시 잡는 것이 '
            f'안전합니다.\n\n'
            f'그래도 지금 이대로 시작할까요?'
        )

    def _confirm_dialog_not_moved(self) -> bool:
        """[사용자 선택] 창이 위치를 잡을 때 그 자리에 있는지 보고, 아니면 물어본다.

        창을 옮기면 저장한 세 자리가 창 밖을 가리켜 바탕화면이나 다른 창을 누른다.
        창을 제목으로 찾았는데 화살표 자리가 그 밖에 있을 때만 묻는다. 창을 못
        찾으면 판단할 근거가 없으므로 묻지 않는다.
        """
        point = self._arrow_point()
        if point is None:
            return True
        dialogs = self._messenger_dialogs()
        if not dialogs or any(self._window_contains(w, point) for w in dialogs):
            return True
        return messagebox.askyesno(
            '[사용자 선택] 창이 옮겨졌습니다',
            '위치를 잡을 때와 [사용자 선택] 창의 자리가 다릅니다.\n\n'
            '이대로 시작하면 저장해 둔 자리가 창 밖을 가리켜 엉뚱한 곳을 누릅니다. '
            '창을 처음 자리로 옮기거나, [위치 설정] 탭에서 4, 5, 6번을 다시 잡는 것이 '
            '안전합니다.\n\n'
            '그래도 지금 이대로 시작할까요?'
        )

    def _stop(self):
        if not self._automation_is_running():
            return
        self.stop_flag.set()
        win = getattr(self, 'pick_window', None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
            self.pick_window = None
        self.continue_event.set()
        # 워커가 실제로 끝날 때까지 다시 시작할 수 없게 둔다. 여기서 시작 버튼을
        # 켜면 새 실행이 stop_flag를 지워 두 워커가 동시에 마우스를 움직일 수 있다.
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.continue_btn.config(state='disabled')
        self.status_var.set('중지 처리 중입니다...')
        self._log('\n⏹  중지 요청\n')

    def _resume(self):
        self.continue_event.set()
        self.continue_btn.config(state='disabled')

    def _failed_items(self) -> list:
        """받는 사람에 들어가지 못했거나 확인하지 못한 항목."""
        return [item for item in self.names_list if item.get('failure_reason')]

    def _retry_failed(self):
        # 항목을 통째로 가져온다. 예전에는 기관명과 이름만 옮겨서, 따로 만들어 둔
        # 검색어(search)가 사라진 채 엉뚱하게 검색됐다.
        failed = []
        for item in self._failed_items():
            # 이미 선택된 사용자는 받는 사람에 들어 있다. 다시 돌릴 이유가 없다.
            if item.get('failure_reason') == FAIL_DUPLICATE:
                continue
            copied = dict(item)
            copied.pop('failure_reason', None)
            copied.pop('added', None)
            failed.append(copied)
        if not failed:
            messagebox.showinfo('알림', '다시 실행할 실패 항목이 없습니다.')
            return
        self.names_list = failed
        self._rebuild_parsed_list()
        self._set_parse_status(f'실패 항목 재실행 준비: {len(failed)}명', COLORS['ok'])
        self._start()

    def _selected_count(self):
        """소통메신저 [선택된 사용자] 목록에 담긴 사람 수. 못 세면 None.

        소통메신저는 이 수를 화면에 적어 두지 않고, 목록은 스크롤해야 다 보이며
        가나다순도 아니다. 그래서 화면을 읽지 않고 목록 칸에 항목 수를 직접
        묻는다. 표준 목록 칸일 때만 되고, 아니면 None 이다.
        """
        found = self._find_selected_list()
        if not found:
            return None
        hwnd, class_name, _rect = found
        return self._count_items(hwnd, class_name)

    def _arrow_point(self):
        x = self.config.data.get('add_button_x')
        y = self.config.data.get('add_button_y')
        if x is None or y is None:
            return None
        return int(x), int(y)

    def _windows_at(self, x: int, y: int) -> list:
        """그 자리를 덮고 있는 최상위 창들. 신통픽 창이 앞에 있어도 뒤의 것까지 본다."""
        gui = self._win32gui()
        if gui is None:
            return []
        hits = []
        for hwnd in self._snapshot_dialogs():
            try:
                left, top, right, bottom = gui.GetWindowRect(hwnd)
            except Exception:
                continue
            if left <= x <= right and top <= y <= bottom:
                hits.append(hwnd)
        return hits

    def _child_controls(self, parent) -> list:
        """창 안의 칸들. (핸들, 클래스 이름, 화면 위치) 로 돌려준다. 글은 읽지 않는다."""
        gui = self._win32gui()
        if gui is None:
            return []
        found = []

        def collect(child, _):
            try:
                found.append((child, gui.GetClassName(child), gui.GetWindowRect(child)))
            except Exception:
                pass
            return True

        try:
            gui.EnumChildWindows(parent, collect, None)
        except Exception as exc:
            logging.debug('창 안의 칸 확인 실패: %s', exc)
        return found

    def _messenger_dialogs(self) -> list:
        """제목에 '사용자 선택' 이 들어간 창. 소통메신저의 [받는사람 추가] 창이다.

        저장한 화살표 위치로만 창을 찾으면, 창을 옮겼을 때 엉뚱한 창(바탕화면 등)을
        들여다본다. 제목으로 먼저 찾는다.
        """
        gui = self._win32gui()
        if gui is None:
            return []
        # 받는사람 추가를 누를 때마다 창이 새로 생겨 여러 개가 겹쳐 있을 수 있다.
        # 맨 위 창이 앞에 오도록 화면에 쌓인 순서대로 늘어놓는다.
        visible = self._snapshot_dialogs()
        order = [h for h in self._windows_in_z_order() if h in visible]
        order += sorted(h for h in visible if h not in order)
        found = []
        for hwnd in order:
            try:
                if MESSENGER_DIALOG_TITLE in (gui.GetWindowText(hwnd) or ''):
                    found.append(hwnd)
            except Exception:
                continue
        return found

    def _windows_in_z_order(self) -> list:
        """최상위 창을 화면에 쌓인 순서(맨 위부터)로. 못 읽으면 빈 목록."""
        gui = self._win32gui()
        if gui is None:
            return []
        order = []

        def collect(hwnd, _):
            order.append(hwnd)
            return True

        try:
            gui.EnumWindows(collect, None)
        except Exception as exc:
            logging.debug('창 순서 확인 실패: %s', exc)
            return []
        return order

    def _find_selected_list(self):
        """화살표 버튼 오른쪽의 목록 칸. 못 찾으면 None."""
        point = self._arrow_point()
        if point is None:
            return None
        # 화살표 자리를 덮고 있는 창만 본다. 창을 옮긴 뒤에는 저장한 화살표 자리가
        # 창 밖이라, 거기서 '오른쪽 목록' 을 고르면 검색 결과 목록을 셀 수 있다.
        dialogs = [w for w in self._messenger_dialogs() if self._window_contains(w, point)]
        others = [w for w in self._windows_at(*point) if w not in dialogs]
        for window in dialogs + others:
            picked = pick_selected_list(self._child_controls(window), *point)
            if picked:
                return picked
        return None

    def _uia(self):
        """윈도우 화면 읽어 주기(UI 자동화). (객체, 못 쓰는 이유) 로 돌려준다."""
        cached = getattr(self, '_uia_cached', None)
        if cached is not None:
            return cached, ''
        try:
            import comtypes.client
            comtypes.client.GetModule('UIAutomationCore.dll')
            from comtypes.gen import UIAutomationClient as client
            uia = comtypes.client.CreateObject(
                client.CUIAutomation, interface=client.IUIAutomation)
            self._uia_cached = uia
            return uia, ''
        except Exception as exc:
            logging.info('UI 자동화를 쓸 수 없습니다: %s', exc)
            return None, str(exc)

    def _uia_nodes(self, uia, hwnd, limit: int = 3000) -> list:
        """창 안의 요소를 모두 모은다. 이름은 화면에 내보내지 않고 판단에만 쓴다."""
        try:
            root = uia.ElementFromHandle(hwnd)
            walker = uia.RawViewWalker
        except Exception as exc:
            logging.info('UI 자동화로 창을 열지 못했습니다: %s', exc)
            return []
        nodes = []
        stack = [(root, -1)]
        while stack and len(nodes) < limit:
            element, parent = stack.pop()
            try:
                rect = element.CurrentBoundingRectangle
                node = {
                    'id': len(nodes), 'parent': parent,
                    'type': element.CurrentControlType,
                    'name': element.CurrentName or '',
                    'rect': (rect.left, rect.top, rect.right, rect.bottom),
                    'offscreen': bool(element.CurrentIsOffscreen),
                }
            except Exception:
                continue
            nodes.append(node)
            kids = []
            try:
                child = walker.GetFirstChildElement(element)
                while child:
                    kids.append(child)
                    child = walker.GetNextSiblingElement(child)
            except Exception as exc:
                logging.debug('UI 자동화 자식 읽기 실패: %s', exc)
            for kid in reversed(kids):
                stack.append((kid, node['id']))
        return nodes

    def _read_uia_nodes(self, uia, window):
        """크롬 화면은 누가 읽으려 할 때 비로소 내용을 내주므로 몇 번 다시 읽는다."""
        nodes, tries = [], 0
        for tries in range(1, 5):
            nodes = self._uia_nodes(uia, window)
            if len(nodes) >= 30:
                break
            time.sleep(0.8)
        return nodes, tries

    def _read_search_count(self):
        """소통메신저 '검색 결과(N명)' 의 N. 화면 읽어 주기로 읽고, 못 읽으면 None.

        화면 스레드에서만 부른다. 화면 읽어 주기 객체가 이 스레드에서 만들어졌다.
        """
        if self._win32gui() is None:
            return None
        point = self._arrow_point()
        dialogs = [w for w in self._messenger_dialogs()
                   if point is None or self._window_contains(w, point)]
        if not dialogs:
            return None
        uia, _why = self._uia()
        if uia is None:
            return None
        nodes, _tries = self._read_uia_nodes(uia, dialogs[0])
        return search_count_in(nodes, SEARCH_COUNT_RE)

    def _run_on_ui(self, fn, timeout: float = 5.0):
        """워커 스레드에서 fn 을 화면 스레드로 넘겨 부르고 결과를 받는다. 늦으면 None."""
        done = threading.Event()
        box = {}

        def call():
            try:
                box['value'] = fn()
            except Exception as exc:
                logging.debug('화면 스레드 호출 실패: %s', exc)
            finally:
                done.set()

        self.root.after(0, call)
        if not done.wait(timeout):
            return None
        return box.get('value')

    def _ask_pick(self, name: str, count: int):
        """검색 결과가 여럿일 때 맨 위에 작은 창을 띄워 고르게 한다. 화면 스레드에서 부른다."""
        self.pick_choice = None
        self.status_var.set(
            f'동명이인 확인: {name}  ·  검색 결과 {count}명. 소통메신저에서 맞는 분을 골라 '
            f'화살표를 누른 뒤 [계속] 을 누르세요')
        self.continue_btn.config(state='normal')
        win = tk.Toplevel(self.root)
        win.title('동명이인 확인')
        try:
            win.attributes('-topmost', True)
            win.geometry('+20+20')
        except tk.TclError as exc:
            logging.debug('동명이인 창 위치 설정 실패: %s', exc)
        tk.Label(win, text=f'⏸  {name}  ·  검색 결과 {count}명',
                 bg=COLORS['warn_container'], fg=COLORS['on_warn_container'], font=ui.font(11, 'bold'),
                 padx=12, pady=8).pack(fill='x')
        tk.Label(
            win,
            text=('같은 이름이 여럿이라 신통픽이 고르지 않았습니다.\n'
                  '소통메신저 검색 결과에서 맞는 분을 누르고 오른쪽 화살표를 누른 뒤\n'
                  '[계속] 을 누르세요. 아무도 담지 않으려면 [건너뛰기] 를 누르세요.'),
            font=ui.font(9), justify='left', padx=12, pady=8
        ).pack(anchor='w')
        row = tk.Frame(win)
        row.pack(fill='x', padx=12, pady=(0, 10))

        def choose(choice):
            self.pick_choice = choice
            try:
                win.destroy()
            except tk.TclError:
                pass
            self._resume()

        M3Button(row, text='계속 (골라서 담았음)', command=lambda: choose('continue')).pack(side='left')
        M3Button(row, text='건너뛰기', command=lambda: choose('skip'), variant='text').pack(side='left', padx=6)
        self.pick_window = win

    def _read_messenger_selected(self):
        """소통메신저 [선택된 사용자] 목록의 줄 글을 읽는다.

        돌려주는 값은 (줄 글 목록, 못 읽은 이유). 읽으면 이유는 빈 글이다.
        """
        if self._win32gui() is None:
            return None, '이 PC 에서는 창을 들여다보는 기능(pywin32)을 쓸 수 없습니다.'
        point = self._arrow_point()
        if point is None:
            return None, '[위치 설정] 에서 6번 화살표 버튼 위치를 먼저 잡아 주세요.'
        dialogs = self._messenger_dialogs()
        if not dialogs:
            return None, ('소통메신저 [사용자 선택] 창이 열려 있지 않습니다. '
                          '[받는사람 추가] 를 눌러 창을 연 채로 다시 눌러 주세요.')
        inside = [w for w in dialogs if self._window_contains(w, point)]
        if not inside:
            return None, ('[사용자 선택] 창이 위치를 잡을 때와 다른 곳에 있습니다. '
                          '창을 옮기셨다면 [위치 설정] 에서 4, 5, 6번을 다시 잡아 주세요.')
        uia, why = self._uia()
        if uia is None:
            return None, (f'화면 읽어 주기를 쓸 수 없습니다 ({why}). '
                          '개발용 실행.bat 을 다시 누르면 필요한 것을 깝니다.')
        # 여럿이 겹쳐 있으면 맨 위 창부터 읽는다. 자동 선택도 맨 위 창을 누른다.
        # 맨 위 창에서 담긴 사람을 못 읽으면(아직 안 뜬 화면, 빈 목록 따위) 다음 창을 본다.
        rows, seen_label, used = None, False, 0
        for index, window in enumerate(inside):
            nodes, _tries = self._read_uia_nodes(uia, window)
            found = selected_person_rows(nodes, point[0])
            logging.info('[선택된 사용자] 읽기: %d번째 창, 요소 %d개, 사람 줄 %d개',
                         index + 1, len(nodes), len(found))
            if found:
                rows, used = found, index
                break
            if has_selected_label(nodes):
                seen_label = True
                if rows is None:
                    rows, used = [], index           # 목록이 비어 있는 창일 수 있다
        if not rows and not seen_label:
            return None, ('[선택된 사용자] 목록을 찾지 못했습니다. [사용자 선택] 창이 완전히 '
                          '뜬 다음에 다시 눌러 주세요. 계속 안 되면 [위치 설정] 탭에서 '
                          '6번 자리를 다시 확인해 주세요.')
        self.compare_note = ''
        if len(inside) > 1:
            which = '맨 위 창' if used == 0 else f'위에서 {used + 1}번째 창'
            self.compare_note = (f'[사용자 선택] 창이 {len(inside)}개 겹쳐 열려 있어 {which}을 '
                                 '읽었습니다. 쓰지 않는 창은 닫아 두는 편이 안전합니다.')
        return rows, ''

    def _compare_with_messenger(self, quiet: bool = False):
        """소통메신저 [선택된 사용자] 와 소통픽 명단을 맞춰 누가 들어가고 빠졌는지 보여 준다.

        quiet 는 자동 선택이 끝난 뒤 저절로 부를 때다. 그때는 명단을 못 읽어도
        경고창을 띄우지 않고 상태 줄에만 적는다.
        """
        if not self.names_list:
            messagebox.showwarning('알림', '먼저 명단을 추출해 주세요.')
            return None
        if self._automation_is_running():
            messagebox.showwarning('실행 중입니다', '자동 선택이 끝난 뒤에 비교해 주세요.')
            return None
        self.status_var.set('소통메신저 명단을 읽는 중입니다...')
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.compare_note = ''
        rows, why = self._read_messenger_selected()
        if rows is None:
            if quiet:
                self.status_var.set(
                    self.status_var.get()
                    + '  ·  소통메신저 명단은 읽지 못했습니다 ([소통메신저와 비교] 로 다시 시도)')
                return None
            self.status_var.set('소통메신저 명단을 읽지 못했습니다')
            if self._offer_comtypes_install(why, self._compare_with_messenger):
                return None
            messagebox.showwarning('소통메신저 명단을 읽지 못했습니다', why)
            return None
        result = reconcile.compare_with_messenger(self.names_list, rows)
        self._mark_compare_result(result)
        # 파일 로그에는 이름 없이 수만 남긴다
        logging.info('소통메신저 비교: 읽은 줄 %s, 들어감 %s, 빠짐 %s, 확인 필요 %s, 메신저에만 %s',
                     result.rows, len(result.inside), len(result.missing),
                     sum(len(p) for _n, p, _h in result.unsure), len(result.extra))
        self.status_var.set(
            f'소통메신저 비교  ·  들어감 {len(result.inside)}명  ·  빠짐 {len(result.missing)}명')
        MessengerCompareReport(self.root, result, len(self.names_list),
                               on_add=self._add_missing_to_messenger, note=self.compare_note)
        return result

    def _add_missing_to_messenger(self, items):
        """비교에서 빠진 사람만 소통메신저에 담는다. 명단은 그대로 둔다.

        끝나면 _done 이 다시 비교해 정말 다 들어갔는지 보여 준다.
        """
        try:
            self.nb.select(self.messenger_tabs[1][0])     # 진행 상황이 보이는 탭
        except Exception as exc:
            logging.debug('자동 선택 탭으로 옮기지 못했습니다: %s', exc)
        self._start(list(items))

    def _offer_comtypes_install(self, why: str, then) -> bool:
        """화면 읽어 주기 부품(comtypes)이 없으면 지금 깔지 묻는다.

        설치를 시작했으면 True 다. 다 깔리면 then 을 다시 부른다. 해당이 없거나
        사용자가 마다하면 False 이고, 부른 쪽이 원래 안내를 그대로 보여 준다.

        예전에 받은 개발용 실행.bat 은 이 부품을 깔지 않는다. bat 를 다시 받지 않아도
        되게 여기서 깐다. exe 에는 이미 들어 있으므로 소스로 띄웠을 때만 묻는다.
        """
        if 'comtypes' not in (why or '') or getattr(sys, 'frozen', False):
            return False
        answer = messagebox.askyesno(
            '부품을 설치할까요?',
            '소통메신저 명단을 읽는 데 필요한 부품(comtypes)이 없습니다.\n\n'
            '지금 설치할까요? 인터넷이 필요하고 1분 안쪽으로 걸립니다.')
        # [예] 를 눌렀을 때만 깐다. 알 수 없는 값이면 깔지 않는다.
        if answer is not True:
            return False
        self.status_var.set('comtypes 설치 중입니다. 잠시 기다려 주세요...')
        done = {}

        def work():
            import subprocess
            try:
                proc = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install',
                     '--disable-pip-version-check', 'comtypes'],
                    capture_output=True, text=True, timeout=300)
                done['ok'] = proc.returncode == 0
                done['log'] = (proc.stdout or '')[-400:] + (proc.stderr or '')[-400:]
            except Exception as exc:
                done['ok'], done['log'] = False, str(exc)

        def finished():
            if done.get('ok'):
                import importlib
                importlib.invalidate_caches()
                self.status_var.set('comtypes 설치를 마쳤습니다')
                then()
            else:
                logging.warning('comtypes 설치 실패: %s', done.get('log'))
                self.status_var.set('comtypes 설치에 실패했습니다')
                messagebox.showwarning(
                    '설치하지 못했습니다',
                    '부품을 설치하지 못했습니다. 인터넷 연결을 확인하거나, '
                    '개발용 실행.bat 을 새로 받아 실행해 주세요.\n\n'
                    + (done.get('log') or '')[-300:])

        def wait(thread):
            if thread.is_alive():
                self.root.after(300, lambda: wait(thread))
            else:
                finished()

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        wait(thread)
        return True

    def _mark_compare_result(self, result):
        """비교 결과를 명단에 남긴다. 빠진 사람은 빨갛게, 들어간 사람은 빨간 표시를 지운다.

        그래야 [실패 항목만 다시 실행] 이 빠진 사람만 다시 담는다.
        """
        for item in result.inside:
            item['added'] = True
            item.pop('failure_reason', None)
        for item in result.missing:
            item.pop('added', None)
            item['failure_reason'] = reconcile.NOT_IN_MESSENGER
        for _name, people, have in result.unsure:
            note = reconcile.same_name_note(people, have)
            for item in people:
                item.pop('added', None)
                item['failure_reason'] = note
        self._rebuild_parsed_list()

    def _probe_uia(self, window, point):
        """웹 화면 속 [선택된 사용자] 목록을 화면 읽어 주기로 찾는다.

        돌려주는 값은 (추정, 보여 줄 줄들). 추정은 guess_selected_list 의 결과다.
        크롬 화면은 누가 읽으려 할 때 비로소 내용을 내주므로 몇 번 다시 읽는다.
        """
        lines = ['', '[화면 읽어 주기]']
        uia, why = self._uia()
        if uia is None:
            lines.append(f'  쓸 수 없습니다: {why}')
            lines.append('  개발용 실행.bat 을 다시 누르면 필요한 것(comtypes)을 깝니다.')
            return None, lines
        gui = self._win32gui()
        try:
            base_left, base_top, _r, _b = gui.GetWindowRect(window)
        except Exception:
            base_left = base_top = 0
        nodes, tries = self._read_uia_nodes(uia, window)
        guess = guess_selected_list(nodes, point[0])
        offscreen = sum(1 for node in nodes if node['offscreen'])
        lines.append(f'  읽은 요소: {len(nodes)}개 (화면 밖 {offscreen}개), {tries}번 읽음')
        label = find_label(nodes, SELECTED_LABEL)
        if label:
            l, t, _r, _b = label['rect']
            lines.append(f"  '{SELECTED_LABEL}' 제목: 찾음  창 기준 ({l - base_left}, {t - base_top})")
        else:
            lines.append(f"  '{SELECTED_LABEL}' 제목: 못 찾음")
        kinds = {}
        for node in nodes:
            name = uia_type_name(node['type'])
            kinds[name] = kinds.get(name, 0) + 1
        lines.append('  종류별: ' + ', '.join(
            f'{k} {v}' for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])))
        right = [c for c in repeated_containers(nodes) if c[0]['rect'][0] >= point[0]]
        right.sort(key=lambda c: -c[2])
        lines.append('  오른쪽에서 같은 줄이 반복되는 요소 (많은 순):')
        for node, kid_type, count, off in right[:8]:
            l, t, r, b = node['rect']
            persons = person_rows(nodes, node['id'], kid_type)
            picked = '  ← 이것으로 셈' if guess and guess[0] is node else ''
            lines.append(
                f'    {uia_type_name(node["type"])} 안 {uia_type_name(kid_type)} {count}개'
                f' (이름 줄 {persons}, 화면 밖 {off})  창 기준 ({l - base_left}, {t - base_top})'
                f' 크기 {r - l}x{b - t}{picked}')
        if not right:
            lines.append('    없음')
        lines.append(f'  추정: {guess[2]}명' if guess else '  추정: 찾지 못함')
        return guess, lines

    def _window_contains(self, hwnd, point) -> bool:
        gui = self._win32gui()
        try:
            left, top, right, bottom = gui.GetWindowRect(hwnd)
        except Exception:
            return False
        return left <= point[0] <= right and top <= point[1] <= bottom

    def _describe_dialog(self, window, point) -> list:
        """[사용자 선택] 창 안의 칸을 종류와 위치로 적는다. 위치는 창 왼쪽 위 기준이다."""
        gui = self._win32gui()
        try:
            left, top, right, bottom = gui.GetWindowRect(window)
        except Exception:
            return ['  창 위치를 읽지 못했습니다.']
        where = '안' if self._window_contains(window, point) else '밖'
        lines = [f'\n[창] {gui.GetClassName(window)}  ({left}, {top}, {right}, {bottom})'
                 f'  화살표 위치는 이 창 {where}에 있습니다']
        children = self._child_controls(window)
        kinds = {}
        for shown, (hwnd, class_name, rect) in enumerate(children):
            kinds[class_name] = kinds.get(class_name, 0) + 1
            if shown >= 60:
                continue
            l, t, r, b = rect
            line = f'  {class_name}  ({l - left}, {t - top}) 크기 {r - l}x{b - t}'
            if count_message_for(class_name) is not None:
                line += f'  항목 {self._count_items(hwnd, class_name)}'
            lines.append(line)
        if len(children) > 60:
            lines.append(f'  … 외 {len(children) - 60}개')
        summary = ', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))
        lines.append(f'  칸 종류: {summary or "없음 (창 전체를 한 덩어리로 그림)"}')
        return lines

    def _count_items(self, hwnd, class_name):
        """목록 칸에 항목 수를 묻는다. 응답이 없으면 기다리지 않고 None."""
        gui = self._win32gui()
        message = count_message_for(class_name)
        if gui is None or message is None:
            return None
        try:
            # 소통메신저가 멈춰 있으면 신통픽까지 같이 멈추지 않게 0.5초만 기다린다.
            _ok, count = gui.SendMessageTimeout(hwnd, message, 0, 0, 0x0002, 500)
        except Exception as exc:
            logging.debug('목록 항목 수를 묻지 못했습니다: %s', exc)
            return None
        return count if isinstance(count, int) and count >= 0 else None

    def _probe_messenger_lists(self):
        """소통메신저 목록을 셀 수 있는지 확인하고, 본 것을 보여 준다.

        이름 같은 글은 읽지 않는다. 칸의 종류와 위치, 항목 수만 적는다.
        """
        gui = self._win32gui()
        point = self._arrow_point()
        dialogs = self._messenger_dialogs() if gui is not None else []
        # 결과는 O 아니면 X 다. 한눈에 보이도록 창 맨 위에 크게 쓴다.
        mark, headline, advice = 'X', '', ''
        extra_lines = []
        if gui is None:
            headline = '이 PC 에서는 창을 들여다보는 기능(pywin32)을 쓸 수 없습니다.'
        elif point is None:
            headline = '6번 오른쪽 화살표 버튼 위치를 먼저 잡아 주세요.'
        else:
            picked = self._find_selected_list()
            count = self._count_items(picked[0], picked[1]) if picked else None
            inside = [w for w in dialogs if self._window_contains(w, point)]
            if count is not None:
                mark = 'O'
                headline = f'[선택된 사용자] 목록을 셀 수 있습니다. 지금 {count}명이 들어 있습니다.'
                advice = '소통메신저에 담아 둔 사람 수와 같은지 확인해 주세요.'
            elif not dialogs:
                headline = '소통메신저 [사용자 선택] 창을 찾지 못했습니다.'
                advice = '소통메신저에서 [받는사람 추가] 를 눌러 창을 연 채로 다시 눌러 주세요.'
            elif not inside:
                headline = '[사용자 선택] 창이 위치를 잡을 때와 다른 곳에 있습니다.'
                advice = ('창을 옮기셨다면 [위치 설정] 에서 4, 5, 6번을 다시 잡고 다시 눌러 '
                          '주세요. 이대로 자동 선택을 시작하면 엉뚱한 곳을 누릅니다.')
            else:
                # 창 안이 웹 화면이면 윈도우 목록 칸이 없다. 화면 읽어 주기로 다시 본다.
                guess, uia_lines = self._probe_uia(inside[0], point)
                extra_lines = uia_lines
                if guess:
                    mark = 'O'
                    headline = (f'[선택된 사용자] 목록을 읽을 수 있을 것 같습니다. '
                                f'{guess[2]}명으로 셉니다.')
                    advice = ('소통메신저에 담아 둔 사람 수와 같은지 꼭 확인해 주세요. '
                              '같으면 이 방법으로 세도록 만들겠습니다.')
                else:
                    headline = '[선택된 사용자] 목록을 셀 수 없습니다.'
                    advice = ('[내용 복사] 를 누른 뒤 대화창에 붙여 넣어 보내 주세요. '
                              '목록이 어떻게 되어 있는지 보고 다른 방법을 찾겠습니다.')

        lines = [f'결과: {mark}', headline]
        if advice:
            lines.append(advice)
        if gui is not None and point is not None:
            lines.append('')
            lines.append(f'6번 화살표 버튼 위치: ({point[0]}, {point[1]})')
            lines.append(f'[사용자 선택] 창: {len(dialogs)}개')
            for window in dialogs:
                lines.extend(self._describe_dialog(window, point))
            lines.extend(extra_lines)
            if not dialogs:
                # 제목으로 못 찾았으면 화살표 자리에 있는 창이라도 적어 둔다
                for window in self._windows_at(*point):
                    try:
                        name = gui.GetClassName(window)
                    except Exception:
                        continue
                    lines.append(f'  화살표 자리의 창: {name}')
        text = '\n'.join(lines)
        logging.info('소통메신저 목록 확인:\n%s', text)
        if any('comtypes' in line for line in extra_lines):
            if self._offer_comtypes_install('comtypes', self._probe_messenger_lists):
                return text

        win = tk.Toplevel(self.root)
        win.title('소통메신저 목록 읽기 확인')
        win.geometry(f'{ui.px(680)}x{ui.px(520)}')
        color = COLORS['ok'] if mark == 'O' else COLORS['error']
        tk.Label(win, text=mark, fg=color, font=ui.font(48, 'bold')).pack(pady=(10, 0))
        tk.Label(win, text=headline, fg=color, font=ui.font(11, 'bold'),
                 wraplength=ui.px(580), justify='center').pack(padx=10)
        if advice:
            tk.Label(win, text=advice, fg=COLORS['on_surface_variant'], font=ui.font(9),
                     wraplength=ui.px(580), justify='center').pack(padx=10, pady=(2, 0))
        box_card, box = ui.text_field(win, height=10, wrap='word', font=ui.font(9))
        box_card.pack(fill='both', expand=True, padx=10, pady=(10, 4))
        box.insert('1.0', text)
        box.config(state='disabled')
        row = tk.Frame(win)
        row.pack(fill='x', padx=10, pady=(0, 10))
        status = tk.Label(row, text='', fg=COLORS['ok'], font=ui.font(9))
        M3Button(
            row,
            text='내용 복사',
            command=lambda: copy_text(win, text) and status.config(text='복사했습니다'),
            variant='tonal'
        ).pack(side='left')
        status.pack(side='left', padx=8)
        M3Button(row, text='닫기', command=win.destroy, variant='text').pack(side='right')
        return text

    # ── 자동화 워커 ────────────────────────────
    def _worker(self, run_items):
        ok = fail = 0
        manual = self.config.data.get('manual_confirm', False)
        total = len(run_items)
        no_result_streak = 0

        for idx, item in enumerate(run_items):
            if self.stop_flag.is_set():
                break
            org = item.get('org', '')
            name = item.get('name', '')
            # 에듀파인 항목은 기관명 하나로 검색한다 (사람 이름이 없다)
            search_str = item.get('search') or ((org + '+' + name) if org else name)
            prefix = f'[{idx + 1}/{total}]  '

            self._log(f'{prefix}{search_str}  ... ')
            try:
                # 검색 전 결과 영역을 기억해 둔다. 앞사람의 결과가 남아 있는
                # 사이에 눌러 엉뚱한 사람이 들어가는 일을 막는다.
                before = self._result_pixels()
                before_pixels = before[0] if before else None

                self._do_search(search_str)
                time.sleep(self.config.data.get('search_delay', 0.5))

                found = self._wait_for_result(before_pixels)
                if found == 'stopped':
                    self._log('\n')
                    self._mark_failed(idx, FAIL_MANUAL_STOP, item)
                    break
                if found != 'new':
                    fail += 1
                    no_result_streak += 1
                    if found == 'stale':
                        self._log('검색 결과가 바뀌지 않았습니다\n')
                        self._mark_failed(idx, FAIL_SEARCH_STALE, item)
                    else:
                        self._log('사용자 없음\n')
                        self._mark_failed(idx, FAIL_NO_USER, item)
                    if no_result_streak == 3:
                        self._log(
                            '     연달아 결과를 못 찾았습니다. 검색 후 대기 시간을 늘리거나 '
                            '[위치 설정] 탭에서 결과 첫 줄 위치를 확인해 보세요.\n')
                    self._update_progress(idx + 1, total)
                    continue
                no_result_streak = 0

                if manual:
                    self.continue_event.clear()
                    self.root.after(0, lambda n=name: self._show_continue(n))
                    self.continue_event.wait()
                    if self.stop_flag.is_set():
                        self._mark_failed(idx, FAIL_MANUAL_STOP, item)
                        break
                    ok += 1
                    item['added'] = True
                    self._log('✓\n')
                else:
                    # 검색 결과가 여럿이면 첫 사람을 누르지 않고 사람이 고르게 한다
                    many = self._run_on_ui(self._read_search_count)
                    if many is not None and many >= 2:
                        self._log(f'⏸  (검색 결과 {many}명, 직접 고르기 기다림) ')
                        self.continue_event.clear()
                        self.root.after(0, lambda n=search_str, k=many: self._ask_pick(n, k))
                        self.continue_event.wait()
                        if self.stop_flag.is_set():
                            self._log('\n')
                            self._mark_failed(idx, FAIL_MANUAL_STOP, item)
                            break
                        if getattr(self, 'pick_choice', None) == 'skip':
                            fail += 1
                            self._log('건너뜀\n')
                            self._mark_failed(idx, FAIL_SAME_NAME_SKIPPED, item)
                            self._update_progress(idx + 1, total)
                            continue
                        ok += 1
                        item['added'] = True
                        self._log('✓  (직접 고름)\n')
                        self._update_progress(idx + 1, total)
                        continue
                    result = self._do_select()
                    if result == 'stopped':
                        self._log('\n')
                        self._mark_failed(idx, FAIL_MANUAL_STOP, item)
                        break
                    if result == 'duplicate':
                        fail += 1
                        self._log('⚠  이미 선택된 사용자\n')
                        self._mark_failed(idx, FAIL_DUPLICATE, item)
                        self._update_progress(idx + 1, total)
                        continue
                    ok += 1
                    item['added'] = True
                    self._log('✓\n')
            except pyautogui.FailSafeException:
                self._log('\n⚠  긴급 중지 (화면 모서리)\n')
                self._mark_failed(idx, FAIL_MANUAL_STOP, item)
                self.stop_flag.set()
                break
            except Exception as e:
                fail += 1
                self._log(f'✗  ({e})\n')
                self._mark_failed(idx, failure_reason_from_error(e), item)

            self._update_progress(idx + 1, total)
            time.sleep(0.1)

        stopped = self.stop_flag.is_set()
        self.root.after(0, lambda: self._done(ok, fail, stopped, run_items))

    def _do_search(self, search_str: str):
        x = self.config.data['search_field_x']
        y = self.config.data['search_field_y']
        if x is None or y is None:
            raise RuntimeError('좌표 오류: 검색 입력창 위치 미설정')
        delay = self.config.data.get('search_delay', 0.5) * 0.3
        pyautogui.click(x, y)
        time.sleep(delay)
        pyautogui.hotkey('ctrl', 'a')
        pyperclip.copy(search_str)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(delay)
        pyautogui.press('enter')

    def _click_add_once(self, popup_wait: float = POPUP_WAIT_ADD) -> bool:
        """결과 첫 줄과 선택 버튼을 한 번 누른다.

        이미 선택된 사용자라는 안내창이 떴으면 True. 그 사람이 받는 사람에
        들어 있다는 뜻이다.
        """
        rx = self.config.data['result_first_x']
        ry = self.config.data['result_first_y']
        ax = self.config.data['add_button_x']
        ay = self.config.data['add_button_y']
        if None in (rx, ry, ax, ay):
            raise RuntimeError('좌표 오류: 결과 또는 선택 버튼 위치 미설정')
        pyautogui.click(rx, ry)
        time.sleep(0.15)
        before = self._snapshot_dialogs()
        pyautogui.click(ax, ay)
        appeared = self._wait_for_dialog(before, popup_wait)
        if not appeared:
            return False
        duplicate = self._is_duplicate_popup(appeared)
        # 무슨 안내창인지와 상관없이 닫는다. 열린 채로 두면 다음 클릭이 다 막힌다.
        self._close_dialogs(appeared)
        return duplicate

    def _do_select(self) -> str:
        """결과 첫 줄을 누르고 선택 버튼을 눌러 받는 사람에 추가한다.

        추가됐는지 되짚어 확인하지는 않는다. 확인하려면 사람마다 선택 버튼을
        한 번 더 눌러야 해서 시간이 두 배로 든다. 그래서 빼 두었다.
        대신 끝난 뒤 [선택된 사용자] 목록을 세어 들어간 수와 맞춰 본다(_selected_count).

        이미 선택된 사용자였다면 '선택된 사용자 입니다.' 안내창이 뜬다.
        그때는 중복으로 남긴다.
        """
        time.sleep(0.2)
        if self._click_add_once(POPUP_WAIT_ADD):
            return 'duplicate'      # 명단을 돌리기 전부터 받는 사람에 있던 사람
        return 'ok'

    _win32gui_warned = False

    def _win32gui(self):
        """창을 들여다보는 모듈. 못 쓰면 None 을 주고 한 번만 알린다."""
        try:
            import win32gui
            return win32gui
        except Exception as exc:
            if not App._win32gui_warned:
                App._win32gui_warned = True
                logging.warning('win32gui 를 쓸 수 없어 안내창을 볼 수 없습니다: %s', exc)
            return None

    def _snapshot_dialogs(self) -> set:
        """지금 떠 있는 창 핸들.

        예전에는 표준 안내창(#32770) 만 찾았다. 소통메신저가 그 틀을 쓰지 않으면
        안내창을 하나도 보지 못하고, 추가됐는지 확인하는 장치가 통째로 먹통이
        된다. 그래서 보이는 창을 다 담아 두고, 무엇인지는 문구로 가린다.
        """
        gui = self._win32gui()
        if gui is None:
            return set()
        found = set()

        def cb(hwnd, _):
            try:
                if gui.IsWindowVisible(hwnd) and gui.IsWindowEnabled(hwnd):
                    found.add(hwnd)
            except Exception:
                pass
            return True

        try:
            gui.EnumWindows(cb, None)
        except Exception as exc:
            logging.warning('창 목록 확인 실패: %s', exc)
        return found

    def _window_texts(self, hwnd) -> list:
        """창과 그 안에 적힌 글을 모은다."""
        gui = self._win32gui()
        if gui is None:
            return []
        texts = []
        try:
            texts.append(gui.GetWindowText(hwnd))

            def collect(child, _):
                try:
                    text = gui.GetWindowText(child)
                    if text:
                        texts.append(text)
                except Exception:
                    pass
                return True

            gui.EnumChildWindows(hwnd, collect, None)
        except Exception as exc:
            logging.debug('창 글 읽기 실패: %s', exc)
        return texts

    def _wait_for_dialog(self, before: set, timeout: float) -> set:
        """새로 뜬 창을 기다린다. 끝까지 없으면 빈 집합.

        한 번만 보고 넘어가면 늦게 뜨는 안내창을 놓친다. 그러면 추가가 됐는데도
        안 됐다고 표시된다.
        """
        deadline = time.monotonic() + timeout
        while True:
            appeared = self._snapshot_dialogs() - before
            if appeared:
                return appeared
            if time.monotonic() >= deadline:
                return set()
            time.sleep(0.1)

    def _is_duplicate_popup(self, hwnds: set) -> bool:
        """새로 뜬 창이 이미 선택된 사용자라는 안내인가."""
        for hwnd in hwnds:
            texts = self._window_texts(hwnd)
            if looks_like_duplicate_popup(texts):
                return True
            if texts:
                logging.info('안내창을 알아보지 못했습니다: %s', ' | '.join(
                    t for t in texts if t)[:200])
        return False

    def _close_dialogs(self, hwnds: set) -> bool:
        """안내창을 닫는다. 남아 있으면 한 번 더 누른다.

        안내창이 열린 채로 남으면 그다음 클릭이 전부 먹지 않는다.
        """
        for _ in range(2):
            pyautogui.press('enter')
            time.sleep(0.15)
            if not (self._snapshot_dialogs() & hwnds):
                return True
        logging.warning('안내창이 닫히지 않았습니다')
        return False

    def _screen_size(self):
        """주 모니터 크기. 못 구하면 None."""
        try:
            width, height = pyautogui.size()
        except Exception as exc:
            logging.debug('화면 크기 확인 실패: %s', exc)
            return None
        if not width or not height:
            return None
        return int(width), int(height)

    def _result_region(self) -> tuple:
        """결과 첫 줄을 가로로 넓게 덮는 화면 영역 (left, top, 너비, 높이).

        화면을 읽는 기능은 주 모니터만 볼 수 있다. 보조 모니터에 잡아 둔
        좌표를 주 모니터 안으로 끌어와 보면, 엉뚱한 자리를 결과라고 판단한다.
        그럴 때는 조용히 넘어가지 않고 사유를 남긴다.
        """
        x = self.config.data.get('result_first_x')
        y = self.config.data.get('result_first_y')
        if x is None or y is None:
            raise RuntimeError('좌표 오류: 결과 위치 미설정')
        x, y = int(x), int(y)
        left = x - RESULT_SCAN_WIDTH // 2
        top = y - RESULT_SCAN_HEIGHT // 2
        size = self._screen_size()
        if size:
            screen_w, screen_h = size
            if not (0 <= x < screen_w and 0 <= y < screen_h):
                raise RuntimeError(
                    f'좌표 오류: 결과 위치({x}, {y})가 주 모니터'
                    f'({screen_w}×{screen_h}) 밖입니다. 소통메신저를 주 모니터로 '
                    f'옮기고 위치를 다시 잡아 주세요'
                )
            left = min(max(0, left), max(0, screen_w - RESULT_SCAN_WIDTH))
            top = min(max(0, top), max(0, screen_h - RESULT_SCAN_HEIGHT))
        else:
            left, top = max(0, left), max(0, top)
        return left, top, RESULT_SCAN_WIDTH, RESULT_SCAN_HEIGHT

    def _result_pixels(self):
        """결과 첫 줄 영역의 픽셀과 크기. 화면을 못 읽으면 None."""
        left, top, width, height = self._result_region()
        try:
            shot = pyautogui.screenshot(region=(left, top, width, height))
            width, height = shot.size
            pixels = tuple(shot.convert('RGB').getdata())
        except Exception as exc:
            logging.debug('결과 영역을 못 읽었습니다: %s', exc)
            return None
        if len(pixels) < width * height:
            return None
        return pixels, width, height

    def _has_result(self) -> bool:
        """결과 첫 줄 둘레를 훑어 글자가 그려졌는지 본다.

        한 점만 보던 때에는 이름 길이에 따라 그 점이 글자 사이 빈 칸에 떨어져,
        검색은 됐는데도 결과가 없다고 판정하고 마우스를 아예 움직이지 않았다.
        """
        current = self._result_pixels()
        if current is None:
            return self._has_result_at_point()
        return looks_like_result(*current)

    def _has_result_at_point(self) -> bool:
        """영역을 못 읽을 때 쓰는 예전 방식: 결과 좌표 한 점의 밝기만 본다."""
        x = self.config.data.get('result_first_x')
        y = self.config.data.get('result_first_y')
        if x is None or y is None:
            raise RuntimeError('좌표 오류: 결과 위치 미설정')
        try:
            r, g, b = pyautogui.pixel(x, y)[:3]
            # 결과 없으면 배경이 흰색(240+) → 결과 있으면 텍스트로 인해 더 어두움
            return not (r > 240 and g > 240 and b > 240)
        except Exception as exc:
            raise RuntimeError(f'좌표 오류: 결과 위치 확인 실패 ({exc})') from exc

    def _search_result_count(self):
        """소통메신저가 적어 둔 '검색 결과(N명)' 을 읽는다. 못 읽으면 None.

        화면 픽셀보다 확실하다. 0명이면 그 이름으로 찾은 사람이 없다는 뜻이고,
        숫자가 있으면 검색이 실제로 돌았다는 뜻이다. 라벨을 찾으면 핸들을
        기억해 두고 다음부터는 그 창의 글만 읽는다.
        """
        gui = self._win32gui()
        if gui is None:
            return None
        hwnd = getattr(self, '_count_hwnd', None)
        if hwnd:
            try:
                found = SEARCH_COUNT_RE.search(gui.GetWindowText(hwnd) or '')
                if found:
                    return int(found.group(1))
            except Exception as exc:
                logging.debug('검색 결과 수를 읽지 못했습니다: %s', exc)
            self._count_hwnd = None
        for window in self._snapshot_dialogs():
            for text in self._window_texts(window):
                found = SEARCH_COUNT_RE.search(text or '')
                if found:
                    self._count_hwnd = self._find_text_hwnd(window, SEARCH_COUNT_RE)
                    return int(found.group(1))
        return None

    def _find_text_hwnd(self, parent, pattern):
        """그 글이 적힌 자식 창의 핸들. 못 찾으면 None."""
        gui = self._win32gui()
        if gui is None:
            return None
        hit = []

        def collect(child, _):
            try:
                if pattern.search(gui.GetWindowText(child) or ''):
                    hit.append(child)
            except Exception:
                pass
            return True

        try:
            gui.EnumChildWindows(parent, collect, None)
        except Exception as exc:
            logging.debug('자식 창 확인 실패: %s', exc)
        return hit[0] if hit else None

    def _wait_for_result(self, previous=None) -> str:
        """검색 결과가 새로 그려질 때까지 기다린다.

        글자가 있는지만 보면, 앞사람의 결과가 아직 남아 있는 사이에 통과해서
        그 사람을 누르게 된다. 누락도 이렇게 생기고, 더 나쁘게는 엉뚱한 사람이
        받는 사람에 들어갈 수 있다. 그래서 검색 전과 달라졌는지까지 본다.

        돌려주는 값
            new     새 결과가 그려졌다
            empty   결과가 없다 (그 이름으로 검색된 사람이 없다)
            stale   결과가 있지만 검색 전과 그대로다 (검색이 먹지 않았다)
            stopped 사용자가 중지했다
        """
        delay = self.config.data.get('search_delay', 0.5) or 0.5
        deadline = time.monotonic() + max(RESULT_WAIT_MIN, delay * 3)
        state = 'empty'
        while True:
            if self.stop_flag.is_set():
                return 'stopped'
            # 소통메신저가 건수를 적어 두면 그걸 먼저 믿는다. 0명이면 더 기다릴
            # 것도 없이 그 이름으로 찾은 사람이 없다는 뜻이다.
            counted = self._search_result_count()
            if counted == 0:
                return 'empty'
            current = self._result_pixels()
            if current is None:
                # 화면 영역을 못 읽는 환경에서는 예전처럼 한 점만 본다.
                if self._has_result_at_point():
                    return 'new'
            else:
                pixels = current[0]
                if looks_like_result(*current):
                    if previous is None or pixels != previous:
                        return 'new'
                    state = 'stale'
                else:
                    state = 'empty'
            if time.monotonic() >= deadline:
                return state
            time.sleep(0.15)

    def _show_continue(self, name: str):
        name = name or ''
        self.status_var.set(
            f'수동 선택 대기: {name}. 소통메신저에서 결과를 누르고 선택 버튼을 누른 뒤 [계속] 을 누르세요'
        )
        self.continue_btn.config(state='normal')

    def _done(self, ok: int, fail: int, stopped: bool = False, run_items=None):
        self.worker_thread = None
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.continue_btn.config(state='disabled')
        run_items = list(self.names_list if run_items is None else run_items)

        # 결과가 남지 않은 항목은 조용히 넘기지 않는다. 중지하면 그 뒤 사람들은
        # 시도조차 안 했는데, 예전에는 빨간 표시도 없이 담긴 것처럼 남았다.
        unmarked = reconcile.NOT_TRIED if stopped else reconcile.NOT_CHECKED
        run_ids = {id(item) for item in run_items}
        for idx, item in enumerate(self.names_list):
            if (id(item) in run_ids
                    and not item.get('added') and not item.get('failure_reason')):
                self._paint_failed(idx, unmarked)

        tally = reconcile.messenger_tally(run_items, stopped)
        self._refresh_failed_retry_state()

        sep = '─' * 44
        result_word = '중지' if stopped else '완료'
        self._log(f'\n{sep}\n{result_word}  ✓ {ok}명   ✗ {fail}명\n')
        self._log(f'{reconcile.summary_line(tally, "명")}\n')
        logging.info('자동 선택 결과: 추출 %s, 들어감 %s, 빠짐 %s',
                     tally.total, tally.reflected, tally.short)

        head = f'{result_word}  ·  {reconcile.summary_line(tally, "명")}'
        self.status_var.set(head + ('  ← 빨간색 항목 확인' if tally.short else ''))
        if stopped:
            return
        # 신통픽이 누른 것과 실제로 들어간 것은 다를 수 있다. 끝나면 바로
        # 소통메신저 [선택된 사용자] 를 읽어 소통픽 명단과 맞춰 보여 준다.
        self._compare_with_messenger(quiet=True)

    def _update_progress(self, idx: int, total: int):
        self.root.after(
            0,
            lambda: (
                self.progress.config(value=idx),
                self.prog_label.config(text=f'{idx} / {total}명'),
                self._refresh_auto_chips(),
            )
        )

    def _mark_failed(self, idx: int, reason: str, item=None):
        """빨갛게 표시한다. item 을 주면 명단에서 그 항목의 자리를 찾아 칠한다.

        누락된 사람만 다시 담을 때는 돌리는 순번과 명단 순번이 다르다.
        """
        # 파일 로그에는 개인정보를 남기지 않고 순번과 사유만 기록한다.
        logging.warning('명단 추가 실패: 순번=%s, 사유=%s', idx + 1, reason)
        def apply():
            at = idx
            if item is not None:
                at = next((k for k, it in enumerate(self.names_list) if it is item), None)
                if at is None:
                    item['failure_reason'] = reason
                    return
            self._paint_failed(at, reason)
            self._refresh_failed_retry_state()
        self.root.after(0, apply)

    def _paint_failed(self, idx: int, reason: str):
        """목록의 그 항목에 사유를 남기고 빨갛게 칠한다. 화면 스레드에서만 부른다."""
        if idx >= len(self.names_list):
            return
        self.names_list[idx]['failure_reason'] = reason
        self.parsed_list.delete(idx)
        self.parsed_list.insert(idx, self._format_item_label(self.names_list[idx]))
        self.parsed_list.itemconfig(idx, {'bg': COLORS['error_container'],
                                          'fg': COLORS['on_error_container']})

    def _log(self, msg: str):
        self.root.after(0, lambda: self._log_append(msg))

    def _log_append(self, msg: str):
        self.log.config(state='normal')
        if '✓' in msg:
            self.log.insert('end', msg, 'ok')
        elif '✗' in msg or '⚠' in msg:
            self.log.insert('end', msg, 'fail')
        else:
            self.log.insert('end', msg)
        self.log.see('end')
        self.log.config(state='disabled')

    def _log_clear(self):
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        self.log.config(state='disabled')


# ─────────────────────────────────────────────
#  진입점
# ─────────────────────────────────────────────
if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()

