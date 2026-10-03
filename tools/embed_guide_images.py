"""안내 그림과 앱 화면 캡처를 랜딩페이지에 박아 넣는다.

`index.html` 은 파일 한 장으로 배포한다 (`.vercelignore` 가 나머지를 전부 뺀다).
그래서 `assets/guide/` 의 PNG 를 data URI 로 바꿔 `src` 에 직접 넣는다.
그림을 새로 찍거나 바꾼 뒤에 한 번 돌리면 된다.
소통메신저와 에듀파인의 누르는 자리 그림은 `assets/guide/` (data-guide, PNG),
신통픽 앱 화면 캡처는 `assets/landing/` (data-shot, WebP) 에 둔다.

    python3 tools/embed_guide_images.py            # 미리보기
    python3 tools/embed_guide_images.py --apply    # index.html 갱신

`index.html` 의 `<img data-guide="파일이름.png" ...>` 를 찾아 그 `src` 만 고친다.
어긋난 채로 두면 `tests/test_landing_page.py` 가 잡는다.
"""

import base64
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_DIR = os.path.join(ROOT, 'assets', 'guide')
LANDING_DIR = os.path.join(ROOT, 'assets', 'landing')
# (html 속성, 그림이 있는 폴더, data URI 종류)
SOURCES = (
    ('data-guide', GUIDE_DIR, 'image/png'),
    ('data-shot', LANDING_DIR, 'image/webp'),
)
HTML_PATH = os.path.join(ROOT, 'index.html')

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


def data_uri(name: str, folder: str = GUIDE_DIR, mime: str = 'image/png') -> str:
    """그림 한 장을 data URI 로. 파일이 없으면 그대로 알린다."""
    path = os.path.join(folder, name)
    with open(path, 'rb') as image:
        encoded = base64.b64encode(image.read()).decode('ascii')
    return f'data:{mime};base64,{encoded}'


def referenced_names(html: str, attr: str = 'data-guide') -> list:
    """랜딩페이지가 쓰겠다고 적어 둔 그림 이름들."""
    return re.findall(attr + r'="([^"]+)"', html)


def _fit_size(html: str, attr: str, name: str, path: str) -> str:
    """<img> 의 width, height 를 그림 크기에 맞춘다 (화면이 흔들리지 않게). Pillow 가 없으면 그대로."""
    try:
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        return html
    tag = re.compile(r'<img\b[^>]*\b' + attr + r'="' + re.escape(name) + r'"[^>]*>')

    def fix(match):
        text = match.group(0)
        text = re.sub(r'\bwidth="\d+"', f'width="{width}"', text, count=1)
        text = re.sub(r'\bheight="\d+"', f'height="{height}"', text, count=1)
        return text
    return tag.sub(fix, html)


def embed(html: str) -> tuple:
    """(고친 html, 바뀐 그림 이름들). 없는 파일은 SystemExit."""
    changed = []
    for attr, folder, mime in SOURCES:
        for name in dict.fromkeys(referenced_names(html, attr)):
            if not os.path.exists(os.path.join(folder, name)):
                raise SystemExit(f'{os.path.relpath(folder, ROOT)}/{name} 이 없습니다')
            uri = data_uri(name, folder, mime)
            pattern = re.compile(
                r'(<img\b[^>]*\b' + attr + r'="' + re.escape(name) + r'"[^>]*\bsrc=")[^"]*(")'
            )
            html, hits = pattern.subn(lambda m: m.group(1) + uri + m.group(2), html)
            html = _fit_size(html, attr, name, os.path.join(folder, name))
            if not hits:
                raise SystemExit(
                    f'{name} 을 가리키는 <img> 에 src 속성이 없습니다. '
                    f'{attr} 뒤에 src="" 를 적어 두세요'
                )
            changed.append(name)
    return html, changed


def main(apply: bool):
    with open(HTML_PATH, encoding='utf-8') as source:
        before = source.read()

    after, names = embed(before)
    if not names:
        print('index.html 에 data-guide 그림이 없습니다')
        return

    if after == before:
        print(f'그림 {len(names)}장 모두 최신입니다')
        return

    if not apply:
        print(f'그림 {len(names)}장이 파일과 다릅니다. --apply 로 갱신하세요')
        for name in names:
            print(f'  - {name}')
        return

    with open(HTML_PATH, 'w', encoding='utf-8') as target:
        target.write(after)
    print(f'index.html 에 그림 {len(names)}장을 넣었습니다')


if __name__ == '__main__':
    main('--apply' in sys.argv[1:])
