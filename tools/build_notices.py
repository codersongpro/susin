"""오픈소스 고지를 만든다.

`licenses/` 의 원문과 아래 목록을 읽어서 두 곳을 같은 내용으로 맞춘다.

  - THIRD_PARTY_NOTICES.md  저장소와 exe 에 같이 들어가는 고지문
  - index.html              <!--NOTICES:START--> 와 <!--NOTICES:END--> 사이

사용 라이브러리를 바꾸면 COMPONENTS 를 고치고 이 스크립트를 돌린다.

    python3 tools/build_notices.py           # 어긋난 곳이 있는지만 본다
    python3 tools/build_notices.py --apply   # 두 파일을 다시 쓴다
"""
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_DIR = os.path.join(ROOT, 'licenses')
NOTICE_PATH = os.path.join(ROOT, 'THIRD_PARTY_NOTICES.md')
HTML_PATH = os.path.join(ROOT, 'index.html')
START, END = '<!--NOTICES:START-->', '<!--NOTICES:END-->'

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

MOUSEINFO_NOTICE = """\
MouseInfo (https://github.com/asweigart/mouseinfo), Al Sweigart.
GNU General Public License version 3 (PyPI 분류는 GPLv3+).

PyAutoGUI 를 설치하면 함께 따라 오는 부품입니다. 신통픽은 이 부품의 기능을 쓰지 않습니다.
실행 파일에는 함께 묶여 있으므로 GPL 조건에 따라 아래를 안내합니다.

  - 라이선스 전문: licenses/MouseInfo-GPL-3.0-full.txt, https://www.gnu.org/licenses/gpl-3.0.html
  - 원본 소스: https://github.com/asweigart/mouseinfo, https://pypi.org/project/MouseInfo/
  - 신통픽 소스: https://github.com/codersongpro/susin
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
    ('MouseInfo', 'https://github.com/asweigart/mouseinfo',
     'PyAutoGUI 에 딸려 오는 부품 (신통픽은 쓰지 않음)',
     'GPL-3.0', ('text', MOUSEINFO_NOTICE)),
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
        '신통픽 자체의 라이선스는 `LICENSE` (MIT) 입니다.',
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


def build_html() -> str:
    out = [START]
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
    out.append('    ' + END)
    return '\n'.join(out)


def apply_html(page: str) -> str:
    pattern = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.S)
    if not pattern.search(page):
        raise SystemExit('index.html 에 NOTICES:START / NOTICES:END 표시가 없습니다')
    return pattern.sub(lambda _m: build_html().strip(), page, count=1)


def main(apply: bool) -> int:
    with open(HTML_PATH, encoding='utf-8') as source:
        page = source.read()
    new_page = apply_html(page)
    notice = build_markdown()
    try:
        with open(NOTICE_PATH, encoding='utf-8') as source:
            old_notice = source.read()
    except OSError:
        old_notice = ''
    stale = [name for name, same in (('index.html', new_page == page),
                                     ('THIRD_PARTY_NOTICES.md', notice == old_notice)) if not same]
    if not stale:
        print('오픈소스 고지가 최신입니다')
        return 0
    if not apply:
        print('어긋난 파일: ' + ', '.join(stale) + '  (--apply 로 다시 씁니다)')
        return 1
    with open(HTML_PATH, 'w', encoding='utf-8', newline='') as target:
        target.write(new_page)
    with open(NOTICE_PATH, 'w', encoding='utf-8', newline='\n') as target:
        target.write(notice)
    print('다시 썼습니다: ' + ', '.join(stale))
    return 0


if __name__ == '__main__':
    raise SystemExit(main('--apply' in sys.argv))
