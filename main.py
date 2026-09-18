"""신통픽 — 소통메신저·에듀파인 수신자 한 번에

수신 + 소통. 명단을 읽어 충북 기관명으로 정리하는 파이프라인은 하나이고,
두 도구를 합친 것이다.

  소통픽 — 소통메신저 [사용자 선택] 창에서 수신자를 자동으로 골라 담는다
  수신픽 — 에듀파인 공문 수신그룹 일괄등록 엑셀을 만든다
"""

APP_NAME    = '신통픽'
APP_VERSION = '2.2.4'

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import time
import json
import logging
import os
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
    FAIL_MANUAL_STOP,
    FAIL_NO_USER,
    FAIL_NOT_ADDED,
    FAIL_SEARCH_STALE,
    RESULT_SCAN_HEIGHT,
    RESULT_SCAN_WIDTH,
    RESULT_WAIT_MIN,
    VERIFY_ADD_TRIES,
    failure_reason_from_error,
    looks_like_duplicate_popup,
    looks_like_result,
)
from hwp_extract import extract_hwp_text
from sotong_parser import (
    AUTO_GRADES,
    GRADE_AMBIGUOUS,
    parse_input,
    parse_orgs,
)
from ui_helpers import format_item_label

LOG_FILE = os.path.join(APP_DATA_DIR, 'app.log')
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

class CaptureDialog(tk.Toplevel):
    def __init__(self, parent, on_captured, label='위치'):
        super().__init__(parent)
        self.on_captured = on_captured
        self._finished = False
        self._enter_released = False
        self.title('위치 캡처')
        self.geometry('420x270')
        self.resizable(False, False)

        tk.Label(
            self, text=f'📍  캡처 대상: {label}',
            bg='#1565C0', fg='white', font=('맑은 고딕', 12, 'bold'), pady=12
        ).pack(fill='x')

        tk.Label(
            self,
            text='[캡처 시작] 버튼을 클릭한 뒤 소통메신저의 대상 위치로\n'
                 '마우스를 이동하세요. 소통메신저를 눌러 앞으로 꺼내도 됩니다.\n'
                 'Enter로 확정, Esc로 취소합니다.',
            font=('맑은 고딕', 10), justify='center', pady=12
        ).pack()

        self.status = tk.Label(
            self, text='아래 버튼을 클릭하여 캡처를 시작하세요.',
            font=('맑은 고딕', 11, 'bold'), fg='#FF9800'
        )
        self.status.pack(pady=6)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        self.start_btn = tk.Button(
            btn_frame, text='캡처 시작', command=self._begin,
            bg='#FF9800', fg='white', font=('맑은 고딕', 11, 'bold'),
            relief='flat', padx=16, pady=6, cursor='hand2'
        )
        self.start_btn.pack(side='left', padx=6)
        tk.Button(
            btn_frame, text='취소', command=self.destroy,
            bg='#9E9E9E', fg='white', font=('맑은 고딕', 10),
            relief='flat', padx=12, pady=6
        ).pack(side='left', padx=6)

    def _begin(self):
        self.start_btn.config(state='disabled')
        self.status.config(text='마우스 위치 확인 중...  Enter 확정 / Esc 취소')
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
        # 확정으로 치지 않는다.
        self._enter_released = not key_is_down(VK_RETURN)
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
        self.status.config(text=f'현재 위치: ({pos.x}, {pos.y})  Enter 확정 / Esc 취소')

        # 소통메신저가 앞에 나와 있어도 Enter 가 먹어야 한다.
        if key_is_down(VK_ESCAPE):
            self.destroy()
            return
        if key_is_down(VK_RETURN):
            if self._enter_released:
                self._confirm()
                return
        else:
            self._enter_released = True

        self.after(120, self._poll_position)

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
            self.status.config(text=f'✓ 캡처 완료: ({pos.x}, {pos.y})', fg='green')
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
  {APP_NAME}  v{APP_VERSION}  —  소통메신저·에듀파인 수신자 한 번에
  처음 사용자도 따라할 수 있도록 작성되었습니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

■ 이 프로그램이 하는 일
──────────────────────────────────────────────────────
  명단을 붙여넣으면 충북 기관명으로 정리해 주고,
  그 결과를 두 곳 중 한 곳으로 내보냅니다.

    소통메신저 — [사용자 선택] 창에서 자동으로 골라 담기
    에듀파인   — 개인수신그룹 일괄등록 엑셀 만들기

  [1. 명단 입력] 탭 맨 위에서 어느 쪽을 쓸지 고릅니다.
  고른 쪽에 필요한 탭만 남습니다.

  ─ 소통메신저를 고르면 ─
  소통메신저에서 아래 3단계를 자동으로 반복합니다.

    1단계: 검색 입력창에 이름을 넣고 검색합니다
    2단계: 검색 결과 첫 번째 항목을 누릅니다
    3단계: [사용자 선택] 버튼을 눌러 받는 사람에 추가합니다
    4단계: 정말 추가됐는지 선택 버튼을 한 번 더 눌러 확인합니다

  4단계는 이미 선택된 사용자를 다시 선택할 때 뜨는
  '선택된 사용자 입니다.' 안내창을 추가됐다는 증거로 씁니다.
  안내창이 끝까지 없으면 추가되지 않은 것이라 빨간 항목으로
  남깁니다. [위치 설정] 탭에서 끌 수 있지만, 끄면 빠진 사람을
  알 수 없습니다.

  수십에서 수백 명을 일일이 추가하는 반복 작업을 대신합니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 시작 전 준비 사항
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. 소통메신저에 로그인합니다.
  2. 오른쪽 위의 편지 버튼(✉) 클릭 →
     '쪽지 작성' 또는 '대화하기'를 선택합니다.
  3. 메시지 작성 화면에서 [사용자 선택] 버튼을 클릭합니다.
  4. 사용자 선택 창 상단 탭에서 [전체조직]을 선택합니다.
  5. 소통메신저 창과 {APP_NAME} 창을 나란히 배치하면 편리합니다.

  ※ 실행 중에는 마우스를 움직이지 마세요.
     긴급 중지: 마우스를 화면 왼쪽 위 모서리(0,0)로 빠르게 이동


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 탭 1 — 명단 입력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  명단 입력 방법은 두 가지입니다.

  [ 방법 A ]  파일 직접 열기
    ① [엑셀 파일 열기] 또는 [HWP 파일 열기] 버튼을 클릭합니다.
    ② 파일을 선택하면 자동으로 입력창에 불러옵니다.
    ③ [명단 추출 →] 버튼을 클릭합니다.

  [ 방법 B ]  복사·붙여넣기
    ① 엑셀·한글에서 소속기관(A열)과 이름(B열)을 선택합니다.
    ② Ctrl+C 로 복사합니다.
    ③ 입력창을 클릭하고 Ctrl+V 로 붙여넣습니다.
    ④ [명단 추출 →] 버튼을 클릭합니다.

  ▶ 추출 결과 목록 활용
    · 항목 더블클릭:  소속기관·이름 직접 수정
    · Delete 키 또는 [선택 항목 삭제 (Del)]:  선택 항목 제거
    · 빨간색 항목:  자동 추가에 실패한 항목


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 탭 2 — 위치 설정  ※ 최초 1회만 설정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  소통메신저의 클릭 위치 3곳을 {APP_NAME}에 알려주는 과정입니다.
  한 번만 설정하면 이후에는 자동으로 기억합니다.

  공통 캡처 방법:
    [📍 위치 설정] 을 누르고 [캡처 시작] 을 누른 뒤,
    소통메신저의 해당 위치로 마우스를 옮기고 Enter 를 누르면 확정됩니다.
    소통메신저를 눌러 앞으로 꺼내도 Enter 는 그대로 먹습니다.
    잘못 눌렀다면 Esc 로 취소할 수 있습니다.

  [ STEP 1 ]  검색 입력창 위치
    소통메신저 '이름 검색' 입력칸 위로 마우스를 이동한 뒤 Enter.

  [ STEP 2 ]  결과 첫 번째 항목 위치
    임의 이름(예: 홍길동)을 검색한 뒤
    결과 목록의 첫 번째 줄 위로 마우스를 이동한 뒤 Enter.

  [ STEP 3 ]  사용자 선택 버튼 위치
    결과가 보이는 상태에서
    [사용자 선택] 또는 [추가] 버튼 위로 마우스를 이동한 뒤 Enter.

  [ 검색 설정 ]
    · 검색 후 대기 시간: 기본 0.5초.
      인터넷이 느리면 1.0~2.0초로 높이세요.
    · 수동 확인 모드: 동명이인이 있을 때 체크합니다.
      (검색 결과를 직접 확인 후 [▶▶ 계속] 클릭)

  ★ 반드시 [✅ 설정 저장] 버튼을 눌러 저장하세요!


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 탭 3 — 자동 선택 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ① 소통메신저 [사용자 선택] 창 → [전체조직] 탭을 열어둡니다.
  ② {APP_NAME}에서 [3. 자동 선택] 탭을 클릭합니다.
  ③ [▶ 자동 선택 시작] 버튼을 클릭합니다.
  ④ 명단의 각 이름마다 아래 3단계가 자동으로 실행됩니다.
       1단계: 이름 검색
       2단계: 결과 첫 번째 항목 클릭
       3단계: [사용자 선택] 버튼 클릭
     진행 상황은 로그창에서 확인할 수 있습니다.
       ✓  → 추가 완료
       ✗  → 검색 결과 없음
  ⑤ 완료 시 성공·실패 건수가 표시됩니다.

  ⚠ 긴급 중지
    · 마우스를 화면 왼쪽 위 모서리(0, 0)로 빠르게 이동
    · 또는 [■ 중지] 버튼 클릭


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 자주 묻는 질문
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Q. 소속기관이 '소속없음'으로 표시돼요.
  A. 소속기관명을 인식하지 못한 경우입니다.
     목록에서 해당 항목을 더블클릭하여 직접 수정하세요.

  Q. 프로그램이 엉뚱한 위치를 클릭해요.
  A. 소통메신저 창 위치가 바뀌었을 수 있습니다.
     [2. 위치 설정] 탭에서 3곳을 다시 설정하고 저장하세요.

  Q. 검색은 됐는데 추가가 안 돼요.
  A. [사용자 선택] 버튼 위치(STEP 3)가 잘못 설정되었을 수 있습니다.
     위치를 다시 캡처하고 저장하세요.

  Q. 검색 결과가 아예 없어요.
  A. 소통메신저에 등록되지 않은 사용자입니다.
     해당 항목은 자동으로 ✗ 처리됩니다.

  Q. 너무 빠르게 진행돼서 오류가 생겨요.
  A. [2. 위치 설정] 탭의 '검색 후 대기 시간'을 늘리세요.
     느린 환경: 1.0~2.0초 권장

  Q. 동명이인이 있어서 걱정돼요.
  A. '수동 확인 모드'를 체크하세요.
     검색 후 결과를 직접 확인하고 [▶▶ 계속]을 눌러 진행합니다.

  Q. HWP 파일이 안 열려요.
  A. 한/글이 설치되어 있지 않으면 일부 파일이 열리지 않습니다.
     한글에서 표를 Ctrl+C로 복사 후 입력창에 Ctrl+V로 붙여넣으세요.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 에듀파인 — 수신그룹 일괄등록
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  공문 수신 기관이 30곳이면 조직도에서 검색 → 체크 → [>>] 를
  30번 반복해야 합니다. 클릭 120번입니다.

  에듀파인에는 [개인설정 > 개인수신그룹관리 > 일괄등록] 이 있습니다.
  엑셀 한 장을 올리면 수신그룹이 통째로 만들어지고,
  다음부터는 기안할 때 [수신자 지정 > 개인수신그룹] 에서
  그룹 하나만 고르면 끝납니다. 클릭 120번이 2번이 됩니다.

  {APP_NAME}은 그 엑셀을 만들어 줍니다.


  ① 내 정보 넣기  (처음 한 번만)
  ──────────────────────────────────────────────────────
    [2. 수신그룹 엑셀] 탭 → STEP 1

      사용자ID   : 에듀파인 로그인 ID
      사용자명   : 결재선에 뜨는 이름

    등록교육청은 충청북도교육청으로 자동 적용됩니다.
    한 번 넣으면 저장되니 다음부터는 건너뜁니다.


  ② 기관 명단 넣기
  ──────────────────────────────────────────────────────
    [1. 명단 입력] 탭에서 '수신픽' 을 고르고
    기관 명단을 붙여넣습니다.
    줄바꿈·쉼표·탭 아무거나 되고, 글머리기호와 번호는 알아서 뗍니다.

      학성초
      한천초, 백곡초
      1. 충북외고

    [명단 추출 →] 를 누르면 네 갈래로 나뉩니다.

      확정              그대로 씁니다
      같은 이름이 여럿  '행정과' 처럼 실재하는 곳이 여러 곳
      추정              짐작만 된 것
      찾지 못함         사전에 없는 것

    확정이 아닌 것은 더블클릭해서 후보 중에 고릅니다.
    추정 상태로는 엑셀에 실리지 않습니다.
    엑셀은 그대로 등록되므로, 틀린 기관이 조용히 들어가지 않게 막습니다.

    확인이 필요한 기관은 붉은색으로 표시됩니다.
    [확인 필요 기관 일괄 수정]을 누르면 한 창에서 차례로 고칠 수 있습니다.
    같은 기관을 여러 번 넣으면 기관명과 입력 횟수를 알려 주고 한 번만 남깁니다.
    [추출 기록 보기]에서는 최근 30회의 추출 결과를 다시 확인할 수 있습니다.


  ③ 부서에 보내려면
  ──────────────────────────────────────────────────────
    교육청·교육지원청·직속기관의 부서도 수신자가 됩니다.
    다만 학교와 달리 이름 하나로는 안 될 때가 있습니다.

      정책기획과              한 곳뿐이라 바로 확정
      행정과                  11곳에 있어 확정하지 않음 → 후보에서 고름
      청주교육지원청 행정과    상위조직과 맞물려 한 곳으로 좁혀짐
      단재교육연수원 교육연수부  3단계도 됩니다

    전체경로를 외울 필요는 없습니다.
    [기관 찾아보기…] 버튼을 누르면 770곳을 검색해서 고를 수 있습니다.
    찾을 말을 띄어쓰기로 나눠 적으면 모두 포함된 것만 걸러집니다.

      예)  청주 초등학교   ·   행정과   ·   단재 연수부

    ※ 부서는 엑셀 경로를 쓰는 편이 안전합니다.
      좌표 자동선택은 조직명 칸에 '행정과' 를 쳐서 첫 결과를 고르는
      방식이라, 여러 곳에 겹치는 부서명에서는 엉뚱한 곳이 잡힐 수 있습니다.


  ④ 엑셀 만들어 올리기
  ──────────────────────────────────────────────────────
    [2. 수신그룹 엑셀] 탭 STEP 2 에 수신그룹명을 적고
    [수신그룹 엑셀 만들기] 를 누릅니다.

    그룹명은 에듀파인에서 나중에 찾기 쉬운 이름으로 적습니다.
    예) 2026 진천 초등학교, 2학기 업무담당자
    그룹기호는 선택 사항이므로 필요 없으면 비워 둡니다.

    코드가 없는 기관이 있으면 목록으로 알려 줍니다. 조용히 빠지지 않습니다.
    그런 기관은 [코드 없는 기관 순차 복사] 로 조직도에 직접 넣으면 됩니다.

    만들어진 엑셀을 에듀파인
    [개인설정 > 개인수신그룹관리 > 일괄등록] 에서 올립니다.

    ※ 처음에는 기관 2~3곳짜리 시험 그룹으로 한 번 확인해 보세요.

  ⑤ 코드 없는 기관 순차 복사
  ──────────────────────────────────────────────────────
    기관명을 한 건씩 클립보드에 넣어 줍니다.
    조직명 칸에 Ctrl+V → Enter → 체크 → [>>] 만 반복하면 됩니다.
    Enter 키로 다음으로 넘어갑니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 개발자 정보
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Developed by  송동석
  Teacher  |  Data Analytics  |  App Developer
  협업 및 피드백:  dungst.me@gmail.com

  {APP_NAME}  |  버전 v{APP_VERSION}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


