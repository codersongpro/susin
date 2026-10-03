"""약관, 라이선스 페이지와 오픈소스 고지를 만든다.

손으로 쓰는 것은 LICENSE 와 아래 TERMS_BODY 이고, 나머지는 여기서 만든다.

  - THIRD_PARTY_NOTICES.md  저장소와 exe 에 같이 들어가는 오픈소스 고지문
  - license.html            LICENSE 전문 + 오픈소스 고지
  - terms.html              이용약관

두 페이지의 색과 틀은 index.html 의 /*SHARED:START*/ 와 /*SHARED:END*/ 사이를 그대로 가져온다.
사용 라이브러리를 바꾸면 COMPONENTS 를 고치고 이 스크립트를 돌린다.

    python3 tools/build_notices.py           # 어긋난 곳이 있는지만 본다
    python3 tools/build_notices.py --apply   # 파일을 다시 쓴다
"""
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_DIR = os.path.join(ROOT, 'licenses')
NOTICE_PATH = os.path.join(ROOT, 'THIRD_PARTY_NOTICES.md')
HTML_PATH = os.path.join(ROOT, 'index.html')
LICENSE_PATH = os.path.join(ROOT, 'LICENSE')
PAGES = {'license.html': 'build_license_page', 'terms.html': 'build_terms_page'}
SHARED_START, SHARED_END = '/*SHARED:START*/', '/*SHARED:END*/'

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

# 파일은 licenses/ 안의 이름이다. 글꼴은 앱이 쓰는 파일 옆의 원문을 그대로 쓴다.
FONT_LICENSE = os.path.join('assets', 'fonts', 'LICENSE.txt')

PYTHON_NOTICE = """\
Python is licensed under the PSF License Agreement.
Copyright (c) 2001 Python Software Foundation; All Rights Reserved.

전문: https://docs.python.org/3/license.html
"""

PYINSTALLER_NOTICE = """\
PyInstaller (https://pyinstaller.org).
GPL-2.0 or later, with a special exception that allows the programs it builds
to be distributed under any license.

실행 파일을 만드는 도구입니다. 만들어진 실행 파일에는 PyInstaller 의 부트로더가
들어가며, 위 예외 조항에 따라 신통픽에는 GPL 이 적용되지 않습니다.

  - 라이선스 전문: licenses/PyInstaller-COPYING-full.txt
"""

# (이름, 주소, 쓰임, 라이선스 표기, 원문 파일 또는 직접 쓴 글)
COMPONENTS = [
    ('Pretendard', 'https://github.com/orioncactus/pretendard', '앱 화면과 이 페이지의 글꼴',
     'SIL Open Font License 1.1', ('path', FONT_LICENSE)),
    ('Python', 'https://docs.python.org/3/license.html', '프로그램을 돌리는 바탕',
     'PSF License', ('text', PYTHON_NOTICE)),
    ('Tcl/Tk (tkinter)', 'https://www.tcl.tk/software/tcltk/license.html', '앱 화면을 그리는 부분',
     'Tcl/Tk License (BSD 계열)', ('file', 'Tcl-Tk.txt')),
    ('PyAutoGUI', 'https://github.com/asweigart/pyautogui', '마우스와 키보드를 대신 움직임',
     'BSD 3-Clause', ('file', 'PyAutoGUI.txt')),
    ('PyMsgBox', 'https://github.com/asweigart/pymsgbox', 'PyAutoGUI 가 함께 쓰는 부품',
     'BSD 3-Clause', ('file', 'PyMsgBox.txt')),
    ('PyGetWindow', 'https://github.com/asweigart/PyGetWindow', 'PyAutoGUI 가 함께 쓰는 부품',
     'BSD 3-Clause', ('file', 'PyGetWindow.txt')),
    ('PyRect', 'https://github.com/asweigart/pyrect', 'PyAutoGUI 가 함께 쓰는 부품',
     'BSD 3-Clause', ('file', 'PyRect.txt')),
    ('PyScreeze', 'https://github.com/asweigart/pyscreeze', 'PyAutoGUI 가 함께 쓰는 부품',
     'BSD 3-Clause', ('file', 'PyScreeze.txt')),
    ('PyTweening', 'https://github.com/asweigart/pytweening', 'PyAutoGUI 가 함께 쓰는 부품',
     'BSD 3-Clause', ('file', 'PyTweening.txt')),
    ('Pyperclip', 'https://github.com/asweigart/pyperclip', '클립보드 복사',
     'BSD 3-Clause', ('file', 'Pyperclip.txt')),
    ('openpyxl', 'https://openpyxl.readthedocs.io', '엑셀 파일 읽기와 쓰기',
     'MIT', ('file', 'openpyxl.txt')),
    ('et-xmlfile', 'https://foss.heptapod.net/openpyxl/et_xmlfile', 'openpyxl 이 함께 쓰는 부품',
     'MIT', ('file', 'et-xmlfile.txt')),
    ('Pillow', 'https://python-pillow.org', '유리 같은 바탕과 화면 이미지',
     'MIT-CMU (HPND)', ('file', 'Pillow.txt')),
    ('pywin32', 'https://github.com/mhammond/pywin32', '윈도우 기능 호출',
     'BSD 3-Clause', ('file', 'pywin32.txt')),
    ('comtypes', 'https://github.com/enthought/comtypes', '소통메신저 목록 읽기',
     'MIT', ('file', 'comtypes.txt')),
    ('olefile', 'https://github.com/decalage2/olefile', '한글(HWP) 파일 읽기',
     'BSD 2-Clause', ('file', 'olefile.txt')),
    ('PyInstaller', 'https://pyinstaller.org', 'exe 파일로 묶는 도구 (부트로더가 exe 에 들어감)',
     'GPL-2.0 이상, 만든 파일에는 제한이 없는 예외 조항', ('text', PYINSTALLER_NOTICE)),
]


