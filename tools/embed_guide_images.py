"""안내 그림을 랜딩페이지에 박아 넣는다.

`index.html` 은 파일 한 장으로 배포한다 (`.vercelignore` 가 나머지를 전부 뺀다).
그래서 `assets/guide/` 의 PNG 를 data URI 로 바꿔 `src` 에 직접 넣는다.
그림을 새로 찍거나 바꾼 뒤에 한 번 돌리면 된다.

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
HTML_PATH = os.path.join(ROOT, 'index.html')

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


def data_uri(name: str) -> str:
    """그림 한 장을 data URI 로. 파일이 없으면 그대로 알린다."""
    path = os.path.join(GUIDE_DIR, name)
    with open(path, 'rb') as image:
        encoded = base64.b64encode(image.read()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


def referenced_names(html: str) -> list:
    """랜딩페이지가 쓰겠다고 적어 둔 그림 이름들."""
    return re.findall(r'data-guide="([^"]+)"', html)


def embed(html: str) -> tuple:
    """(고친 html, 바뀐 그림 이름들). 없는 파일은 SystemExit."""
    changed = []
    for name in dict.fromkeys(referenced_names(html)):
        if not os.path.exists(os.path.join(GUIDE_DIR, name)):
            raise SystemExit(f'assets/guide/{name} 이 없습니다')
        uri = data_uri(name)
        pattern = re.compile(
            r'(<img\b[^>]*\bdata-guide="' + re.escape(name) + r'"[^>]*\bsrc=")[^"]*(")'
        )
        html, hits = pattern.subn(lambda m: m.group(1) + uri + m.group(2), html)
        if not hits:
            raise SystemExit(
                f'{name} 을 가리키는 <img> 에 src 속성이 없습니다. '
                'data-guide 뒤에 src="" 를 적어 두세요'
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