_HELP_EDUFINE_MARKER = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ 에듀파인 — 수신그룹 일괄등록
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
_sotong_help, _susin_help = _HELP_TEXT.split(_HELP_EDUFINE_MARKER, 1)
_SOTONG_HELP_TEXT = _sotong_help.replace(
    f'{APP_NAME}  v{APP_VERSION}  —  소통메신저·에듀파인 수신자 한 번에',
    f'소통픽 사용법  v{APP_VERSION}  —  소통메신저 수신자 자동 선택',
    1,
).rstrip()
_SUSIN_HELP_TEXT = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  수신픽 사용법  v{APP_VERSION}  —  에듀파인 수신그룹 엑셀 만들기
  처음 사용자도 따라할 수 있도록 작성되었습니다.
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
         '그룹기호는 선택 사항이므로 필요 없으면 비워 두세요.'),
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

class ClipboardWalker(tk.Toplevel):
    """기관명을 한 건씩 클립보드에 넣어 주는 창.

    기관코드가 없어도 쓸 수 있는 경로다. 에듀파인 [수신자 지정] 조직명 칸에
    Ctrl+V → Enter → 체크 → >> 만 반복하면 된다.
    """

    def __init__(self, parent, items):
        super().__init__(parent)
        self.items = list(items)
        self.idx = 0
        self.title('클립보드 순차 복사')
        self.geometry('520x260')
        self.resizable(False, False)
        self.configure(bg='#F5F7FA')
        self.transient(parent)

        tk.Label(
            self, text='에듀파인 조직명 칸에 Ctrl+V → Enter → 체크 → >>  를 반복하세요.',
            bg='#F5F7FA', fg='#37474F', font=('맑은 고딕', 9)
        ).pack(pady=(14, 6))

        self.name_var = tk.StringVar()
        tk.Label(
            self, textvariable=self.name_var, bg='#F5F7FA', fg='#0D47A1',
            font=('맑은 고딕', 18, 'bold'), wraplength=480
        ).pack(pady=6)

        self.progress_var = tk.StringVar()
        tk.Label(self, textvariable=self.progress_var, bg='#F5F7FA',
                 fg='#555', font=('맑은 고딕', 9)).pack()

        row = tk.Frame(self, bg='#F5F7FA')
        row.pack(pady=14)

        tk.Button(row, text='← 이전', command=self.prev,
                  bg='#90A4AE', fg='white', activebackground='#78909C',
                  relief='flat', font=('맑은 고딕', 9), padx=12, pady=6,
                  cursor='hand2').pack(side='left', padx=4)

        self.next_btn = tk.Button(
            row, text='복사하고 다음  (Enter)', command=self.advance,
            bg='#6A1B9A', fg='white', activebackground='#4A148C',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=18, pady=6,
            cursor='hand2')
        self.next_btn.pack(side='left', padx=4)

        tk.Button(row, text='닫기', command=self.destroy,
                  bg='#B0BEC5', fg='white', activebackground='#90A4AE',
                  relief='flat', font=('맑은 고딕', 9), padx=12, pady=6,
                  cursor='hand2').pack(side='left', padx=4)

        self.note = tk.Label(self, text='', bg='#F5F7FA', fg='#C62828',
                             font=('맑은 고딕', 8))
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