def read_text(path: str) -> str:
    with open(path, encoding='utf-8') as source:
        return source.read().replace('\r\n', '\n').strip('\n') + '\n'


def license_text(source) -> str:
    kind, value = source
    if kind == 'text':
        return value.strip('\n') + '\n'
    if kind == 'path':
        return read_text(os.path.join(ROOT, value))
    return read_text(os.path.join(LICENSE_DIR, value))


def build_markdown() -> str:
    lines = [
        '# 오픈소스 고지',
        '',
        '신통픽(sintongpick)은 아래 소프트웨어와 글꼴을 쓰거나 함께 묶어 배포합니다.',
        '각 라이선스가 요구하는 저작권 표시와 사용 조건을 여기에 모았습니다.',
        '이 파일은 `python3 tools/build_notices.py --apply` 로 만들며, 손으로 고치지 않습니다.',
        '',
        '신통픽 자체의 사용 조건은 `LICENSE` (신통픽 사용 허가서) 에 있습니다.',
        '',
        '| 이름 | 쓰임 | 라이선스 |',
        '|---|---|---|',
    ]
    for name, url, use, kind, _source in COMPONENTS:
        lines.append(f'| [{name}]({url}) | {use} | {kind} |')
    for name, url, _use, kind, source in COMPONENTS:
        lines += ['', '---', '', f'## {name}', '', f'{kind}  ', url, '', '```text',
                  license_text(source).rstrip('\n'), '```']
    return '\n'.join(lines) + '\n'




# ── 페이지 ──────────────────────────────────────────────

