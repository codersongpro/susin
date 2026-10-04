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

PyInstaller는 실행 파일을 만드는 도구이며, 생성된 실행 파일에는 부트로더가 포함됩니다.
위 예외 조항에 따라 신통픽 자체에는 GPL 라이선스가 적용되지 않습니다.

  - 라이선스 전문: licenses/PyInstaller-COPYING-full.txt
"""

# (이름, 주소, 쓰임, 라이선스 표기, 원문 파일 또는 직접 쓴 글)
COMPONENTS = [
    ('Pretendard', 'https://github.com/orioncactus/pretendard', '앱 화면과 이 페이지의 글꼴',
     'SIL Open Font License 1.1', ('path', FONT_LICENSE)),
    ('Python', 'https://docs.python.org/3/license.html', '프로그램 실행 환경',
     'PSF License', ('text', PYTHON_NOTICE)),
    ('Tcl/Tk (tkinter)', 'https://www.tcl.tk/software/tcltk/license.html', '앱 화면 구성',
     'Tcl/Tk License (BSD 계열)', ('file', 'Tcl-Tk.txt')),
    ('PyAutoGUI', 'https://github.com/asweigart/pyautogui', '마우스·키보드 자동 조작',
     'BSD 3-Clause', ('file', 'PyAutoGUI.txt')),
    ('PyMsgBox', 'https://github.com/asweigart/pymsgbox', 'PyAutoGUI의 메시지 창 기능',
     'BSD 3-Clause', ('file', 'PyMsgBox.txt')),
    ('PyGetWindow', 'https://github.com/asweigart/PyGetWindow', 'PyAutoGUI의 창 정보 조회 기능',
     'BSD 3-Clause', ('file', 'PyGetWindow.txt')),
    ('PyRect', 'https://github.com/asweigart/pyrect', '창 위치와 크기 계산',
     'BSD 3-Clause', ('file', 'PyRect.txt')),
    ('PyScreeze', 'https://github.com/asweigart/pyscreeze', '화면 캡처와 이미지 검색',
     'BSD 3-Clause', ('file', 'PyScreeze.txt')),
    ('PyTweening', 'https://github.com/asweigart/pytweening', '마우스 이동 속도 조절',
     'BSD 3-Clause', ('file', 'PyTweening.txt')),
    ('Pyperclip', 'https://github.com/asweigart/pyperclip', '클립보드 복사',
     'BSD 3-Clause', ('file', 'Pyperclip.txt')),
    ('openpyxl', 'https://openpyxl.readthedocs.io', '엑셀 파일 읽기와 쓰기',
     'MIT', ('file', 'openpyxl.txt')),
    ('et-xmlfile', 'https://foss.heptapod.net/openpyxl/et_xmlfile', 'openpyxl의 XML 파일 작성 기능',
     'MIT', ('file', 'et-xmlfile.txt')),
    ('Pillow', 'https://python-pillow.org', '배경 효과와 화면 이미지 생성',
     'MIT-CMU (HPND)', ('file', 'Pillow.txt')),
    ('pywin32', 'https://github.com/mhammond/pywin32', '윈도우 기능 호출',
     'BSD 3-Clause', ('file', 'pywin32.txt')),
    ('comtypes', 'https://github.com/enthought/comtypes', '소통메신저 목록 읽기',
     'MIT', ('file', 'comtypes.txt')),
    ('olefile', 'https://github.com/decalage2/olefile', '한글(HWP) 파일 읽기',
     'BSD 2-Clause', ('file', 'olefile.txt')),
    ('PyInstaller', 'https://pyinstaller.org', '실행 파일 패키징 (부트로더 포함)',
     'GPL-2.0 이상 (생성한 프로그램의 배포에 관한 예외 조항 포함)', ('text', PYINSTALLER_NOTICE)),
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
        '신통픽(sintongpick)에 사용되거나 배포 파일에 포함된 소프트웨어와 글꼴의 저작권 표시 및 라이선스 안내입니다.',
        '각 구성 요소에는 해당 라이선스가 적용됩니다.',
        '이 문서는 `python3 tools/build_notices.py --apply`로 생성합니다. 수정할 때는 생성 스크립트와 원본 문서를 변경하세요.',
        '',
        '신통픽 자체의 이용 조건은 `LICENSE`(신통픽 사용 허가서)를 참고하세요.',
        '',
        '| 이름 | 용도 | 라이선스 |',
        '|---|---|---|',
    ]
    for name, url, use, kind, _source in COMPONENTS:
        lines.append(f'| [{name}]({url}) | {use} | {kind} |')
    for name, url, _use, kind, source in COMPONENTS:
        lines += ['', '---', '', f'## {name}', '', kind, '', url, '', '```text',
                  license_text(source).rstrip('\n'), '```']
    return '\n'.join(lines) + '\n'




# ── 페이지 ──────────────────────────────────────────────

PAGE_CSS = """
    .page-title { font-size: 40px; font-weight: 700; letter-spacing: -.02em; line-height: 1.2; margin-bottom: 10px; }
    .doc { max-width: 920px; margin: 16px auto 0; padding: 40px 48px; }
    .doc h2 { font-size: 22px; font-weight: 700; margin: 36px 0 8px; }
    .doc h2:first-of-type { margin-top: 8px; }
    .doc h3 { font-size: 17px; font-weight: 700; margin: 24px 0 8px; }
    .doc p, .doc li { font-size: 15px; color: var(--ink-2); line-height: 1.85; max-width: 780px; }
    .doc p + p { margin-top: 12px; }
    .doc ol { margin: 8px 0 0; padding-left: 24px; }
    .doc li + li { margin-top: 12px; }
    .doc li p + p { margin-top: 8px; }
    .doc code { font-size: 13px; background: rgba(0, 0, 0, .05); padding: 1px 6px; border-radius: 6px; }
    .doc .meta { font-size: 13px; }
    .toc { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
    .toc a { padding: 6px 14px; border-radius: 14px; font-size: 14px; font-weight: 500; text-decoration: none;
             background: var(--acc-c); color: var(--on-acc-c); }
    .plain {
      margin-top: 14px; padding: 22px 24px; border-radius: 16px; background: rgba(255, 255, 255, .6);
      border: 1px solid var(--line); overflow-wrap: anywhere;
      font: 15px/1.85 'Pretendard Variable', Pretendard, 'Malgun Gothic', sans-serif; color: var(--ink);
    }
    .plain .license-title { font-size: 17px; font-weight: 700; color: var(--ink); }
    .plain .license-clauses { list-style: none; padding-left: 0; }
    .plain .license-clauses li { padding-left: 1.5em; text-indent: -1.5em; }
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
    .oss-item summary > span { min-width: 0; overflow-wrap: anywhere; text-wrap: pretty; }
    .oss-item summary:focus-visible { outline: 2px solid var(--acc); outline-offset: 4px; }
    .oss-item summary:hover .n { text-decoration: underline; }
    .oss-item .oss-link { margin: 0 0 8px; font-size: 13px; overflow-wrap: anywhere; }
    .oss-item pre {
      margin: 0 0 14px; padding: 14px 16px; border-radius: 12px; background: rgba(255, 255, 255, .65);
      border: 1px solid var(--line); font: 12px/1.6 ui-monospace, Consolas, 'Courier New', monospace;
      color: var(--ink-2); white-space: pre-wrap; word-break: normal; overflow-wrap: anywhere; max-height: 400px; overflow: auto;
    }
    footer { max-width: 1120px; margin: 0 auto 24px; padding: 0 12px; }
    .foot { min-height: 48px; padding: 12px 16px; border-radius: 20px; display: flex; flex-wrap: wrap;
            align-items: center; justify-content: center; gap: 4px 8px; font-size: 13px; color: var(--ink-2); }
    .foot strong { color: var(--ink); }
    @media (max-width: 960px) { .nav-links { display: none; } nav { justify-content: space-between; } }
    @media (max-width: 640px) {
      nav { margin: 8px 8px 0; padding: 0 8px 0 18px; top: 8px; gap: 8px; }
      .brand { flex-shrink: 0; }
      .brand small { display: block; margin-left: 0; font-size: 10px; }
      nav .btn-sm { padding: 0 12px; font-size: 13px; }
      main { padding: 0 8px 16px; }
      section, .doc { padding: 30px 20px; }
      .page-title { font-size: 30px; }
      .plain { padding: 20px 16px; }
      .oss-head { display: none; }
      .oss-item summary { grid-template-columns: minmax(0, 1fr) 22px; gap: 4px 12px; }
      .oss-item summary > span { grid-column: 1; }
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
    <span>&nbsp;·&nbsp; 문의 <a href="mailto:dungst.me@gmail.com">dungst.me@gmail.com</a></span>
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


def render_license_body() -> str:
    """LICENSE의 내용을 유지하면서 텍스트 파일의 줄바꿈을 문단과 목록으로 바꾼다."""
    out = []
    for index, block in enumerate(re.split(r'\n\s*\n', read_text(LICENSE_PATH).strip())):
        lines = [line.strip() for line in block.splitlines()]
        if re.match(r'^\d+\. ', lines[0]):
            out.append(f'<h3>{html.escape(" ".join(lines))}</h3>')
        elif re.match(r'^[가-힣]\. ', lines[0]):
            items = []
            for line in lines:
                if re.match(r'^[가-힣]\. ', line):
                    items.append(line)
                else:
                    items[-1] += ' ' + line
            out.append('<ol class="license-clauses">\n' + '\n'.join(
                f'<li>{html.escape(item)}</li>' for item in items) + '\n</ol>')
        else:
            attr = ' class="license-title"' if index == 0 else ''
            out.append(f'<p{attr}>{html.escape(" ".join(lines))}</p>')
    return '\n'.join(out)


def build_license_page() -> str:
    license_body = render_license_body()
    body = f"""<section class="glass doc" id="license">
  <span class="label">라이선스</span>
  <h1 class="page-title">라이선스</h1>
  <p class="lead">신통픽의 이용 조건과 사용된 소프트웨어·글꼴의 저작권 및 라이선스를 안내합니다.</p>
  <div class="toc"><a href="#app">신통픽 사용 허가서</a><a href="#oss">오픈소스 고지</a><a href="#data">기관명 데이터</a></div>

  <h2 id="app">신통픽 사용 허가서</h2>
  <p>신통픽은 무료로 사용할 수 있으며, 수정하지 않은 원본은 무료로 배포할 수 있습니다. 판매와 수정에는 개발자의 사전 서면 허락이 필요합니다.</p>
  <p>아래는 저장소와 배포 파일에 포함된 <code>LICENSE</code>의 전문입니다.</p>
  <div class="plain">{license_body}</div>

  <h2 id="oss">오픈소스 고지</h2>
  <p>신통픽은 아래 소프트웨어와 글꼴을 사용하며, 대부분은 실행 파일(<code>sintongpick.exe</code>)에 포함되어 있습니다. 각 구성 요소에는 해당 라이선스가 적용됩니다.</p>
  <p>항목을 펼치면 저작권 표시와 라이선스 원문 또는 전문이 있는 위치를 확인할 수 있습니다. 같은 고지 내용은 배포 파일에 포함된 <code>THIRD_PARTY_NOTICES.md</code>에도 있습니다.</p>
  <div class="oss-head"><span>이름</span><span>용도</span><span>라이선스</span><span></span></div>
{oss_items()}

  <h2 id="data">기관명 데이터</h2>
  <p>기관명 사전은 나이스의 공개 학교기본정보(2026년 8월 31일 기준)와 에듀파인 조직도의 기관명을 바탕으로 작성했습니다. 학교명, 학교급, 기관명 등 사실 정보만 포함합니다.</p>
  <p>소통메신저, 에듀파인, 나이스는 각 제공 기관의 서비스이며 신통픽과는 별개입니다. 사용 안내에는 설명에 필요한 화면 일부만 사용했으며, 화면에 표시된 사람 이름은 모두 가상의 예시입니다.</p>
  <p class="meta">문의: <a href="mailto:dungst.me@gmail.com">dungst.me@gmail.com</a></p>
</section>"""
    return render_page('라이선스 | 신통픽', '신통픽의 사용 허가서와 사용된 소프트웨어·글꼴의 저작권 및 라이선스 안내입니다.', body)


TERMS_BODY = """<section class="glass doc" id="terms">
  <span class="label">이용약관</span>
  <h1 class="page-title">이용약관</h1>
  <p class="lead">신통픽의 이용 조건과 이용자가 확인해야 할 사항을 안내합니다.</p>
  <p class="meta">시행일은 2026년 10월 3일입니다.</p>

  <h2>제1조 목적</h2>
  <p>이 약관은 신통픽 개발자(이하 “개발자”)가 무료로 배포하는 신통픽(수신픽과 소통픽)의 이용 조건을 정합니다.</p>

  <h2>제2조 이용 대상과 환경</h2>
  <ol>
    <li>신통픽은 누구나 무료로 사용할 수 있으며, Windows에서만 실행됩니다.</li>
    <li>업무망 PC에서 사용하기 전에 소속 기관의 정보보안 담당자와 상의해 주세요. 백신 예외는 임의로 등록하지 마세요.</li>
    <li>신통픽은 개인이 개발한 프로그램입니다. 충청북도교육청 또는 소통메신저·에듀파인의 제공 기관이 개발하거나 보증하지 않습니다.</li>
    <li>개발자의 사전 서면 허락 없이 신통픽을 판매·수정하거나 수정한 프로그램을 배포할 수 없습니다. 자세한 조건은 <a href="license.html">신통픽 사용 허가서</a>를 참고하세요.</li>
  </ol>

  <h2>제3조 주요 기능</h2>
  <ol>
    <li>소통픽은 마우스와 키보드를 자동으로 조작해 소통메신저의 [사용자 선택] 창에서 수신자를 선택합니다.</li>
    <li>수신픽은 에듀파인의 수신그룹 일괄등록에 사용할 엑셀 파일을 만듭니다. 파일 등록과 공문 발송은 이용자가 직접 진행합니다.</li>
  </ol>

  <h2>제4조 이용자의 확인 책임</h2>
  <ol>
    <li>신통픽의 수신자 선택 결과와 생성한 엑셀 파일은 업무를 돕기 위한 자료입니다. 쪽지나 공문을 보내기 전에 수신자가 정확한지 이용자가 직접 확인해야 합니다.</li>
    <li>이름이 같거나 유사해 하나로 확정할 수 없는 항목은 이용자가 직접 선택해야 합니다. 수신자를 확인하지 않고 발송해 발생한 결과에 대한 책임은 이용자에게 있습니다.</li>
    <li>자동 선택이 실행되는 동안에는 마우스를 움직이지 마세요. 중단하려면 마우스를 화면 왼쪽 위 모서리로 옮기거나 [중지]를 누르세요.</li>
    <li>화면 해상도, 확대 배율 또는 소통메신저 창의 위치가 바뀌면 마우스 위치를 다시 캡처해야 합니다.</li>
  </ol>

  <h2>제5조 정보 처리</h2>
  <ol>
    <li>입력한 명단과 기관 정보는 이용자의 PC 안에서만 사용하며, 개발자나 외부로 전송하지 않습니다.</li>
    <li>소통픽과 수신픽에 입력한 명단은 앱을 종료하면 삭제됩니다.</li>
    <li>
      <p>설정 파일은 이용자의 PC에 있는 <code>%LOCALAPPDATA%\\SintongPick</code> 폴더에 저장됩니다. 캡처한 마우스 위치, 검색 후 대기 시간, 수신픽의 사용자 ID·사용자명·그룹명, 최근 30회의 기관 추출 기록(기관명)이 포함됩니다.</p>
      <p>같은 폴더의 실행 기록(<code>app.log</code>)에는 사람 이름을 기록하지 않고 순번과 사유만 남깁니다. 해당 폴더를 삭제하면 저장된 설정과 기록이 모두 삭제됩니다.</p>
    </li>
    <li>인터넷 연결은 새 버전 확인에만 사용하며, 이때 명단이나 이름은 전송하지 않습니다.</li>
  </ol>

  <h2>제6조 보증의 한계</h2>
  <ol>
    <li>신통픽은 현재 상태 그대로 사용할 수 있습니다. 오류가 없거나 모든 PC에서 정상적으로 실행된다는 점을 보증하지 않습니다.</li>
    <li>소통메신저나 에듀파인의 화면이 변경되면 신통픽이 정상적으로 동작하지 않거나 잘못된 위치를 클릭할 수 있습니다.</li>
    <li>마우스와 키보드를 자동으로 조작하는 기능으로 인해 백신이 신통픽의 실행을 차단할 수 있습니다.</li>
  </ol>

  <h2>제7조 책임의 한계</h2>
  <p>개발자는 신통픽 이용으로 발생한 손해에 대해 법이 허용하는 범위에서 책임을 지지 않습니다. 다만, 개발자의 고의 또는 중대한 과실로 발생한 손해는 제외합니다.</p>

  <h2>제8조 지식재산권</h2>
  <ol>
    <li>신통픽의 저작권은 개발자에게 있으며, 이용 조건은 <a href="license.html">신통픽 사용 허가서</a>를 따릅니다. 판매와 수정은 개발자의 허락 없이 할 수 없습니다.</li>
    <li>신통픽에 포함된 소프트웨어와 글꼴에는 <a href="license.html#oss">오픈소스 고지</a>에 명시된 각각의 라이선스가 적용됩니다.</li>
    <li>소통메신저, 에듀파인, 나이스의 명칭과 화면에 관한 권리는 각 제공 기관에 있습니다. 사용 안내에는 설명에 필요한 화면 일부만 사용합니다.</li>
  </ol>

  <h2>제9조 약관의 변경</h2>
  <p>약관이 변경되면 이 페이지에 변경 내용과 시행일을 안내합니다.</p>

  <h2>제10조 문의</h2>
  <p>이용 조건에 관한 문의는 <a href="mailto:dungst.me@gmail.com">dungst.me@gmail.com</a>으로 보내주세요.</p>
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