class WalkthroughDialog(tk.Toplevel):
    """실제 조작할 위젯을 강조하며 순서대로 안내하는 따라하기 창."""

    def __init__(self, parent, title, steps, on_step, on_close):
        super().__init__(parent)
        self.parent = parent
        self.guide_title = title
        self.steps = list(steps)
        self.on_step = on_step
        self.on_close = on_close
        self.idx = 0
        self._closed = False
        self.highlight_target = None
        self.highlight_frames = [
            tk.Frame(parent, bg='#FFC107') for _ in range(4)
        ]

        self.title(title)
        self.geometry('460x290')
        self.resizable(False, False)
        self.transient(parent)
        self.configure(bg='#F5F7FA')
        self.protocol('WM_DELETE_WINDOW', self.finish)
        try:
            self.attributes('-topmost', True)
        except tk.TclError:
            pass

        self.progress_var = tk.StringVar()
        tk.Label(self, textvariable=self.progress_var, bg='#1565C0', fg='white',
                 font=('맑은 고딕', 10, 'bold'), anchor='w', padx=16, pady=10).pack(fill='x')

        self.heading_var = tk.StringVar()
        tk.Label(self, textvariable=self.heading_var, bg='#F5F7FA', fg='#0D47A1',
                 font=('맑은 고딕', 16, 'bold'), anchor='w').pack(
                     fill='x', padx=24, pady=(24, 10))

        self.body_var = tk.StringVar()
        tk.Label(self, textvariable=self.body_var, bg='#F5F7FA', fg='#37474F',
                 font=('맑은 고딕', 11), justify='left', anchor='nw',
                 wraplength=410).pack(fill='both', expand=True, padx=24)

        tk.Label(
            self, text='노란색 테두리로 표시된 부분에서 이 단계를 진행하세요.',
            bg='#FFF8E1', fg='#E65100', font=('맑은 고딕', 9, 'bold'),
            anchor='w', padx=10, pady=6
        ).pack(fill='x', padx=20, pady=(8, 0))

        buttons = tk.Frame(self, bg='#F5F7FA')
        buttons.pack(fill='x', padx=20, pady=18)
        self.prev_btn = tk.Button(
            buttons, text='이전', command=self.prev,
            bg='#90A4AE', fg='white', relief='flat', padx=14, pady=6)
        self.prev_btn.pack(side='left')
        tk.Button(
            buttons, text='건너뛰기', command=self.finish,
            bg='#B0BEC5', fg='white', relief='flat', padx=14, pady=6).pack(
                side='right', padx=(8, 0))
        self.next_btn = tk.Button(
            buttons, text='다음', command=self.next,
            bg='#1565C0', fg='white', relief='flat', padx=18, pady=6)
        self.next_btn.pack(side='right')

        self.bind('<Left>', lambda _e: self.prev())
        self.bind('<Right>', lambda _e: self.next())
        self.bind('<Escape>', lambda _e: self.finish())
        self._render()

    def _render(self):
        tab_key, widget_key, heading, body = self.steps[self.idx]
        total = len(self.steps)
        self.progress_var.set(f'{self.idx + 1} / {total}  {self.guide_title}')
        self.heading_var.set(heading)
        self.body_var.set(body)
        self.prev_btn.config(state='normal' if self.idx else 'disabled')
        self.next_btn.config(text='끝내기' if self.idx == total - 1 else '다음')
        target = self.on_step(tab_key, widget_key)
        self.parent.update_idletasks()
        self.update_idletasks()
        self._highlight(target)
        self._move_next_to(target)
        self.lift()

    def _highlight(self, target):
        """대상을 가리지 않도록 네 개의 얇은 프레임으로 테두리만 그린다."""
        self._clear_highlight()
        self.highlight_target = target
        if target is None:
            return
        try:
            x = target.winfo_rootx() - self.parent.winfo_rootx()
            y = target.winfo_rooty() - self.parent.winfo_rooty()
            width = target.winfo_width()
            height = target.winfo_height()
        except tk.TclError:
            self.highlight_target = None
            return
        if width <= 1 or height <= 1:
            return

        pad = 4
        thickness = 4
        top, bottom, left, right = self.highlight_frames
        top.place(x=x - pad, y=y - pad,
                  width=width + pad * 2, height=thickness)
        bottom.place(x=x - pad, y=y + height + pad - thickness,
                     width=width + pad * 2, height=thickness)
        left.place(x=x - pad, y=y - pad,
                   width=thickness, height=height + pad * 2)
        right.place(x=x + width + pad - thickness, y=y - pad,
                    width=thickness, height=height + pad * 2)
        for border in self.highlight_frames:
            border.lift()

    def _clear_highlight(self):
        for border in self.highlight_frames:
            border.place_forget()

    def _move_next_to(self, target):
        """안내창을 강조 대상 옆에 배치해 대상이 가려지지 않게 한다."""
        if target is None:
            return
        try:
            target_x = target.winfo_rootx()
            target_y = target.winfo_rooty()
            target_width = target.winfo_width()
            target_height = target.winfo_height()
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
        except tk.TclError:
            return

        width, height, gap = 460, 290, 14
        if target_x + target_width + gap + width <= screen_width:
            x = target_x + target_width + gap
        elif target_x - gap - width >= 0:
            x = target_x - gap - width
        else:
            x = target_x

        y = target_y
        if y + height > screen_height:
            y = target_y + target_height - height
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
        self.geometry(f'{width}x{height}+{x}+{y}')

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
        self._clear_highlight()
        for border in self.highlight_frames:
            border.destroy()
        self.on_close()
        self.destroy()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f'{APP_NAME}  v{APP_VERSION}')
        self.root.geometry('900x720')
        self.root.minsize(880, 700)

        self.config = Config()
        self.codes = edufine.load_codes()
        self.names_list: list = []
        self.last_org_duplicates: list = []
        self.stop_flag = threading.Event()
        self.continue_event = threading.Event()
        self.continue_event.set()
        self.worker_thread = None
        self.guide_dialog = None

        self._apply_theme()
        self._build_ui()
        self._refresh_calib_labels()
        self._check_deps()
        self._check_for_update_async()

    # ── 테마 (충북교육청 블루) ─────────────────
    def _apply_theme(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception as exc:
            logging.info("Tk 테마 적용 실패: %s", exc)
        style.configure('TNotebook', background='#E8EAF6', tabmargins=[2, 5, 2, 0])
        style.configure('TNotebook.Tab', padding=[14, 7],
                        font=('맑은 고딕', 10, 'bold'),
                        background='#C5CAE9', foreground='#37474F')
        style.map('TNotebook.Tab',
                  background=[('selected', '#1565C0')],
                  foreground=[('selected', 'white')])
        style.configure('TFrame', background='#F5F7FA')
        style.configure('TLabelframe', background='#F5F7FA')
        style.configure('TLabelframe.Label',
                        font=('맑은 고딕', 10, 'bold'), foreground='#1565C0')

    # ── UI 빌드 ────────────────────────────────
    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        # 개발자 정보 바 (항상 상단 표시)
        dev_bar = tk.Label(
            self.root,
            text=f'  {APP_NAME} v{APP_VERSION}  |  Developed by 송동석'
                 '  |  초등교사 · 데이터 분석 · 앱 개발'
                 '  |  협업: dungst.me@gmail.com  ',
            bg='#1565C0', fg='white',
            font=('맑은 고딕', 9), anchor='w', pady=5
        )
        dev_bar.grid(row=0, column=0, sticky='ew')

        # 어느 도구를 쓸지. 탭 위에 둬서 어느 화면에서든 바로 바꿀 수 있게 한다.
        picker = tk.Frame(self.root, bg='#263238')
        picker.grid(row=1, column=0, sticky='ew')
        picker.columnconfigure(0, weight=1, uniform='pick')
        picker.columnconfigure(1, weight=1, uniform='pick')

        tk.Label(
            picker, text='먼저 어느 쪽을 쓸지 고르세요',
            bg='#263238', fg='#ECEFF1', font=('맑은 고딕', 10, 'bold'), anchor='w'
        ).grid(row=0, column=0, columnspan=2, sticky='w', padx=14, pady=(10, 6))

        self.target_var = tk.StringVar(value=self.config.target)
        self.target_cards = {}
        for col, target in enumerate((TARGET_MESSENGER, TARGET_EDUFINE)):
            card = tk.Frame(picker, cursor='hand2', highlightthickness=3)
            card.grid(row=1, column=col, sticky='nsew',
                      padx=(14, 7) if col == 0 else (7, 14), pady=(0, 12))
            card.columnconfigure(0, weight=1)

            title = tk.Label(card, font=('맑은 고딕', 14, 'bold'), anchor='w')
            title.grid(row=0, column=0, sticky='ew', padx=14, pady=(10, 0))

            desc = tk.Label(card, text=TARGET_SUMMARIES[target],
                            font=('맑은 고딕', 9), anchor='w', justify='left')
            desc.grid(row=1, column=0, sticky='ew', padx=14, pady=(2, 10))

            self.target_cards[target] = (card, title, desc)
            for widget in (card, title, desc):
                widget.bind('<Button-1>', lambda e, t=target: self._choose_target(t))

        self.target_hint = tk.Label(
            picker, text='', bg='#263238', fg='#B0BEC5',
            font=('맑은 고딕', 9), anchor='w'
        )
        self.target_hint.grid(row=2, column=0, sticky='w',
                              padx=14, pady=(0, 10))

        tk.Button(
            picker, text='사용 가이드',
            command=lambda: self._show_onboarding(self.config.target),
            bg='#455A64', fg='white', activebackground='#37474F',
            relief='flat', font=('맑은 고딕', 9), padx=10, pady=4,
            cursor='hand2'
        ).grid(row=2, column=1, sticky='e', padx=14, pady=(0, 8))

        # 탭 노트북
        nb = ttk.Notebook(self.root)
        nb.grid(row=2, column=0, sticky='nsew', padx=4, pady=(4, 4))

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

        self._tab_input(f1)
        self._tab_calib(f2)
        self._tab_auto(f3)
        self._tab_edufine(f4)
        self._tab_help(f5, TARGET_MESSENGER)
        self._tab_help(f6, TARGET_EDUFINE)
        self._apply_target()

        # 상태바
        self.status_var = tk.StringVar(value='준비')
        tk.Label(
            self.root, textvariable=self.status_var,
            relief='sunken', anchor='w', bg='#f0f0f0', fg='#333',
            font=('맑은 고딕', 9), pady=3
        ).grid(row=3, column=0, sticky='ew')
        self._refresh_ready_status()

    # ── 탭 1: 명단 입력 ────────────────────────
    def _tab_input(self, frame: ttk.Frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        frame.rowconfigure(6, weight=2)

        # ① 입력 형식 안내 박스
        guide = tk.Frame(frame, bg='#E3F2FD', bd=1, relief='solid')
        guide.grid(row=0, column=0, sticky='ew', padx=10, pady=(6, 4))
        guide.columnconfigure(0, weight=1)

        self.guide_title = tk.Label(
            guide, text='', bg='#E3F2FD', fg='#0D47A1',
            font=('맑은 고딕', 9, 'bold'), anchor='w')
        self.guide_title.grid(row=0, column=0, sticky='w', padx=10, pady=(6, 2))

        self.guide_body = tk.Label(
            guide, text='', bg='#E3F2FD', fg='#333',
            font=('맑은 고딕', 9), justify='left', anchor='w')
        self.guide_body.grid(row=1, column=0, sticky='w', padx=10, pady=(0, 8))

        self.ready_status = tk.Label(
            guide, text='', bg='#E3F2FD', fg='#0D47A1',
            font=('맑은 고딕', 9, 'bold'), anchor='w'
        )
        self.ready_status.grid(row=2, column=0, sticky='ew', padx=10, pady=(0, 8))

        # ② 파일 열기 버튼 행
        file_btn_frame = tk.Frame(frame, bg='#F5F7FA')
        file_btn_frame.grid(row=1, column=0, sticky='ew', padx=8, pady=(0, 2))

        for text, cmd, bg in [
            ('엑셀 파일 열기 (.xlsx)', self._open_excel, '#607D8B'),
            ('HWP 파일 열기 (.hwp)',   self._open_hwp,   '#607D8B'),
        ]:
            tk.Button(
                file_btn_frame, text=text, command=cmd,
                bg=bg, fg='white', activebackground=bg,
                relief='flat', font=('맑은 고딕', 9), padx=8, pady=4, cursor='hand2'
            ).pack(side='left', padx=3)

        # ③ 텍스트 입력 영역
        self.input_text = scrolledtext.ScrolledText(
            frame, height=8, font=('맑은 고딕', 9), wrap='none'
        )
        self.input_text.grid(row=2, column=0, sticky='nsew', padx=8, pady=4)

        # ④ 추출 버튼 행
        action_frame = tk.Frame(frame, bg='#F5F7FA')
        action_frame.grid(row=3, column=0, sticky='ew', padx=8, pady=(0, 4))

        for attr, text, cmd, bg in [
            ('parse_button', '명단 추출 →', self._parse,       '#1565C0'),
            (None,           '초기화',       self._clear_input, '#E53935'),
        ]:
            button = tk.Button(
                action_frame, text=text, command=cmd,
                bg=bg, fg='white', activebackground=bg,
                relief='flat', font=('맑은 고딕', 9, 'bold'), padx=12, pady=5, cursor='hand2'
            )
            button.pack(side='left', padx=3)
            if attr:
                setattr(self, attr, button)

        # 아래 버튼들은 수신픽에서만 쓴다. _apply_target 이 보이고 감춘다.
        # 부서는 전체경로를 외울 수 없으니 목록에서 고르게 한다
        self.browse_btn = tk.Button(
            action_frame, text='기관 찾아보기…', command=self._open_org_picker,
            bg='#00695C', fg='white', activebackground='#004D40',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=12, pady=5, cursor='hand2')

        self.bulk_fix_btn = tk.Button(
            action_frame, text='확인 필요 기관 일괄 수정', command=self._open_bulk_org_editor,
            bg='#C62828', fg='white', activebackground='#B71C1C',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=12, pady=5,
            cursor='hand2', state='disabled')

        self.org_history_btn = tk.Button(
            action_frame, text='추출 기록 보기', command=self._open_org_history,
            bg='#546E7A', fg='white', activebackground='#455A64',
            relief='flat', font=('맑은 고딕', 9), padx=10, pady=5,
            cursor='hand2')

        # ⑤ 추출 결과 상태 라벨
        self.parse_status = tk.Label(
            frame, text='', fg='#555', font=('맑은 고딕', 9), anchor='w'
        )
        self.parse_status.grid(row=4, column=0, sticky='w', padx=12, pady=(0, 2))

        self.org_issue_summary = tk.Label(
            frame, text='', fg='#B71C1C', bg='#FFEBEE',
            font=('맑은 고딕', 9, 'bold'), justify='left', anchor='w',
            wraplength=840, padx=8, pady=4
        )
        self.org_issue_summary.grid(row=5, column=0, sticky='ew', padx=8, pady=(0, 4))

        # ⑥ 추출된 명단 리스트
        list_frame = tk.Frame(frame)
        list_frame.grid(row=6, column=0, sticky='nsew', padx=8, pady=(0, 4))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.parsed_list = tk.Listbox(
            list_frame, font=('맑은 고딕', 9), selectmode='extended',
            activestyle='none', selectbackground='#1565C0', selectforeground='white'
        )
        self.parsed_list.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(list_frame, orient='vertical',
                           command=self.parsed_list.yview)
        sb.grid(row=0, column=1, sticky='ns')
        self.parsed_list.config(yscrollcommand=sb.set)

        # ⑦ 하단 버튼 + 범례
        bottom_frame = tk.Frame(frame, bg='#F5F7FA')
        bottom_frame.grid(row=7, column=0, sticky='ew', padx=8, pady=(0, 6))
        bottom_frame.columnconfigure(1, weight=1)

        tk.Button(
            bottom_frame, text='선택 항목 삭제 (Del)', command=self._delete_selected,
            bg='#EF6C00', fg='white', activebackground='#E65100',
            relief='flat', font=('맑은 고딕', 9), padx=8, pady=3, cursor='hand2'
        ).grid(row=0, column=0, sticky='w')

        tk.Label(
            bottom_frame,
            text='더블클릭으로 수정  ·  ● 빨간색 = 자동 선택 실패',
            fg='#555', font=('맑은 고딕', 8), bg='#F5F7FA', anchor='e'
        ).grid(row=0, column=1, sticky='e', padx=(0, 4))

        ctx = tk.Menu(self.root, tearoff=0)
        ctx.add_command(label='수정', command=self._edit_item)
        ctx.add_command(label='삭제', command=self._delete_selected)
        self.parsed_list.bind('<Button-3>', lambda e: ctx.tk_popup(e.x_root, e.y_root))
        self.parsed_list.bind('<Double-Button-1>', self._edit_item)
        self.parsed_list.bind('<Delete>', lambda e: self._delete_selected())

    # ── 탭 2: 위치 설정 ────────────────────────
    def _tab_calib(self, frame: ttk.Frame):
        frame.columnconfigure(0, weight=1)

        self.calib_intro = tk.Label(
            frame, text='', fg='#555', font=('맑은 고딕', 9), justify='center')
        self.calib_intro.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 6))

        # STEP 1·2·3: 위치 설정
        pos_frame = ttk.LabelFrame(frame, text='STEP 1 · 2 · 3 — 위치 설정 (순서대로)')
        pos_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=4)
        pos_frame.columnconfigure(1, weight=1)
        self.calibration_panel = pos_frame

        for row_i, (label_text, key) in enumerate([
            ('STEP 1  검색 입력창:', 'search_field'),
            ('STEP 2  결과 첫 번째:', 'result_first'),
            ('STEP 3  사용자 선택 버튼:', 'add_button'),
        ]):
            tk.Label(pos_frame, text=label_text,
                     font=('맑은 고딕', 9, 'bold')).grid(
                row=row_i, column=0, padx=8, pady=6, sticky='w')

            lbl = tk.Label(pos_frame, text='미설정', fg='red',
                           font=('맑은 고딕', 9))
            lbl.grid(row=row_i, column=1, sticky='w', padx=4)
            setattr(self, f'lbl_{key}', lbl)

            tk.Button(
                pos_frame, text='📍 위치 설정',
                bg='#FF9800', fg='white', activebackground='#FF9800',
                relief='flat', font=('맑은 고딕', 9), padx=6, pady=3,
                cursor='hand2',
                command=lambda k=key: self._do_capture(k)
            ).grid(row=row_i, column=2, padx=8, pady=4)

        # 검색 설정
        setting_frame = ttk.LabelFrame(frame, text='검색 설정')
        setting_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=4)

        tk.Label(setting_frame, text='검색 후 대기 시간(초):',
                 font=('맑은 고딕', 9)).grid(row=0, column=0, padx=8, pady=6, sticky='w')

        self.delay_var = tk.DoubleVar(value=self.config.data.get('search_delay', 0.5))
        ttk.Spinbox(
            setting_frame, from_=0.3, to=5.0, increment=0.1,
            textvariable=self.delay_var, width=6,
            font=('맑은 고딕', 9)
        ).grid(row=0, column=1, padx=4, sticky='w')

        tk.Label(setting_frame, text='(느리면 값을 높이세요)',
                 fg='#888', font=('맑은 고딕', 9)).grid(
            row=0, column=2, padx=4, sticky='w')

        self.manual_var = tk.BooleanVar(
            value=self.config.data.get('manual_confirm', False)
        )
        tk.Checkbutton(
            setting_frame,
            text='수동 확인 모드 권장 — 검색 후 [계속] 버튼을 눌러야 다음으로 진행\n'
                 '(동명이인·검색 결과 오탐이 있을 때 안전: 결과 클릭 → 선택 버튼 클릭을 직접 수행)',
            variable=self.manual_var,
            font=('맑은 고딕', 9), justify='left', anchor='w'
        ).grid(row=1, column=0, columnspan=3, sticky='w', padx=8, pady=4)

        self.verify_var = tk.BooleanVar(
            value=self.config.data.get('verify_add', True)
        )
        tk.Checkbutton(
            setting_frame,
            text='추가됐는지 확인하고 넘어가기 (권장)\n'
                 '한 사람마다 선택 버튼을 한 번 더 눌러 봅니다. 이미 들어가 있으면 소통메신저가\n'
                 "'선택된 사용자 입니다.' 안내창을 띄우는데, 그것을 추가됐다는 증거로 씁니다.\n"
                 '안내창이 끝까지 없으면 추가되지 않은 것이라 빨간 항목으로 남깁니다.\n'
                 '끄면 빨라지지만 빠진 사람을 알 수 없습니다.',
            variable=self.verify_var,
            font=('맑은 고딕', 9), justify='left', anchor='w'
        ).grid(row=2, column=0, columnspan=3, sticky='w', padx=8, pady=4)

        tk.Button(
            frame, text='✅  설정 저장',
            bg='#4CAF50', fg='white', activebackground='#4CAF50',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=12, pady=6,
            cursor='hand2', command=self._save_calib
        ).grid(row=4, column=0, pady=8)

        self.calib_msg = tk.Label(
            frame, text='', fg='green', font=('맑은 고딕', 9)
        )
        self.calib_msg.grid(row=5, column=0)

    # ── 탭 4: 수신그룹 엑셀 (에듀파인 전용) ────
    def _tab_edufine(self, frame: ttk.Frame):
        frame.columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text='에듀파인 [개인설정 > 개인수신그룹관리 > 일괄등록] 에 올릴 엑셀을 만듭니다.\n'
                 '한 번 등록해 두면 다음부터는 기안할 때 [수신자 지정 > 개인수신그룹] 에서 그룹만 고르면 됩니다.',
            bg='#E3F2FD', fg='#0D47A1', font=('맑은 고딕', 9),
            justify='left', anchor='w', padx=10, pady=8
        ).grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 6))

        self.codes_status = tk.Label(
            frame, text='', anchor='w', justify='left',
            font=('맑은 고딕', 9, 'bold'), bg='#E8F5E9', fg='#1B5E20',
            padx=10, pady=7
        )
        self.codes_status.grid(row=1, column=0, sticky='ew', padx=10, pady=4)

        # ① 내 정보 — 매번 같은 값이라 한 번만 넣는다
        me_frame = ttk.LabelFrame(frame, text='STEP 1 — 내 정보 (한 번만 입력)')
        me_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=4)
        me_frame.columnconfigure(1, weight=1)
        me_frame.columnconfigure(3, weight=1)
        self.edufine_me_panel = me_frame

        self.edufine_vars = {
            '등록교육청코드': tk.StringVar(value=edufine.REGISTERING_OFFICE_CODE),
        }

        for key, c in [('사용자ID', 0), ('사용자명', 2)]:
            tk.Label(me_frame, text=key, bg='#F5F7FA',
                     font=('맑은 고딕', 9)).grid(row=0, column=c, sticky='w', padx=(8, 4), pady=5)
            var = tk.StringVar(value=self.config.edufine.get(key, ''))
            self.edufine_vars[key] = var
            entry = ttk.Entry(me_frame, textvariable=var, width=20)
            entry.grid(row=0, column=c + 1, sticky='ew', padx=(0, 10), pady=5)
            entry.bind('<FocusOut>', lambda e: self._save_edufine_fields())

        tk.Label(
            me_frame,
            text='등록교육청은 충청북도교육청으로 자동 적용됩니다. 사용자ID와 사용자명만 입력하세요.',
            fg='#555', font=('맑은 고딕', 8), bg='#F5F7FA', anchor='w'
        ).grid(row=1, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 6))

        # ② 그룹 만들기
        group_frame = ttk.LabelFrame(frame, text='STEP 2 — 수신그룹 만들기')
        group_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=4)
        group_frame.columnconfigure(1, weight=1)
        group_frame.columnconfigure(3, weight=1)
        self.edufine_group_panel = group_frame

        for key, c in [('그룹명', 0), ('그룹기호', 2)]:
            tk.Label(group_frame, text=key, bg='#F5F7FA',
                     font=('맑은 고딕', 9)).grid(row=0, column=c, sticky='w', padx=(8, 4), pady=6)
            var = tk.StringVar(value=self.config.edufine.get(key, ''))
            self.edufine_vars[key] = var
            ttk.Entry(group_frame, textvariable=var, width=20).grid(
                row=0, column=c + 1, sticky='ew', padx=(0, 10), pady=6)

        tk.Label(
            group_frame,
            text='그룹명은 에듀파인에서 찾기 쉬운 이름으로 적으세요. 예: 2026 진천 초등학교, 2학기 업무담당자',
            fg='#37474F', font=('맑은 고딕', 8), bg='#F5F7FA', anchor='w'
        ).grid(row=1, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 2))
        tk.Label(
            group_frame,
            text='그룹기호는 선택 사항입니다. 따로 쓰지 않으면 비워 두어도 됩니다.',
            fg='#37474F', font=('맑은 고딕', 8), bg='#F5F7FA', anchor='w'
        ).grid(row=2, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 7))

        btn_row = tk.Frame(group_frame, bg='#F5F7FA')
        btn_row.grid(row=3, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 8))

        self.edufine_make_button = tk.Button(
            btn_row, text='수신그룹 엑셀 만들기', command=self._build_group_excel,
            bg='#1565C0', fg='white', activebackground='#0D47A1',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=14, pady=6, cursor='hand2'
        )
        self.edufine_make_button.pack(side='left')

        tk.Button(
            btn_row, text='코드 없는 기관 순차 복사', command=self._open_clipboard_walker,
            bg='#6A1B9A', fg='white', activebackground='#4A148C',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=14, pady=6, cursor='hand2'
        ).pack(side='left', padx=(8, 0))

        tk.Label(
            btn_row,
            text='코드가 없는 기관은 순차 복사로 조직도에 직접 붙여넣으세요',
            fg='#555', font=('맑은 고딕', 8), bg='#F5F7FA'
        ).pack(side='left', padx=(10, 0))

        # 빈 양식 받기 — 에듀파인이 요구하는 서식을 눈으로 확인하고 싶을 때
        sample_row = tk.Frame(group_frame, bg='#F5F7FA')
        sample_row.grid(row=4, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 8))
        tk.Button(
            sample_row, text='빈 양식 받기', command=self._save_blank_template,
            bg='#546E7A', fg='white', activebackground='#455A64',
            relief='flat', font=('맑은 고딕', 9), padx=12, pady=4, cursor='hand2'
        ).pack(side='left')
        tk.Label(
            sample_row,
            text='에듀파인 [파일양식받기] 와 같은 빈 양식입니다. 서식 확인이나 수기 작성에 쓰세요.',
            fg='#555', font=('맑은 고딕', 8), bg='#F5F7FA'
        ).pack(side='left', padx=(10, 0))

        self.edufine_msg = tk.Label(
            frame, text='', fg='#555', font=('맑은 고딕', 9),
            justify='left', anchor='w', wraplength=820
        )
        self.edufine_msg.grid(row=4, column=0, sticky='ew', padx=14, pady=(2, 10))

    def _open_org_picker(self):
        """기관 찾아보기 — 770곳에서 골라 명단에 넣는다.

        '충청북도청주교육지원청 행정과' 같은 전체경로를 외울 수는 없다.
        """
        if not self.codes.get('기관'):
            messagebox.showwarning(
                '기관코드가 없습니다',
                '[수신그룹 엑셀] 탭에서 기관코드를 먼저 가져오세요.')
            return

        dlg = tk.Toplevel(self.root)
        dlg.title('기관 찾아보기')
        dlg.geometry('680x600')
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.configure(bg='#F5F7FA')

        tk.Label(dlg, text='찾을 말을 띄어쓰기로 나눠 적으면 모두 포함된 기관만 보입니다.\n'
                           '예)  청주 초등학교   ·   행정과   ·   단재 연수부',
                 bg='#F5F7FA', fg='#546E7A', font=('맑은 고딕', 9),
                 justify='left').pack(anchor='w', padx=16, pady=(14, 6))

        query = tk.StringVar()
        entry = ttk.Entry(dlg, textvariable=query, font=('맑은 고딕', 11))
        entry.pack(fill='x', padx=16)
        entry.focus_set()

        # 분류 버튼 — 초등학교만, 교육지원청만 처럼 한 번에 좁힌다
        self.picker_category = None
        cat_row = tk.Frame(dlg, bg='#F5F7FA')
        cat_row.pack(fill='x', padx=16, pady=(8, 2))
        counts = edufine.category_counts(self.codes)
        cat_buttons = {}

        def choose_category(name):
            self.picker_category = None if self.picker_category == name else name
            for key, btn in cat_buttons.items():
                on = key == self.picker_category
                btn.config(bg='#1565C0' if on else '#CFD8DC',
                           fg='white' if on else '#37474F')
            refresh()

        for name in edufine.CATEGORIES:
            if not counts.get(name):
                continue
            btn = tk.Button(
                cat_row, text=f'{name} {counts[name]}',
                command=lambda n=name: choose_category(n),
                bg='#CFD8DC', fg='#37474F', activebackground='#B0BEC5',
                relief='flat', font=('맑은 고딕', 8), padx=8, pady=3, cursor='hand2')
            btn.pack(side='left', padx=2)
            cat_buttons[name] = btn

        count_label = tk.Label(dlg, text='', bg='#F5F7FA', fg='#555',
                               font=('맑은 고딕', 9), anchor='w')
        count_label.pack(fill='x', padx=16, pady=(6, 2))

        list_wrap = tk.Frame(dlg)
        list_wrap.pack(fill='both', expand=True, padx=16)
        box = tk.Listbox(list_wrap, font=('맑은 고딕', 10), selectmode='extended',
                         activestyle='none', selectbackground='#1565C0',
                         selectforeground='white')
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

        btns = tk.Frame(dlg, bg='#F5F7FA')
        btns.pack(pady=12)
        tk.Button(btns, text='선택한 것 넣기', command=add_selected,
                  bg='#1565C0', fg='white', activebackground='#0D47A1',
                  relief='flat', font=('맑은 고딕', 9, 'bold'),
                  padx=16, pady=6, cursor='hand2').pack(side='left', padx=4)
        tk.Button(btns, text='보이는 것 전부 넣기', command=add_all_shown,
                  bg='#00695C', fg='white', activebackground='#004D40',
                  relief='flat', font=('맑은 고딕', 9, 'bold'),
                  padx=16, pady=6, cursor='hand2').pack(side='left', padx=4)
        tk.Button(btns, text='닫기', command=dlg.destroy,
                  bg='#B0BEC5', fg='white', activebackground='#90A4AE',
                  relief='flat', font=('맑은 고딕', 9),
                  padx=14, pady=6, cursor='hand2').pack(side='left', padx=4)

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
                    fg='#1B5E20')
            else:
                label.config(text='내장 기관코드 파일을 찾을 수 없습니다', fg='#C62828')

        msg = getattr(self, 'edufine_msg', None)
        if msg and self.names_list:
            ready, missing = self._split_confirmed()
            parts = [f'엑셀에 들어갈 기관 {len(ready)}곳']
            if missing:
                parts.append(f'빠지는 기관 {len(missing)}곳')
            msg.config(text='  ·  '.join(parts))
        elif msg:
            msg.config(text='')

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
                'STEP 1 의 사용자ID와 사용자명을 채워주세요.')
            return

        group_name = self.config.edufine.get('그룹명', '').strip()
        if not group_name:
            messagebox.showwarning('그룹명이 필요합니다', 'STEP 2 에 수신그룹명을 적어주세요.')
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
                f"· {r.get('name') or r.get('raw')} — {r.get('reason', '코드 없음')}"
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

        self.status_var.set(f'수신그룹 엑셀 저장 완료: {len(ready)}곳')
        messagebox.showinfo(
            '저장했습니다',
            f'{len(ready)}곳이 담긴 엑셀을 만들었습니다.\n\n{path}\n\n'
            '에듀파인 [개인설정 > 개인수신그룹관리 > 일괄등록] 에서 이 파일을 올리세요.')

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
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        self.auto_intro = tk.Label(
            frame, text='', fg='#555', font=('맑은 고딕', 9), justify='center')
        self.auto_intro.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 6))

        btn_frame = tk.Frame(frame, bg='#F5F7FA')
        btn_frame.grid(row=1, column=0, sticky='ew', padx=8, pady=4)

        self.start_btn = tk.Button(
            btn_frame, text='▶  자동 선택 시작',
            bg='#4CAF50', fg='white', activebackground='#388E3C',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=10, pady=6,
            cursor='hand2', command=self._start
        )
        self.start_btn.pack(side='left', padx=4)

        self.continue_btn = tk.Button(
            btn_frame, text='▶▶  계속',
            bg='#2196F3', fg='white', activebackground='#1565C0',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=10, pady=6,
            cursor='hand2', state='disabled', command=self._resume
        )
        self.continue_btn.pack(side='left', padx=4)

        self.stop_btn = tk.Button(
            btn_frame, text='■  중지',
            bg='#F44336', fg='white', activebackground='#C62828',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=10, pady=6,
            cursor='hand2', state='disabled', command=self._stop
        )
        self.stop_btn.pack(side='left', padx=4)

        self.retry_failed_btn = tk.Button(
            btn_frame, text='↻  실패 항목만 다시 실행',
            bg='#795548', fg='white', activebackground='#5D4037',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=10, pady=6,
            cursor='hand2', state='disabled', command=self._retry_failed
        )
        self.retry_failed_btn.pack(side='left', padx=4)

        tk.Button(
            btn_frame, text='로그 지우기',
            bg='#607D8B', fg='white', activebackground='#455A64',
            relief='flat', font=('맑은 고딕', 9), padx=9, pady=6,
            cursor='hand2', command=self._log_clear
        ).pack(side='left', padx=4)

        tk.Label(frame, text='진행 상황:', anchor='w',
                 font=('맑은 고딕', 9)).grid(
            row=3, column=0, sticky='w', padx=10, pady=(6, 2))

        self.log = scrolledtext.ScrolledText(
            frame, height=14, state='disabled',
            font=('맑은 고딕', 9), wrap='none'
        )
        self.log.tag_config('ok', foreground='#1B5E20')
        self.log.tag_config('fail', foreground='#B71C1C')
        self.log.grid(row=2, column=0, sticky='nsew', padx=8, pady=4)

        prog_row = tk.Frame(frame, bg='#F5F7FA')
        prog_row.grid(row=4, column=0, sticky='ew', padx=8, pady=(2, 8))
        prog_row.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(prog_row, mode='determinate')
        self.progress.grid(row=0, column=0, sticky='ew')

        self.prog_label = tk.Label(
            prog_row, text='0 / 0', font=('맑은 고딕', 9), bg='#F5F7FA'
        )
        self.prog_label.grid(row=0, column=1, padx=8)

    # ── 제품별 사용 방법 ────────────────────────
    def _tab_help(self, frame: ttk.Frame, target: str):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        label = TARGET_LABELS[target]
        video_btn = tk.Button(
            frame,
            text=f'▶  {label} 사용법 영상 (YouTube)',
            bg='#FF0000', fg='white', activebackground='#CC0000',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=10, pady=6,
            cursor='hand2',
            command=lambda selected=target: webbrowser.open(GUIDE_VIDEO_URLS[selected])
        )
        video_btn.grid(row=0, column=0, pady=(10, 4))
        if target == TARGET_MESSENGER:
            self.sotong_video_btn = video_btn
        else:
            self.susin_video_btn = video_btn

        txt = scrolledtext.ScrolledText(
            frame, font=('맑은 고딕', 10), wrap='word', state='normal'
        )
        txt.grid(row=1, column=0, sticky='nsew', padx=4, pady=4)
        txt.insert('1.0', HELP_TEXTS[target])
        txt.config(state='disabled')

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
            verify = '켜짐' if self.config.data.get('verify_add', True) else '꺼짐'
            delay = self.config.data.get('search_delay', 0.5)
            label.config(
                text=f'{where}  |  명단 {count}명  ·  위치 {positions}  ·  '
                     f'수동 확인 {manual}  ·  추가 확인 {verify}  ·  대기 {delay}초'
            )

    def _refresh_failed_retry_state(self):
        btn = getattr(self, 'retry_failed_btn', None)
        if not btn:
            return
        has_failed = any(item.get('failure_reason') for item in self.names_list)
        btn.config(state='normal' if has_failed else 'disabled')

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
        button = getattr(self, 'bulk_fix_btn', None)
        if summary is None or button is None:
            return
        if not self.is_edufine():
            summary.grid_remove()
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
                f'확인 필요 {len(review)}곳 · 붉은 항목을 '
                '[확인 필요 기관 일괄 수정]에서 한 번에 처리하세요.'
            )

        if lines:
            summary.grid()
            summary.config(
                text='\n'.join(lines),
                bg='#FFEBEE' if review else '#FFF8E1',
                fg='#B71C1C' if review else '#E65100',
            )
        else:
            summary.config(text='')
            summary.grid_remove()

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
        dlg.geometry('720x560')
        dlg.transient(self.root)
        dlg.configure(bg='#F5F7FA')

        tk.Label(
            dlg,
            text=f'최근 {len(history)}회 기록 · 기관명과 상태만 저장하며 원문과 파일 경로는 저장하지 않습니다.',
            bg='#E3F2FD', fg='#0D47A1', font=('맑은 고딕', 9, 'bold'),
            anchor='w', padx=12, pady=8
        ).pack(fill='x')
        text = scrolledtext.ScrolledText(
            dlg, font=('맑은 고딕', 9), wrap='word', state='normal')
        text.pack(fill='both', expand=True, padx=12, pady=10)

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
                text.insert('end', f"  · {item.get('name', '')} — {status}{repeat}\n")
            text.insert('end', '\n')
        text.tag_config('heading', foreground='#0D47A1', font=('맑은 고딕', 10, 'bold'))
        text.config(state='disabled')
        tk.Button(
            dlg, text='닫기', command=dlg.destroy,
            bg='#546E7A', fg='white', relief='flat', padx=18, pady=5
        ).pack(pady=(0, 12))

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
        dlg.geometry('820x560')
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.configure(bg='#F5F7FA')
        dlg.columnconfigure(0, weight=1)
        dlg.columnconfigure(1, weight=2)
        dlg.rowconfigure(2, weight=1)

        tk.Label(
            dlg,
            text='왼쪽의 붉은 기관을 하나씩 선택하고, 오른쪽에서 정확한 기관을 찾아 확정하세요.',
            bg='#FFEBEE', fg='#B71C1C', font=('맑은 고딕', 10, 'bold'),
            anchor='w', padx=12, pady=9
        ).grid(row=0, column=0, columnspan=2, sticky='ew')

        tk.Label(dlg, text='확인 필요 기관', bg='#F5F7FA', fg='#37474F',
                 font=('맑은 고딕', 10, 'bold')).grid(
                     row=1, column=0, sticky='w', padx=12, pady=(10, 4))
        detail_var = tk.StringVar(value='기관을 선택하세요.')
        tk.Label(dlg, textvariable=detail_var, bg='#F5F7FA', fg='#37474F',
                 font=('맑은 고딕', 10, 'bold'), anchor='w').grid(
                     row=1, column=1, sticky='ew', padx=12, pady=(10, 4))

        pending_box = tk.Listbox(
            dlg, font=('맑은 고딕', 9), activestyle='none',
            selectbackground='#C62828', selectforeground='white')
        pending_box.grid(row=2, column=0, sticky='nsew', padx=(12, 6), pady=(0, 8))

        right = tk.Frame(dlg, bg='#F5F7FA')
        right.grid(row=2, column=1, sticky='nsew', padx=(6, 12), pady=(0, 8))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        tk.Label(right, text='기관 검색', bg='#F5F7FA', fg='#555',
                 font=('맑은 고딕', 9)).grid(row=0, column=0, sticky='w')
        query = tk.StringVar()
        search_entry = ttk.Entry(right, textvariable=query, font=('맑은 고딕', 10))
        search_entry.grid(row=1, column=0, sticky='ew', pady=(2, 6))
        result_box = tk.Listbox(
            right, font=('맑은 고딕', 9), activestyle='none',
            selectbackground='#1565C0', selectforeground='white')
        result_box.grid(row=2, column=0, sticky='nsew')

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

        buttons = tk.Frame(dlg, bg='#F5F7FA')
        buttons.grid(row=3, column=0, columnspan=2, pady=(2, 12))
        tk.Button(
            buttons, text='선택 기관으로 확정', command=confirm_selected,
            bg='#1565C0', fg='white', relief='flat', padx=18, pady=6,
            font=('맑은 고딕', 9, 'bold')).pack(side='left', padx=4)
        tk.Button(
            buttons, text='명단에서 제외', command=remove_selected,
            bg='#C62828', fg='white', relief='flat', padx=14, pady=6,
            font=('맑은 고딕', 9)).pack(side='left', padx=4)
        tk.Button(
            buttons, text='완료', command=dlg.destroy,
            bg='#546E7A', fg='white', relief='flat', padx=18, pady=6,
            font=('맑은 고딕', 9)).pack(side='left', padx=4)

        refresh_pending()
        search_entry.focus_set()

    def _rebuild_parsed_list(self):
        self.parsed_list.delete(0, 'end')
        for item in self.names_list:
            self.parsed_list.insert('end', self._format_item_label(item))
            if item.get('failure_reason'):
                self.parsed_list.itemconfig('end', {'bg': '#FFCDD2', 'fg': '#B71C1C'})
            elif self.is_edufine() and self._org_needs_review(item):
                self.parsed_list.itemconfig('end', {'bg': '#FFEBEE', 'fg': '#B71C1C'})
            elif not item.get('org'):
                self.parsed_list.itemconfig('end', {'bg': '#E0E0E0', 'fg': '#757575'})
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
                'HWP에서 해당 표/목록을 직접 복사(Ctrl+C)하여\n'
                '텍스트 입력창에 붙여넣기 해주세요.'
            )
            self.status_var.set('HWP 읽기 실패 — 직접 복사·붙여넣기 필요')

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
        self.target_var.set(target)
        self.config.use_target(target)
        self.config.save()
        # 명단의 의미가 달라진다 (사람 ↔ 기관). 남겨 두면 헷갈리므로 비운다.
        self.names_list.clear()
        self.last_org_duplicates = []
        self.parsed_list.delete(0, 'end')
        self.parse_status.config(text='')
        self._apply_target()

    def _on_target_change(self):
        """target_var 에 들어 있는 값으로 전환한다."""
        self._choose_target(self.target_var.get())

    def _paint_target_cards(self):
        """고른 쪽을 눈에 띄게. 어느 쪽인지 헷갈리면 안 된다."""
        for target, (card, title, desc) in getattr(self, 'target_cards', {}).items():
            chosen = target == self.config.target
            bg = '#1565C0' if chosen else '#ECEFF1'
            edge = '#FFC107' if chosen else '#37474F'
            card.config(bg=bg, highlightbackground=edge, highlightcolor=edge)
            title.config(bg=bg, fg='white' if chosen else '#546E7A',
                         text=('✓  ' if chosen else '     ') + TARGET_LABELS[target])
            desc.config(bg=bg, fg='#BBDEFB' if chosen else '#90A4AE')

    def _apply_target(self):
        edufine_on = self.is_edufine()
        self._paint_target_cards()

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

        hint = getattr(self, 'target_hint', None)
        if hint:
            hint.config(text=(
                f'{TARGET_LABELS[self.config.target]} 사용 중  ·  '
                + (TARGET_SYSTEMS[TARGET_EDUFINE] + ' 공문 수신그룹'
                   if edufine_on else
                   TARGET_SYSTEMS[TARGET_MESSENGER] + ' 수신자 선택')
            ))

        title = getattr(self, 'guide_title', None)
        body = getattr(self, 'guide_body', None)
        if title and body:
            if edufine_on:
                title.config(text='📋  기관 명단을 넣으세요')
                body.config(text=(
                    '엑셀·한글에서 기관명을 복사해 아래 입력창에 붙여넣거나,\n'
                    '[엑셀 파일 열기] 로 파일을 바로 열어도 됩니다.\n'
                    '줄바꿈·쉼표·탭 아무거나 되고, 번호나 글머리기호는 알아서 뗍니다.\n'
                    '\n'
                    '예)  학성초        충북외고        청주교육지원청 행정과'
                ))
            else:
                title.config(text='📋  소속기관과 이름을 넣으세요')
                body.config(text=(
                    '엑셀·한글에서 소속기관과 이름 두 열을 복사해 아래에 붙여넣거나,\n'
                    '[엑셀 파일 열기] · [HWP 파일 열기] 로 파일을 바로 열어도 됩니다.\n'
                    '\n'
                    '예)  충주중학교    홍길동        (소속기관, 이름 순서)'
                ))

        # 좌표 안내는 소통메신저 전용이다
        intro = getattr(self, 'calib_intro', None)
        if intro:
            intro.config(text=(
                '소통메신저 [사용자 선택] 창을 열어 둔 상태에서 아래 3곳을 순서대로 설정하세요.\n'
                'STEP 1: 검색 입력창  ·  STEP 2: 결과 첫 번째 항목  ·  STEP 3: 사용자 선택 버튼\n'
                '[캡처 시작] 을 누르고 마우스를 대상 위치로 옮긴 뒤 Enter 를 누르면 '
                '확정됩니다. 소통메신저가 앞에 나와 있어도 됩니다. Esc 는 취소입니다.'
            ))
        auto_intro = getattr(self, 'auto_intro', None)
        if auto_intro:
            auto_intro.config(text=(
                '소통메신저 [사용자 선택] 창을 열고 [전체조직] 탭을 켜 두세요.\n'
                '이름마다 ① 검색 입력  ② 결과 첫 번째 클릭  ③ 선택 버튼 클릭  이 반복됩니다.\n'
                '추가됐는지 확인하려고 선택 버튼을 한 번 더 누릅니다. 안내창이 뜨면 추가된 것입니다.\n'
                '⚠  마우스를 화면 왼쪽 위 모서리로 옮기면 긴급 중지됩니다.'
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

        color = 'green' if ok > 0 else 'red'
        parts = [f'명단 추출 완료: {ok}명']
        if fail:
            parts.append(f'인식실패 {fail}')
        if no_org:
            parts.append(f'소속없음 {no_org}')
            if warn_items:
                parts.append(f'({", ".join(warn_items[:5])}{"..." if len(warn_items) > 5 else ""})')
        self.parse_status.config(
            text='  /  제외: '.join(parts) if (fail or no_org) else parts[0],
            fg=color
        )
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

        parts = [f'기관 {confirmed}곳 확정']
        if pending:
            parts.append(f'확인 필요 {pending}곳 — 일괄 수정 버튼에서 확인하세요')
        if duplicates:
            parts.append(f'중복 입력 {len(duplicates)}종 제거')
        self.parse_status.config(
            text='  /  '.join(parts),
            fg='green' if pending == 0 and confirmed else ('#B71C1C' if pending else 'red')
        )
        self.status_var.set(f'기관 {confirmed}곳 확정, 확인 필요 {pending}곳')
        self._refresh_ready_status()
        self._refresh_edufine_status()

    def _clear_input(self):
        if self._block_while_running():
            return
        self.input_text.delete('1.0', 'end')
        self.parsed_list.delete(0, 'end')
        self.names_list.clear()
        self.last_org_duplicates = []
        self.parse_status.config(text='')
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

    def _after_list_edit(self):
        """목록을 손본 뒤 상태를 다시 맞춘다. 이 목록이 그대로 엑셀로 간다."""
        total = len(self.names_list)
        if self.is_edufine():
            pending = sum(1 for i in self.names_list if self._org_needs_review(i))
            parts = [f'기관 {total - pending}곳 확정']
            if pending:
                parts.append(f'확인 필요 {pending}곳 (일괄 수정 버튼에서 확인하세요)')
            self.parse_status.config(
                text='  /  '.join(parts),
                fg='green' if not pending else '#B71C1C')
        else:
            self.parse_status.config(text=f'명단 추출 완료: {total}명', fg='green')
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
        dlg.geometry('360x190')
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)

        tk.Label(dlg, text='소속기관:', font=('맑은 고딕', 10)).grid(
            row=0, column=0, padx=14, pady=(18, 6), sticky='e')
        org_var = tk.StringVar(value=item.get('org', ''))
        org_entry = tk.Entry(dlg, textvariable=org_var, font=('맑은 고딕', 10), width=22)
        org_entry.grid(row=0, column=1, padx=8, pady=(18, 6), sticky='w')

        tk.Label(dlg, text='이름:', font=('맑은 고딕', 10)).grid(
            row=1, column=0, padx=14, pady=6, sticky='e')
        name_var = tk.StringVar(value=item.get('name', ''))
        tk.Entry(dlg, textvariable=name_var, font=('맑은 고딕', 10), width=22).grid(
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
        tk.Button(btn_frame, text='저장', command=apply,
                  bg='#1565C0', fg='white', relief='flat',
                  font=('맑은 고딕', 10), padx=14, pady=4).pack(side='left', padx=6)
        tk.Button(btn_frame, text='취소', command=dlg.destroy,
                  bg='#9E9E9E', fg='white', relief='flat',
                  font=('맑은 고딕', 10), padx=14, pady=4).pack(side='left', padx=6)

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
        CaptureDialog(self.root, on_captured, label=labels.get(key, key))

    def _save_calib(self):
        self.config.data['search_delay'] = round(self.delay_var.get(), 1)
        self.config.data['manual_confirm'] = self.manual_var.get()
        self.config.data['verify_add'] = self.verify_var.get()
        self.config.save()
        self.calib_msg.config(text='✅ 설정 저장 완료')
        self.root.after(2000, lambda: self.calib_msg.config(text=''))
        self._refresh_ready_status()

    def _edit_org_item(self, idx, item):
        """에듀파인 기관 항목 고치기 — 후보에서 고르거나 직접 적는다."""
        dlg = tk.Toplevel(self.root)
        dlg.title('기관 확인')
        dlg.geometry('420x380')
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.configure(bg='#F5F7FA')

        tk.Label(dlg, text=f"입력한 값:  {item.get('raw', '')}", bg='#F5F7FA',
                 fg='#37474F', font=('맑은 고딕', 10, 'bold')).pack(pady=(16, 2))
        tk.Label(dlg, text='아래 후보에서 고르거나, 정확한 기관명을 직접 적으세요.',
                 bg='#F5F7FA', fg='#555', font=('맑은 고딕', 9)).pack(pady=(0, 8))

        box = tk.Listbox(dlg, font=('맑은 고딕', 10), height=9,
                         activestyle='none', selectbackground='#1565C0',
                         selectforeground='white')
        box.pack(fill='both', expand=True, padx=16)

        candidates = list(item.get('candidates') or [])
        if item.get('org') and item['org'] not in candidates:
            candidates.insert(0, item['org'])
        for c in candidates:
            box.insert('end', c)
        if candidates:
            box.selection_set(0)

        typed = tk.StringVar(value=item.get('org') or item.get('raw', ''))
        entry_row = tk.Frame(dlg, bg='#F5F7FA')
        entry_row.pack(fill='x', padx=16, pady=(10, 4))
        tk.Label(entry_row, text='직접 입력', bg='#F5F7FA',
                 font=('맑은 고딕', 9)).pack(side='left', padx=(0, 6))
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

        btns = tk.Frame(dlg, bg='#F5F7FA')
        btns.pack(pady=12)
        tk.Button(btns, text='확정', command=take_selected,
                  bg='#1565C0', fg='white', activebackground='#0D47A1',
                  relief='flat', font=('맑은 고딕', 9, 'bold'),
                  padx=18, pady=5, cursor='hand2').pack(side='left', padx=4)
        tk.Button(btns, text='취소', command=dlg.destroy,
                  bg='#B0BEC5', fg='white', activebackground='#90A4AE',
                  relief='flat', font=('맑은 고딕', 9),
                  padx=14, pady=5, cursor='hand2').pack(side='left', padx=4)

    def _refresh_calib_labels(self):
        for key in ('search_field', 'result_first', 'add_button'):
            x = self.config.data.get(key + '_x')
            y = self.config.data.get(key + '_y')
            lbl = getattr(self, f'lbl_{key}', None)
            if lbl:
                if x is not None and y is not None:
                    lbl.config(text=f'✓ ({x}, {y})', fg='green')
                else:
                    lbl.config(text='미설정', fg='red')
        self._refresh_ready_status()

    # ── 자동 선택 시작/중지/계속 ───────────────
    def _start(self):
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
        self.stop_flag.clear()
        self.continue_event.set()
        for item in self.names_list:
            item.pop('failure_reason', None)
        self._rebuild_parsed_list()
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.continue_btn.config(state='disabled')
        total = len(self.names_list)
        self.progress.config(maximum=total, value=0)
        self.prog_label.config(text=f'0 / {total}')
        started_at = time.strftime('%Y-%m-%d %H:%M:%S')
        self._log(f'\n{"─" * 44}\n{started_at}  자동 선택 시작  ·  총 {total}명\n\n')
        logging.info('자동 선택 시작: 총 %s명', total)
        run_items = tuple(self.names_list)
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
            f'누를 수 있습니다. [2. 위치 설정] 탭에서 세 곳을 다시 잡는 것이 '
            f'안전합니다.\n\n'
            f'그래도 지금 이대로 시작할까요?'
        )

    def _stop(self):
        if not self._automation_is_running():
            return
        self.stop_flag.set()
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

    def _retry_failed(self):
        failed = [
            {'org': item.get('org', ''), 'name': item.get('name', '')}
            for item in self.names_list
            if item.get('failure_reason')
        ]
        if not failed:
            messagebox.showinfo('알림', '다시 실행할 실패 항목이 없습니다.')
            return
        self.names_list = failed
        self._rebuild_parsed_list()
        self.parse_status.config(text=f'실패 항목 재실행 준비: {len(failed)}명', fg='green')
        self._start()

    # ── 자동화 워커 ────────────────────────────
    def _worker(self, run_items):
        ok = fail = 0
        manual = self.config.data.get('manual_confirm', False)
        total = len(run_items)
        no_result_streak = 0
        unverified_streak = 0

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
                    self._mark_failed(idx, FAIL_MANUAL_STOP)
                    break
                if found != 'new':
                    fail += 1
                    no_result_streak += 1
                    if found == 'stale':
                        self._log('—  (검색 결과가 바뀌지 않았습니다)\n')
                        self._mark_failed(idx, FAIL_SEARCH_STALE)
                    else:
                        self._log('—  (사용자 없음)\n')
                        self._mark_failed(idx, FAIL_NO_USER)
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
                        self._mark_failed(idx, FAIL_MANUAL_STOP)
                        break
                    ok += 1
                    self._log('✓\n')
                else:
                    result = self._do_select()
                    if result == 'stopped':
                        self._log('\n')
                        self._mark_failed(idx, FAIL_MANUAL_STOP)
                        break
                    if result == 'duplicate':
                        fail += 1
                        self._log('⚠  (이미 선택된 사용자)\n')
                        self._mark_failed(idx, FAIL_DUPLICATE)
                        self._update_progress(idx + 1, total)
                        continue
                    if result == 'unverified':
                        fail += 1
                        unverified_streak += 1
                        self._log('✗  (받는 사람에 추가되지 않았습니다)\n')
                        if unverified_streak == 3:
                            self._log(
                                '     연달아 추가되지 않았습니다. [위치 설정] 탭에서 '
                                '결과 첫 줄과 선택 버튼 위치를 확인해 보세요.\n')
                        self._mark_failed(idx, FAIL_NOT_ADDED)
                        self._update_progress(idx + 1, total)
                        continue
                    unverified_streak = 0
                    ok += 1
                    self._log('✓\n')
            except pyautogui.FailSafeException:
                self._log('\n⚠  긴급 중지 (화면 모서리)\n')
                self._mark_failed(idx, FAIL_MANUAL_STOP)
                self.stop_flag.set()
                break
            except Exception as e:
                fail += 1
                self._log(f'✗  ({e})\n')
                self._mark_failed(idx, failure_reason_from_error(e))

            self._update_progress(idx + 1, total)
            time.sleep(0.1)

        stopped = self.stop_flag.is_set()
        self.root.after(0, lambda: self._done(ok, fail, stopped))

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

    def _click_add_once(self) -> bool:
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
        time.sleep(0.4)
        new_hwnds = self._snapshot_dialogs() - before
        if new_hwnds and self._is_duplicate_popup(new_hwnds):
            self._close_dialogs(new_hwnds)
            return True
        if new_hwnds:
            # 무슨 안내창인지는 몰라도 열린 채로 두면 다음 클릭이 다 막힌다.
            self._close_dialogs(new_hwnds)
        return False

    def _do_select(self) -> str:
        """추가하고, 정말 추가됐는지 확인한다.

        선택 버튼을 눌렀다는 것만으로는 추가됐는지 알 수 없다. 클릭이 빗나가도
        소통메신저는 아무 말을 하지 않아서, 받는 사람에 없는 사람이 성공으로
        기록됐다.

        이미 선택된 사용자를 다시 선택하려 하면 '선택된 사용자 입니다.' 안내창이
        뜬다. 그 안내창을 추가됐다는 증거로 쓴다. 같은 자리를 한 번 더 눌러
        안내창이 뜨면 앞선 클릭이 통한 것이고, 끝까지 안내창이 없으면 추가되지
        않은 것이라 실패로 남긴다.
        """
        time.sleep(0.2)
        if self._click_add_once():
            return 'duplicate'      # 명단을 돌리기 전부터 받는 사람에 있던 사람
        if not self.config.data.get('verify_add', True):
            return 'ok'
        for _ in range(VERIFY_ADD_TRIES):
            if self.stop_flag.is_set():
                return 'stopped'
            if self._click_add_once():
                return 'ok'         # 앞선 클릭으로 추가된 것이 확인됐다
        return 'unverified'

    def _snapshot_dialogs(self) -> set:
        """현재 열려있는 #32770 다이얼로그 핸들 집합 반환."""
        try:
            import win32gui
            found = set()
            def cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                    if win32gui.GetClassName(hwnd) == '#32770':
                        found.add(hwnd)
            win32gui.EnumWindows(cb, None)
            return found
        except Exception as exc:
            logging.debug("다이얼로그 목록 확인 실패: %s", exc)
            return set()

    def _is_duplicate_popup(self, hwnds: set) -> bool:
        """새로 뜬 안내창이 이미 선택된 사용자라는 안내인가."""
        try:
            import win32gui
            for hwnd in hwnds:
                texts = [win32gui.GetWindowText(hwnd)]
                def collect(h, _):
                    t = win32gui.GetWindowText(h)
                    if t:
                        texts.append(t)
                win32gui.EnumChildWindows(hwnd, collect, None)
                if looks_like_duplicate_popup(texts):
                    return True
        except Exception as exc:
            logging.debug("안내창 확인 실패: %s", exc)
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
            f'수동 선택 대기: {name}  →  소통메신저에서 결과 클릭 → 선택 버튼 클릭 후 [계속] 버튼'
        )
        self.continue_btn.config(state='normal')

    def _done(self, ok: int, fail: int, stopped: bool = False):
        self.worker_thread = None
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.continue_btn.config(state='disabled')
        self._refresh_failed_retry_state()
        sep = '─' * 44
        result_word = '중지' if stopped else '완료'
        self._log(f'\n{sep}\n{result_word}  ✓ {ok}명   ✗ {fail}명\n')
        if stopped:
            self.status_var.set(f'중지됨  ·  성공: {ok}명, 실패: {fail}명')
            return
        if fail:
            self.status_var.set(f'완료 — 성공: {ok}명, 실패: {fail}명  ← 빨간색 항목 확인')
            messagebox.showwarning(
                '추가 실패 알림',
                f'받는 사람에 추가되지 않은 인원이 있습니다.\n\n'
                f'  ✓ 성공: {ok}명\n'
                f'  ✗ 실패: {fail}명\n\n'
                f'[1. 명단 입력] 탭에서 빨간색 항목을 확인하세요.\n'
                f'(검색 결과 없음, 이미 선택된 사용자, 추가 안 됨)'
            )
        else:
            self.status_var.set(f'완료 — 성공: {ok}명')

    def _update_progress(self, idx: int, total: int):
        self.root.after(
            0,
            lambda: (
                self.progress.config(value=idx),
                self.prog_label.config(text=f'{idx} / {total}'),
            )
        )

    def _mark_failed(self, idx: int, reason: str):
        # 파일 로그에는 개인정보를 남기지 않고 순번과 사유만 기록한다.
        logging.warning('명단 추가 실패: 순번=%s, 사유=%s', idx + 1, reason)
        def apply():
            if idx >= len(self.names_list):
                return
            self.names_list[idx]['failure_reason'] = reason
            self.parsed_list.delete(idx)
            self.parsed_list.insert(idx, self._format_item_label(self.names_list[idx]))
            self.parsed_list.itemconfig(idx, {'bg': '#FFCDD2', 'fg': '#B71C1C'})
            self._refresh_failed_retry_state()
        self.root.after(0, apply)

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