PAGE_CSS = """
    .page-title { font-size: 40px; font-weight: 700; letter-spacing: -.02em; line-height: 1.2; margin-bottom: 10px; }
    .doc { padding: 40px 48px; }
    .doc h2 { font-size: 22px; font-weight: 700; margin: 36px 0 8px; }
    .doc h2:first-of-type { margin-top: 8px; }
    .doc h3 { font-size: 16px; font-weight: 700; margin: 22px 0 4px; }
    .doc p, .doc li { font-size: 15px; color: var(--ink-2); line-height: 1.85; max-width: 780px; }
    .doc ol { margin: 4px 0 0 22px; }
    .doc li + li { margin-top: 4px; }
    .doc code { font-size: 13px; background: rgba(0, 0, 0, .05); padding: 1px 6px; border-radius: 6px; }
    .doc .meta { font-size: 13px; }
    .toc { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
    .toc a { padding: 6px 14px; border-radius: 14px; font-size: 14px; font-weight: 500; text-decoration: none;
             background: var(--acc-c); color: var(--on-acc-c); }
    .plain {
      margin-top: 14px; padding: 22px 24px; border-radius: 16px; background: rgba(255, 255, 255, .6);
      border: 1px solid var(--line); white-space: pre-wrap; overflow-wrap: anywhere;
      font: 15px/1.85 'Pretendard Variable', Pretendard, 'Malgun Gothic', sans-serif; color: var(--ink);
    }
    .oss-head, .oss-item summary {
      display: grid; grid-template-columns: minmax(130px, 1fr) 1.6fr 1.3fr 22px; gap: 6px 20px;
      align-items: center; font-size: 14px; line-height: 1.6;
    }
    .oss-head { margin-top: 14px; padding: 0 0 8px; font-size: 12px; font-weight: 700; color: var(--ink-2); }
    .oss-item { border-top: 1px solid var(--line); }
    .oss-item summary { padding: 11px 0; cursor: pointer; list-style: none; }
    .oss-item summary::-webkit-details-marker { display: none; }
    .oss-item summary::after { content: '+'; color: var(--acc); font-size: 22px; line-height: 1; }
    .oss-item[open] summary::after { content: '\\2212'; }
    .oss-item summary .n { font-weight: 700; }
    .oss-item summary .u { color: var(--ink-2); }
    .oss-item summary .l { font-weight: 600; }
    .oss-item summary:hover .n { text-decoration: underline; }
    .oss-item .oss-link { margin: 0 0 8px; font-size: 13px; }
    .oss-item pre {
      margin: 0 0 14px; padding: 14px 16px; border-radius: 12px; background: rgba(255, 255, 255, .65);
      border: 1px solid var(--line); font: 12px/1.6 ui-monospace, Consolas, 'Courier New', monospace;
      color: var(--ink-2); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 320px; overflow: auto;
    }
    footer { max-width: 1120px; margin: 0 auto 24px; padding: 0 12px; }
    .foot { height: 48px; border-radius: 20px; display: flex; align-items: center; justify-content: center;
            gap: 8px; font-size: 13px; color: var(--ink-2); }
    .foot strong { color: var(--ink); }
    @media (max-width: 960px) { .nav-links { display: none; } nav { justify-content: space-between; } }
    @media (max-width: 640px) {
      nav { margin: 8px 8px 0; padding: 0 8px 0 18px; top: 8px; }
      main { padding: 0 8px 16px; }
      section, .doc { padding: 30px 20px; }
      .page-title { font-size: 30px; }
      .oss-head { display: none; }
      .oss-item summary { grid-template-columns: 1fr 22px; gap: 2px 12px; }
      .oss-item summary::after { grid-column: 2; grid-row: 1 / span 3; }
    }
"""

DOWNLOAD_URL = 'https://github.com/codersongpro/susin/releases/latest/download/sintongpick.exe'

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <meta name="description" content="{description}" />
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" />
  <style>
    {shared}
{page_css}  </style>
</head>
<body>

<nav class="glass">
  <a class="brand" href="index.html">신통픽<small>수신픽 + 소통픽</small></a>
  <div class="nav-links">
    <a href="index.html">처음으로</a>
    <a href="terms.html">이용약관</a>
    <a href="license.html">라이선스</a>
  </div>
  <a class="btn btn-filled btn-sm" href="{download}" download>최신 버전 내려받기</a>
</nav>

<main>
{body}
</main>

<footer>
  <div class="foot glass">
    <strong>신통픽</strong>
    <span>&nbsp;·&nbsp; Developed by 송동석(Dustin)</span>
    <span>&nbsp;·&nbsp; <a href="terms.html">이용약관</a> &nbsp;·&nbsp; <a href="license.html">라이선스</a></span>
  </div>
</footer>

