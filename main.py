"""신통픽 — 소통메신저·에듀파인 수신자 한 번에

수신 + 소통. 명단을 읽어 충북 기관명으로 정리하는 파이프라인은 하나이고,
두 도구를 합친 것이다.

  소통픽 — 소통메신저 [사용자 선택] 창에서 수신자를 자동으로 골라 담는다
  수신픽 — 에듀파인 공문 수신그룹 일괄등록 엑셀을 만든다
"""

APP_NAME    = '신통픽'
APP_VERSION = '2.1.0'

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
    Config,
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
    failure_reason_from_error,
)
from hwp_extract import extract_hwp_text
from sotong_parser import (
    AUTO_GRADES,
    GRADE_AMBIGUOUS,
    lookup_org_graded,
    parse_input,
    parse_orgs,
)
from ui_helpers import format_item_label

LOG_FILE = os.path.join(os.path.expanduser("~"), ".chungbuk_auto.log")
LATEST_RELEASE_API = 'https://api.github.com/repos/codersongpro/susin/releases/latest'
RELEASES_PAGE = 'https://github.com/codersongpro/susin/releases/latest'
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, encoding='utf-8')

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

# ─────────────────────────────────────────────
#  CaptureDialog
# ─────────────────────────────────────────────

class CaptureDialog(tk.Toplevel):
    def __init__(self, parent, on_captured, label='위치'):
        super().__init__(parent)
        self.on_captured = on_captured
        self.title('위치 캡처')
        self.geometry('420x270')
        self.resizable(False, False)
        self.grab_set()

        tk.Label(
            self, text=f'📍  캡처 대상: {label}',
            bg='#1565C0', fg='white', font=('맑은 고딕', 12, 'bold'), pady=12
        ).pack(fill='x')

        tk.Label(
            self,
            text='[캡처 시작] 버튼을 클릭한 뒤 소통메신저의 대상 위치로\n'
                 '마우스를 이동하세요. Enter로 확정, Esc로 취소합니다.',
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
        self.focus_set()
        self._poll_position()

    def _poll_position(self):
        if not self.winfo_exists():
            return
        pos = pyautogui.position()
        self.status.config(text=f'현재 위치: ({pos.x}, {pos.y})  Enter 확정 / Esc 취소')
        self.after(120, self._poll_position)

    def _confirm(self):
        self._done(pyautogui.position())

    def _done(self, pos):
        self.status.config(text=f'✓ 캡처 완료: ({pos.x}, {pos.y})', fg='green')
        self.on_captured(pos.x, pos.y)
        self.after(1200, self.destroy)


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

    1단계: 검색 입력창에 이름 입력 → 검색
    2단계: 검색 결과 첫 번째 항목 클릭 (선택)
    3단계: [사용자 선택] 버튼 클릭 (추가 완료)

  수십~수백 명을 일일이 처리하는 반복 작업을 자동화합니다.


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
    [📍 위치 설정] 클릭 → [캡처 시작] 클릭 →
    소통메신저의 해당 위치로 마우스를 이동한 뒤 Enter 키로 확정하세요.
    잘못 눌렀다면 Esc 키로 취소할 수 있습니다.

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
    [4. 수신그룹 엑셀] 탭 → STEP 2

      등록교육청 : 본인이 속한 교육지원청을 목록에서 고릅니다
      사용자ID   : 에듀파인 로그인 ID
      사용자명   : 결재선에 뜨는 이름

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
    [4. 수신그룹 엑셀] 탭 STEP 3 에 수신그룹명을 적고
    [수신그룹 엑셀 만들기] 를 누릅니다.

    코드가 없는 기관이 있으면 목록으로 알려 줍니다. 조용히 빠지지 않습니다.
    그런 기관은 [클립보드 순차 복사] 로 조직도에 직접 넣으면 됩니다.

    만들어진 엑셀을 에듀파인
    [개인설정 > 개인수신그룹관리 > 일괄등록] 에서 올립니다.

    ※ 처음에는 기관 2~3곳짜리 시험 그룹으로 한 번 확인해 보세요.


  ⑤ 기관코드 갱신  (평소에는 필요 없음)
  ──────────────────────────────────────────────────────
    충북 770곳의 코드가 이미 들어 있습니다. STEP 1 은 건너뛰어도 됩니다.

    학교 신설·통폐합으로 갱신이 필요하면,
    에듀파인에서 수신그룹을 하나 만들어 저장한 뒤
    [파일양식받기] 를 누르면 등록한 내용이 코드와 함께 내려옵니다.
    그 파일을 STEP 1 의 [기관코드 가져오기…] 로 넣으면 됩니다.

    코드가 바뀐 기관이 있으면 무엇이 어떻게 바뀌는지 먼저 보여 줍니다.


  ⑥ 클립보드 순차 복사
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


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f'{APP_NAME}  v{APP_VERSION}')
        self.root.geometry('900x720')
        self.root.minsize(880, 700)

        self.config = Config()
        self.codes = edufine.load_codes()
        self.names_list: list = []
        self.stop_flag = threading.Event()
        self.continue_event = threading.Event()
        self.continue_event.set()

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
        self.root.rowconfigure(1, weight=1)

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

        # 탭 노트북
        nb = ttk.Notebook(self.root)
        nb.grid(row=1, column=0, sticky='nsew', padx=4, pady=(0, 4))

        self.nb = nb
        f1 = ttk.Frame(nb)
        f2 = ttk.Frame(nb)
        f3 = ttk.Frame(nb)
        f4 = ttk.Frame(nb)
        f5 = ttk.Frame(nb)

        # 고른 도구에 따라 넣고 빼므로 순서와 이름을 기억해 둔다
        self.tab_input = f1
        self.tab_help = f5
        self.messenger_tabs = [(f2, '  2. 위치 설정  '), (f3, '  3. 자동 선택  ')]
        self.edufine_tabs = [(f4, '  2. 수신그룹 엑셀  ')]

        # 탭 등록은 _apply_target 이 한다. 고른 도구에 따라 매번 다시 구성한다.

        self._tab_input(f1)
        self._tab_calib(f2)
        self._tab_auto(f3)
        self._tab_edufine(f4)
        self._tab_help(f5)
        self._apply_target()

        # 상태바
        self.status_var = tk.StringVar(value='준비')
        tk.Label(
            self.root, textvariable=self.status_var,
            relief='sunken', anchor='w', bg='#f0f0f0', fg='#333',
            font=('맑은 고딕', 9), pady=3
        ).grid(row=2, column=0, sticky='ew')
        self._refresh_ready_status()

    # ── 탭 1: 명단 입력 ────────────────────────
    def _tab_input(self, frame: ttk.Frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(6, weight=2)

        # ⓪ 어느 도구를 쓸지 — 가장 먼저 정해야 하는 것이라 크게 둔다
        picker = tk.Frame(frame, bg='#263238')
        picker.grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 0))
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
        self.target_hint.grid(row=2, column=0, columnspan=2, sticky='w',
                              padx=14, pady=(0, 10))

        # ① 입력 형식 안내 박스
        guide = tk.Frame(frame, bg='#E3F2FD', bd=1, relief='solid')
        guide.grid(row=1, column=0, sticky='ew', padx=10, pady=(6, 4))
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
        file_btn_frame.grid(row=2, column=0, sticky='ew', padx=8, pady=(0, 2))

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
        self.input_text.grid(row=3, column=0, sticky='nsew', padx=8, pady=4)

        # ④ 추출 버튼 행
        action_frame = tk.Frame(frame, bg='#F5F7FA')
        action_frame.grid(row=4, column=0, sticky='ew', padx=8, pady=(0, 4))

        for text, cmd, bg in [
            ('명단 추출 →', self._parse,       '#1565C0'),
            ('초기화',       self._clear_input, '#E53935'),
        ]:
            tk.Button(
                action_frame, text=text, command=cmd,
                bg=bg, fg='white', activebackground=bg,
                relief='flat', font=('맑은 고딕', 9, 'bold'), padx=12, pady=5, cursor='hand2'
            ).pack(side='left', padx=3)

        # 아래 둘은 수신픽에서만 쓴다. _apply_target 이 보이고 감춘다.
        # 부서는 전체경로를 외울 수 없으니 목록에서 고르게 한다
        self.browse_btn = tk.Button(
            action_frame, text='기관 찾아보기…', command=self._open_org_picker,
            bg='#00695C', fg='white', activebackground='#004D40',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=12, pady=5, cursor='hand2')

        # 목록을 고친 그대로 엑셀까지 간다. 탭을 옮겨 다닐 필요가 없다.
        self.make_excel_btn = tk.Button(
            action_frame, text='수신그룹 엑셀 만들기 →', command=self._build_group_excel,
            bg='#1565C0', fg='white', activebackground='#0D47A1',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=14, pady=5, cursor='hand2')

        # ⑤ 추출 결과 상태 라벨
        self.parse_status = tk.Label(
            frame, text='', fg='#555', font=('맑은 고딕', 9), anchor='w'
        )
        self.parse_status.grid(row=5, column=0, sticky='w', padx=12, pady=(0, 2))

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

        # ① 기관코드 사전
        code_frame = ttk.LabelFrame(frame, text='STEP 1 — 기관코드 사전')
        code_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=4)
        code_frame.columnconfigure(0, weight=1)

        self.codes_status = tk.Label(
            code_frame, text='', anchor='w', justify='left',
            font=('맑은 고딕', 9), bg='#F5F7FA'
        )
        self.codes_status.grid(row=0, column=0, sticky='ew', padx=8, pady=(6, 2))

        tk.Label(
            code_frame,
            text='에듀파인에서 수신그룹을 하나 만든 뒤 [파일양식받기] 로 내려받은 엑셀을 고르세요.\n'
                 '그 파일에 기관코드가 들어 있습니다. 한 번 가져오면 계속 쓰입니다.',
            fg='#555', font=('맑은 고딕', 8), justify='left', anchor='w', bg='#F5F7FA'
        ).grid(row=1, column=0, sticky='w', padx=8, pady=(0, 4))

        tk.Button(
            code_frame, text='기관코드 가져오기…', command=self._import_codes,
            bg='#00695C', fg='white', activebackground='#004D40',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=12, pady=5, cursor='hand2'
        ).grid(row=2, column=0, sticky='w', padx=8, pady=(0, 8))

        # ② 내 정보 — 매번 같은 값이라 한 번만 넣는다
        me_frame = ttk.LabelFrame(frame, text='STEP 2 — 내 정보 (한 번만 입력)')
        me_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=4)
        me_frame.columnconfigure(1, weight=1)
        me_frame.columnconfigure(3, weight=1)

        self.edufine_vars = {}

        # 등록교육청은 코드를 외울 수 없으니 목록에서 고르게 한다
        tk.Label(me_frame, text='등록교육청', bg='#F5F7FA',
                 font=('맑은 고딕', 9)).grid(row=0, column=0, sticky='w', padx=(8, 4), pady=5)
        self.edufine_vars['등록교육청코드'] = tk.StringVar(
            value=self.config.edufine.get('등록교육청코드', ''))
        self.office_var = tk.StringVar()
        self.office_combo = ttk.Combobox(me_frame, textvariable=self.office_var,
                                         state='readonly', width=24)
        self.office_combo.grid(row=0, column=1, sticky='ew', padx=(0, 10), pady=5)
        self.office_combo.bind('<<ComboboxSelected>>', self._on_office_selected)
        self._reload_office_choices()

        for key, r, c in [('사용자ID', 0, 2), ('사용자명', 1, 0)]:
            tk.Label(me_frame, text=key, bg='#F5F7FA',
                     font=('맑은 고딕', 9)).grid(row=r, column=c, sticky='w', padx=(8, 4), pady=5)
            var = tk.StringVar(value=self.config.edufine.get(key, ''))
            self.edufine_vars[key] = var
            entry = ttk.Entry(me_frame, textvariable=var, width=20)
            entry.grid(row=r, column=c + 1, sticky='ew', padx=(0, 10), pady=5)
            entry.bind('<FocusOut>', lambda e: self._save_edufine_fields())

        self.office_code_label = tk.Label(
            me_frame, text='', fg='#555', font=('맑은 고딕', 8), bg='#F5F7FA', anchor='w')
        self.office_code_label.grid(row=1, column=2, columnspan=2, sticky='w',
                                    padx=8, pady=(0, 4))

        tk.Label(
            me_frame,
            text='등록교육청은 본인이 속한 교육지원청입니다. 사용자ID·이름은 [파일양식받기] 파일에서도 채워집니다.',
            fg='#555', font=('맑은 고딕', 8), bg='#F5F7FA', anchor='w'
        ).grid(row=2, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 6))

        # ③ 그룹 만들기
        group_frame = ttk.LabelFrame(frame, text='STEP 3 — 수신그룹 만들기')
        group_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=4)
        group_frame.columnconfigure(1, weight=1)
        group_frame.columnconfigure(3, weight=1)

        for key, c, hint in [('그룹명', 0, '예: 2026 도내 교육지원청'), ('그룹기호', 2, '비워도 됩니다')]:
            tk.Label(group_frame, text=key, bg='#F5F7FA',
                     font=('맑은 고딕', 9)).grid(row=0, column=c, sticky='w', padx=(8, 4), pady=6)
            var = tk.StringVar(value=self.config.edufine.get(key, ''))
            self.edufine_vars[key] = var
            ttk.Entry(group_frame, textvariable=var, width=20).grid(
                row=0, column=c + 1, sticky='ew', padx=(0, 10), pady=6)

        btn_row = tk.Frame(group_frame, bg='#F5F7FA')
        btn_row.grid(row=1, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 8))

        tk.Button(
            btn_row, text='수신그룹 엑셀 만들기', command=self._build_group_excel,
            bg='#1565C0', fg='white', activebackground='#0D47A1',
            relief='flat', font=('맑은 고딕', 9, 'bold'), padx=14, pady=6, cursor='hand2'
        ).pack(side='left')

        tk.Button(
            btn_row, text='클립보드 순차 복사', command=self._open_clipboard_walker,
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
        sample_row.grid(row=2, column=0, columnspan=4, sticky='w', padx=8, pady=(0, 8))
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
        """기관 찾아보기 — 부서까지 목록에서 골라 명단에 넣는다.

        '충청북도청주교육지원청 행정과' 같은 전체경로를 외울 수는 없다.
        """
        if not self.codes.get('기관'):
            messagebox.showwarning(
                '기관코드가 없습니다',
                '[4. 수신그룹 엑셀] 탭에서 기관코드를 먼저 가져오세요.')
            return

        dlg = tk.Toplevel(self.root)
        dlg.title('기관 찾아보기')
        dlg.geometry('620x520')
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

        count_label = tk.Label(dlg, text='', bg='#F5F7FA', fg='#555',
                               font=('맑은 고딕', 8), anchor='w')
        count_label.pack(fill='x', padx=16, pady=(4, 2))

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
            shown = edufine.search_orgs(self.codes, query.get())
            box.delete(0, 'end')
            for full in shown:
                box.insert('end', full)
            total = len(self.codes.get('기관', {}))
            count_label.config(text=f'{len(shown)}곳 표시  /  전체 {total}곳')

        def add_selected():
            picked = [shown[i] for i in box.curselection()]
            if not picked:
                return
            existing = {i.get('org') for i in self.names_list}
            index = edufine.index_by_short_name(self.codes)
            added = 0
            for full in picked:
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
            self._refresh_ready_status()
            self._refresh_edufine_status()
            self.parse_status.config(
                text=f'찾아보기에서 {added}곳 추가  (명단 {len(self.names_list)}곳)',
                fg='green')
            count_label.config(text=f'{added}곳을 명단에 넣었습니다.')

        query.trace_add('write', refresh)
        box.bind('<Double-Button-1>', lambda e: add_selected())
        entry.bind('<Return>', lambda e: box.focus_set())

        btns = tk.Frame(dlg, bg='#F5F7FA')
        btns.pack(pady=12)
        tk.Button(btns, text='명단에 추가', command=add_selected,
                  bg='#1565C0', fg='white', activebackground='#0D47A1',
                  relief='flat', font=('맑은 고딕', 9, 'bold'),
                  padx=18, pady=6, cursor='hand2').pack(side='left', padx=4)
        tk.Button(btns, text='닫기', command=dlg.destroy,
                  bg='#B0BEC5', fg='white', activebackground='#90A4AE',
                  relief='flat', font=('맑은 고딕', 9),
                  padx=14, pady=6, cursor='hand2').pack(side='left', padx=4)

        refresh()

    def _reload_office_choices(self):
        """등록교육청 목록을 코드 사전에서 다시 읽는다."""
        combo = getattr(self, 'office_combo', None)
        if not combo:
            return
        self.office_choices = edufine.registering_offices(self.codes)
        combo['values'] = [name for name, _ in self.office_choices]

        current = self.edufine_vars['등록교육청코드'].get().strip()
        for name, code in self.office_choices:
            if code == current:
                self.office_var.set(name)
                break
        else:
            self.office_var.set('')
        self._refresh_office_code_label()

    def _refresh_office_code_label(self):
        label = getattr(self, 'office_code_label', None)
        if not label:
            return
        code = self.edufine_vars['등록교육청코드'].get().strip()
        label.config(text=f'코드 {code}' if code else '교육지원청을 골라주세요')

    def _on_office_selected(self, event=None):
        picked = self.office_var.get()
        for name, code in getattr(self, 'office_choices', []):
            if name == picked:
                self.edufine_vars['등록교육청코드'].set(code)
                break
        self._save_edufine_fields()
        self._refresh_office_code_label()

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
        self.config.save()
        self._refresh_edufine_status()

    def _refresh_edufine_status(self):
        label = getattr(self, 'codes_status', None)
        if not label:
            return
        orgs = self.codes.get('기관', {})
        collected = self.codes.get('수집일') or '-'
        if orgs:
            label.config(text=f'기관코드 {len(orgs)}곳 보유  ·  수집일 {collected}',
                         fg='#1B5E20')
        else:
            label.config(text='기관코드가 아직 없습니다 — 아래에서 먼저 가져오세요',
                         fg='#C62828')

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

    def _import_codes(self):
        path = filedialog.askopenfilename(
            title='에듀파인에서 받은 수신그룹 엑셀을 고르세요',
            filetypes=[('엑셀 파일', '*.xlsx'), ('모든 파일', '*.*')]
        )
        if not path:
            return
        try:
            harvested = edufine.read_group_workbook(path)
        except Exception as exc:
            logging.exception('기관코드 가져오기 실패')
            messagebox.showerror('가져오기 실패', f'파일을 읽지 못했습니다.\n\n{exc}')
            return

        if not harvested['기관']:
            messagebox.showwarning(
                '가져올 코드가 없습니다',
                '이 파일에는 기관코드가 들어 있지 않습니다.\n\n'
                '에듀파인에서 수신그룹을 먼저 저장한 뒤 [파일양식받기] 를 누르면\n'
                '등록한 기관이 코드와 함께 내려옵니다.')
            return

        codes, added, changed = edufine.merge_codes(self.codes, harvested)
        if changed:
            lines = '\n'.join(f'· {n}: {old} → {new}' for n, old, new in changed[:10])
            more = f'\n… 외 {len(changed) - 10}곳' if len(changed) > 10 else ''
            if not messagebox.askyesno(
                    '코드가 바뀐 기관이 있습니다',
                    f'{len(changed)}곳의 코드가 기존과 다릅니다. 새 값으로 바꿀까요?\n\n'
                    f'{lines}{more}'):
                return

        self.codes = codes
        edufine.save_codes(self.codes)
        self._reload_office_choices()

        # 이미 채워 둔 값은 건드리지 않는다. 조직도를 통째로 내보낸 파일에는
        # 본인 것이 아닌 등록교육청코드가 들어 있을 수 있다.
        for key, value in (('등록교육청코드', harvested.get('등록교육청코드')),
                           ('사용자ID', harvested.get('사용자ID')),
                           ('사용자명', harvested.get('사용자명'))):
            if value and key in self.edufine_vars and not self.edufine_vars[key].get().strip():
                self.edufine_vars[key].set(value)
        self._save_edufine_fields()
        self._reload_office_choices()

        messagebox.showinfo(
            '가져오기 완료',
            f'기관코드 {len(self.codes["기관"])}곳을 보유하게 되었습니다.\n'
            f'(새로 추가 {added}곳, 코드 변경 {len(changed)}곳)')

    def _build_group_excel(self):
        self._save_edufine_fields()

        if not self.codes.get('기관'):
            messagebox.showwarning(
                '기관코드가 없습니다',
                'STEP 1 에서 기관코드를 먼저 가져오세요.')
            return
        if not self.config.edufine_ready():
            messagebox.showwarning(
                '내 정보가 비었습니다',
                'STEP 2 의 등록교육청코드·사용자ID·사용자명을 채워주세요.')
            return

        group_name = self.config.edufine.get('그룹명', '').strip()
        if not group_name:
            messagebox.showwarning('그룹명이 필요합니다', 'STEP 3 에 수신그룹명을 적어주세요.')
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
                    '이 기관들은 [클립보드 순차 복사] 로 조직도에 직접 넣으면 됩니다.'):
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
        items = [i['org'] for i in self._confirmed_orgs()]
        if not items:
            leftovers = [i.get('raw', '') for i in self.names_list if i.get('raw')]
            items = [x for x in leftovers if x]
        if not items:
            messagebox.showinfo('명단이 비었습니다', '먼저 [명단 입력] 탭에서 기관을 추출하세요.')
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

    # ── 탭 4: 사용 방법 ────────────────────────
    def _tab_help(self, frame: ttk.Frame):
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        tk.Button(
            frame,
            text='▶  영상으로 사용 방법 보기 (YouTube)',
            bg='#FF0000', fg='white', activebackground='#CC0000',
            relief='flat', font=('맑은 고딕', 10, 'bold'), padx=10, pady=6,
            cursor='hand2',
            command=lambda: webbrowser.open('https://youtu.be/shZnB5NRN5g')
        ).grid(row=0, column=0, pady=(10, 4))

        txt = scrolledtext.ScrolledText(
            frame, font=('맑은 고딕', 10), wrap='word', state='normal'
        )
        txt.grid(row=1, column=0, sticky='nsew', padx=4, pady=4)
        txt.insert('1.0', _HELP_TEXT)
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
            delay = self.config.data.get('search_delay', 0.5)
            label.config(
                text=f'{where}  |  명단 {count}명  ·  위치 {positions}  ·  '
                     f'수동 확인 {manual}  ·  대기 {delay}초'
            )

    def _refresh_failed_retry_state(self):
        btn = getattr(self, 'retry_failed_btn', None)
        if not btn:
            return
        has_failed = any(item.get('failure_reason') for item in self.names_list)
        btn.config(state='normal' if has_failed else 'disabled')

    def _rebuild_parsed_list(self):
        self.parsed_list.delete(0, 'end')
        for item in self.names_list:
            self.parsed_list.insert('end', self._format_item_label(item))
            if item.get('failure_reason'):
                self.parsed_list.itemconfig('end', {'bg': '#FFCDD2', 'fg': '#B71C1C'})
            elif not item.get('org'):
                self.parsed_list.itemconfig('end', {'bg': '#E0E0E0', 'fg': '#757575'})
        self._refresh_ready_status()
        self._refresh_failed_retry_state()

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

    def _choose_target(self, target: str):
        if target == self.config.target:
            return
        self.target_var.set(target)
        self.config.use_target(target)
        self.config.save()
        # 명단의 의미가 달라진다 (사람 ↔ 기관). 남겨 두면 헷갈리므로 비운다.
        self.names_list.clear()
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
        order += [(self.tab_help, '  📖 사용 방법  ')]

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

        for name in ('browse_btn', 'make_excel_btn'):
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
                '[캡처 시작] 후 마우스를 대상 위치로 옮기고 Enter로 확정합니다. Esc로 취소합니다.'
            ))
        auto_intro = getattr(self, 'auto_intro', None)
        if auto_intro:
            auto_intro.config(text=(
                '소통메신저 [사용자 선택] 창을 열고 [전체조직] 탭을 켜 두세요.\n'
                '이름마다 ① 검색 입력  ② 결과 첫 번째 클릭  ③ 선택 버튼 클릭  이 반복됩니다.\n'
                '⚠  마우스를 화면 왼쪽 위 모서리로 옮기면 긴급 중지됩니다.'
            ))

        self._refresh_calib_labels()
        self._refresh_ready_status()
        self._refresh_edufine_status()

    def _parse(self):
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
        rows = parse_orgs(raw)

        # 2차 해석 — 코드 사전(전체경로)으로 다시 본다.
        # 부서는 org_db 만으로는 못 좁힌다. '행정과' 는 11곳이고
        # '청주교육지원청 행정과' 처럼 상위조직과 맞물려야 한 곳이 된다.
        index = edufine.index_by_short_name(self.codes)
        edufine.apply_codes(rows, self.codes, index)

        self.names_list.clear()
        self.parsed_list.delete(0, 'end')

        confirmed = pending = 0
        seen = set()
        for row in rows:
            auto = row['grade'] in AUTO_GRADES
            name = row['name'] or ''
            if auto and name:
                if name in seen:
                    continue
                seen.add(name)
            self.names_list.append({
                'org': name,
                'name': '',
                'search': edufine.display_name(self.codes, name, index) if name else row['raw'],
                'grade': row['grade'],
                'raw': row['raw'],
                'candidates': row.get('candidates', []),
            })
            if auto:
                confirmed += 1
            else:
                pending += 1
        self._rebuild_parsed_list()

        parts = [f'기관 {confirmed}곳 확정']
        if pending:
            parts.append(f'확인 필요 {pending}곳 — 더블클릭해서 고르세요')
        self.parse_status.config(
            text='  /  '.join(parts),
            fg='green' if pending == 0 and confirmed else ('#E65100' if pending else 'red')
        )
        self.status_var.set(f'기관 {confirmed}곳 확정, 확인 필요 {pending}곳')
        self._refresh_ready_status()
        self._refresh_edufine_status()

    def _clear_input(self):
        self.input_text.delete('1.0', 'end')
        self.parsed_list.delete(0, 'end')
        self.names_list.clear()
        self.parse_status.config(text='')
        self._refresh_ready_status()
        self._refresh_failed_retry_state()

    def _delete_selected(self):
        for i in reversed(self.parsed_list.curselection()):
            del self.names_list[i]
        self._rebuild_parsed_list()
        self._after_list_edit()

    def _after_list_edit(self):
        """목록을 손본 뒤 상태를 다시 맞춘다. 이 목록이 그대로 엑셀로 간다."""
        total = len(self.names_list)
        if self.is_edufine():
            pending = sum(1 for i in self.names_list
                          if i.get('grade') not in AUTO_GRADES)
            parts = [f'기관 {total - pending}곳 확정']
            if pending:
                parts.append(f'확인 필요 {pending}곳 (더블클릭해서 고르세요)')
            self.parse_status.config(
                text='  /  '.join(parts),
                fg='green' if not pending else '#E65100')
        else:
            self.parse_status.config(text=f'명단 추출 완료: {total}명', fg='green')
        self._refresh_ready_status()
        self._refresh_edufine_status()

    def _edit_item(self, event=None):
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
            name, grade = lookup_org_graded(value)
            resolved = name or value
            item['org'] = resolved
            item['search'] = resolved
            item['grade'] = 'exact'      # 사람이 직접 고른 값이므로 확정으로 본다
            item['candidates'] = []
            item.pop('failure_reason', None)
            self._rebuild_parsed_list()
            self._after_list_edit()
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
        self._log_clear()
        self._log(f'자동 선택 시작 — 총 {total}명\n\n')
        threading.Thread(target=self._worker, daemon=True).start()

    def _stop(self):
        self.stop_flag.set()
        self.continue_event.set()
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.continue_btn.config(state='disabled')
        self._log('\n⏹  중지\n')

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
    def _worker(self):
        ok = fail = 0
        manual = self.config.data.get('manual_confirm', False)
        total = len(self.names_list)

        for idx, item in enumerate(self.names_list):
            if self.stop_flag.is_set():
                break
            org = item.get('org', '')
            name = item.get('name', '')
            # 에듀파인 항목은 기관명 하나로 검색한다 (사람 이름이 없다)
            search_str = item.get('search') or ((org + '+' + name) if org else name)
            prefix = f'[{idx + 1}/{total}]  '

            self._log(f'{prefix}{search_str}  ... ')
            try:
                self._do_search(search_str)
                time.sleep(self.config.data.get('search_delay', 0.5))

                if not self._has_result():
                    fail += 1
                    self._log('—  (사용자 없음)\n')
                    self._mark_failed(idx, FAIL_NO_USER)
                    self._update_progress(idx + 1, total)
                    continue

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
                    if result == 'duplicate':
                        fail += 1
                        self._log('⚠  (이미 선택된 사용자)\n')
                        self._mark_failed(idx, FAIL_DUPLICATE)
                        self._update_progress(idx + 1, total)
                        continue
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

        self.root.after(0, lambda: self._done(ok, fail))

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

    def _do_select(self) -> str:
        """3단계: 결과 클릭 → 선택 버튼 클릭 → 팝업 감지"""
        rx = self.config.data['result_first_x']
        ry = self.config.data['result_first_y']
        ax = self.config.data['add_button_x']
        ay = self.config.data['add_button_y']
        if None in (rx, ry, ax, ay):
            raise RuntimeError('좌표 오류: 결과 또는 선택 버튼 위치 미설정')
        time.sleep(0.2)
        pyautogui.click(rx, ry)
        time.sleep(0.15)
        before = self._snapshot_dialogs()
        pyautogui.click(ax, ay)
        time.sleep(0.4)
        new_hwnds = self._snapshot_dialogs() - before
        if new_hwnds and self._is_duplicate_popup(new_hwnds):
            pyautogui.press('enter')
            time.sleep(0.15)
            return 'duplicate'
        return 'ok'

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
        """새 다이얼로그의 텍스트에 '이미'가 포함되면 중복 팝업으로 판정."""
        try:
            import win32gui
            for hwnd in hwnds:
                texts = [win32gui.GetWindowText(hwnd)]
                def collect(h, _):
                    t = win32gui.GetWindowText(h)
                    if t:
                        texts.append(t)
                win32gui.EnumChildWindows(hwnd, collect, None)
                if any('이미' in t for t in texts):
                    return True
        except Exception as exc:
            logging.debug("중복 팝업 확인 실패: %s", exc)
        return False

    def _has_result(self) -> bool:
        """검색 결과 첫 항목 위치의 픽셀 밝기로 결과 유무 자동 판단."""
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

    def _show_continue(self, name: str):
        name = name or ''
        self.status_var.set(
            f'수동 선택 대기: {name}  →  소통메신저에서 결과 클릭 → 선택 버튼 클릭 후 [계속] 버튼'
        )
        self.continue_btn.config(state='normal')

    def _done(self, ok: int, fail: int):
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.continue_btn.config(state='disabled')
        self._refresh_failed_retry_state()
        sep = '─' * 44
        self._log(f'\n{sep}\n완료  ✓ {ok}명   ✗ {fail}명\n')
        if fail:
            self.status_var.set(f'완료 — 성공: {ok}명, 실패: {fail}명  ← 빨간색 항목 확인')
            messagebox.showwarning(
                '추가 실패 알림',
                f'받는 사람에 추가되지 않은 인원이 있습니다.\n\n'
                f'  ✓ 성공: {ok}명\n'
                f'  ✗ 실패: {fail}명\n\n'
                f'[1. 명단 입력] 탭에서 빨간색 항목을 확인하세요.\n'
                f'(검색 결과 없음 또는 이미 선택된 사용자)'
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