</body>
</html>
"""


def shared_css() -> str:
    with open(HTML_PATH, encoding='utf-8') as source:
        page = source.read()
    start = page.index(SHARED_START) + len(SHARED_START)
    end = page.index(SHARED_END)
    return page[start:end].strip('\n').lstrip()


def render_page(title: str, description: str, body: str) -> str:
    return PAGE_TEMPLATE.format(title=title, description=description, shared=shared_css(),
                                page_css=PAGE_CSS, download=DOWNLOAD_URL, body=body)


def oss_items() -> str:
    out = []
    for name, url, use, kind, source in COMPONENTS:
        text = html.escape(license_text(source).rstrip('\n'), quote=False)
        out.append(
            '    <details class="oss-item">\n'
            '      <summary>'
            f'<span class="n">{html.escape(name)}</span>'
            f'<span class="u">{html.escape(use)}</span>'
            f'<span class="l">{html.escape(kind)}</span></summary>\n'
            f'      <p class="oss-link"><a href="{html.escape(url)}" target="_blank" rel="noopener">'
            f'{html.escape(url)}</a></p>\n'
            f'      <pre>{text}</pre>\n'
            '    </details>'
        )
    return '\n'.join(out)


def build_license_page() -> str:
    license_body = html.escape(read_text(LICENSE_PATH).rstrip('\n'), quote=False)
    body = f"""<section class="glass doc" id="license">
  <span class="label">라이선스</span>
  <h1 class="page-title">라이선스</h1>
  <p class="lead">신통픽을 쓰는 조건과, 신통픽에 함께 묶인 소프트웨어의 저작권 표시를 모았습니다.</p>
  <div class="toc"><a href="#app">신통픽 사용 허가서</a><a href="#oss">오픈소스 고지</a><a href="#data">기관 이름 자료</a></div>

  <h2 id="app">신통픽 사용 허가서</h2>
  <p>신통픽은 무료로 쓸 수 있습니다. 판매와 수정은 허락 없이 할 수 없습니다. 같은 내용이 저장소와 실행 파일에 들어 있는 <code>LICENSE</code> 파일입니다.</p>
  <div class="plain">{license_body}</div>

  <h2 id="oss">오픈소스 고지</h2>
  <p>신통픽은 아래 소프트웨어와 글꼴을 바탕으로 만들었고, 대부분은 실행 파일(sintongpick.exe)에 함께 묶여 있습니다. 이 소프트웨어들은 위 사용 허가서가 아니라 각자의 라이선스를 따릅니다. 항목을 누르면 저작권과 라이선스 전문이 나옵니다. 같은 내용이 앱과 함께 받는 <code>THIRD_PARTY_NOTICES.md</code> 에도 있습니다.</p>
  <div class="oss-head"><span>이름</span><span>쓰임</span><span>라이선스</span><span></span></div>
{oss_items()}

  <h2 id="data">기관 이름 자료</h2>
  <p>기관 이름 사전은 나이스에서 공개한 공공데이터인 학교기본정보(2026년 8월 31일 기준)와 에듀파인 조직도에 나온 기관 이름을 정리한 것입니다. 학교 이름, 학교급, 기관 이름 같은 사실 정보만 담고 있습니다.</p>
  <p>소통메신저, 에듀파인, 나이스는 각 제공 기관의 서비스이며 신통픽과는 별개입니다. 사용 방법 화면 사진에는 설명을 위해 이 서비스의 화면 일부가 나오고, 사람 이름은 모두 지어낸 예시입니다.</p>
  <p class="meta">문의: <a href="mailto:dungst.me@gmail.com">dungst.me@gmail.com</a></p>
</section>"""
    return render_page('라이선스 | 신통픽', '신통픽 사용 허가서와 함께 묶인 오픈소스의 저작권, 라이선스 전문입니다.', body)


TERMS_BODY = """<section class="glass doc" id="terms">
  <span class="label">이용약관</span>
  <h1 class="page-title">이용약관</h1>
  <p class="lead">신통픽을 쓰기 전에 알아 두실 내용입니다. 시행일은 2026년 10월 3일입니다.</p>

  <h2>제1조 목적</h2>
  <p>이 약관은 송동석(이하 제작자)이 무료로 나누는 신통픽(수신픽과 소통픽)의 이용 조건을 정합니다.</p>

  <h2>제2조 이용 대상과 환경</h2>
  <ol>
    <li>신통픽은 누구나 무료로 쓸 수 있고, 윈도우에서만 돌아갑니다.</li>
    <li>업무망 PC 에서 쓰기 전에 기관의 정보보안 담당자와 상의해 주세요. 백신 예외는 임의로 등록하지 마세요.</li>
    <li>신통픽은 개인이 만든 프로그램입니다. 충청북도교육청, 소통메신저와 에듀파인의 제공 기관이 만들거나 보증한 프로그램이 아닙니다.</li>
    <li>신통픽을 팔거나 고쳐서 나눌 수 없습니다. 자세한 조건은 <a href="license.html">신통픽 사용 허가서</a>에 있습니다.</li>
  </ol>

  <h2>제3조 프로그램이 하는 일</h2>
  <ol>
    <li>소통픽은 마우스와 키보드를 대신 움직여 소통메신저 [사용자 선택] 창에서 수신자를 담습니다.</li>
    <li>수신픽은 에듀파인 일괄등록에 올릴 엑셀 파일을 만듭니다. 파일을 올리고 공문을 보내는 일은 이용자가 직접 합니다.</li>
  </ol>

  <h2>제4조 이용자의 확인 책임</h2>
  <ol>
    <li>신통픽이 고른 수신자와 만든 엑셀은 보조 결과입니다. 쪽지나 공문을 보내기 전에 수신자가 맞는지 이용자가 직접 확인해야 합니다.</li>
    <li>같은 이름이 여럿이거나 이름이 비슷해 짐작만 한 항목은 신통픽이 확정하지 않고 이용자가 고르게 합니다. 확인하지 않고 보내서 생긴 결과의 책임은 이용자에게 있습니다.</li>
    <li>자동 선택이 도는 동안에는 마우스를 움직이지 마세요. 멈추려면 마우스를 화면 왼쪽 위 모서리로 옮기거나 [중지] 를 누릅니다.</li>
    <li>화면 해상도, 확대 배율, 소통메신저 창의 자리가 바뀌면 마우스 위치를 다시 캡처해야 합니다.</li>
  </ol>

  <h2>제5조 정보 처리</h2>
  <ol>
    <li>이용자가 넣은 명단과 기관 정보는 이용자의 PC 안에서만 다루며 제작자나 다른 곳으로 보내지 않습니다.</li>
    <li>소통픽과 수신픽에 넣은 명단은 앱을 닫으면 지워집니다.</li>
    <li>이용자의 PC 에는 설정 파일이 남습니다. 캡처한 마우스 위치, 검색 후 대기 시간, 수신픽의 사용자ID, 사용자명, 그룹명, 최근 30회의 기관 추출 기록(기관 이름)이 들어 있고, 위치는 <code>%LOCALAPPDATA%\\SintongPick</code> 폴더입니다. 같은 폴더의 작동 기록(app.log)에는 사람 이름을 남기지 않고 순번과 사유만 적습니다. 이 폴더를 지우면 모두 없어집니다.</li>
    <li>인터넷은 새 버전이 나왔는지 확인할 때만 쓰며, 이때 명단이나 이름은 보내지 않습니다.</li>
  </ol>

  <h2>제6조 보증의 한계</h2>
  <ol>
    <li>신통픽은 있는 그대로 제공합니다. 오류가 없다는 것과 모든 PC 에서 돌아간다는 것을 보증하지 않습니다.</li>
    <li>소통메신저나 에듀파인 화면이 바뀌면 신통픽이 동작하지 않거나 엉뚱한 곳을 누를 수 있습니다.</li>
    <li>마우스와 키보드를 대신 움직이는 방식 때문에 백신이 신통픽을 의심해 막을 수 있습니다.</li>
  </ol>

  <h2>제7조 책임의 한계</h2>
  <p>제작자는 신통픽을 쓰다가 생긴 손해에 대해 법이 허용하는 범위에서 책임지지 않습니다. 제작자의 고의 또는 중대한 과실로 생긴 손해는 제외합니다.</p>

  <h2>제8조 지식재산권</h2>
  <ol>
    <li>신통픽의 저작권은 제작자에게 있고, 사용 조건은 <a href="license.html">신통픽 사용 허가서</a>를 따릅니다. 판매와 수정은 제작자의 허락 없이 할 수 없습니다.</li>
    <li>신통픽에 함께 묶인 소프트웨어와 글꼴은 <a href="license.html#oss">오픈소스 고지</a>의 라이선스를 따릅니다.</li>
    <li>소통메신저, 에듀파인, 나이스 같은 이름과 화면은 각 제공 기관의 것입니다. 사용 방법 화면 사진은 설명을 위해 일부를 실은 것입니다.</li>
  </ol>

  <h2>제9조 약관의 변경</h2>
  <p>이 약관을 바꾸면 이 페이지에 바뀐 내용과 시행일을 올립니다.</p>

  <h2>제10조 문의</h2>
  <p><a href="mailto:dungst.me@gmail.com">dungst.me@gmail.com</a></p>
</section>"""


def build_terms_page() -> str:
    return render_page('이용약관 | 신통픽', '신통픽의 이용 조건, 수신자를 확인할 책임, 정보 처리, 보증과 책임의 한계입니다.',
                       TERMS_BODY)


def main(apply: bool) -> int:
    wanted = {NOTICE_PATH: build_markdown()}
    for name, builder in PAGES.items():
        wanted[os.path.join(ROOT, name)] = globals()[builder]()
    stale = []
    for path, text in wanted.items():
        try:
            with open(path, encoding='utf-8', newline='') as source:
                current = source.read()
        except OSError:
            current = ''
        if current != text:
            stale.append(path)
    if not stale:
        print('약관, 라이선스, 오픈소스 고지가 최신입니다')
        return 0
    names = ', '.join(os.path.relpath(p, ROOT) for p in stale)
    if not apply:
        print('어긋난 파일: ' + names + '  (--apply 로 다시 씁니다)')
        return 1
    for path in stale:
        with open(path, 'w', encoding='utf-8', newline='\n') as target:
            target.write(wanted[path])
    print('다시 썼습니다: ' + names)
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
