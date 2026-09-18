"""버전을 한 번에 올린다.

버전이 main.py, index.html 두 곳, CHANGELOG.md 에 흩어져 있어 손으로 고치면 어긋난다.
실제로 개발자 카드에 v1.7.2 가 남아 있던 적이 있다.

    python3 tools/bump_version.py 2.1.1
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


def read_version() -> str:
    with open(os.path.join(ROOT, 'main.py'), encoding='utf-8') as f:
        return re.search(r"^APP_VERSION\s*=\s*'([^']+)'", f.read(), re.M).group(1)


def html_versions() -> list:
    with open(os.path.join(ROOT, 'index.html'), encoding='utf-8') as f:
        text = f.read()
    return (re.findall(r'신통픽 v([\d.]+)', text)
            + re.findall(r'version-pill">v([\d.]+)<', text))


def changelog_versions() -> list:
    with open(os.path.join(ROOT, 'CHANGELOG.md'), encoding='utf-8') as f:
        return re.findall(r'^##\s+v([\d.]+)\s*$', f.read(), re.M)


def bump(version: str):
    version = version.strip().lstrip('vV')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise SystemExit(f'버전 형식이 아닙니다: {version} (예: 2.1.1)')

    main_path = os.path.join(ROOT, 'main.py')
    with open(main_path, encoding='utf-8') as f:
        text = f.read()
    text, n = re.subn(r"^APP_VERSION = '[^']+'",
                      f"APP_VERSION = '{version}'", text, count=1, flags=re.M)
    assert n == 1, 'main.py 의 APP_VERSION 을 찾지 못했습니다'
    with open(main_path, 'w', encoding='utf-8') as f:
        f.write(text)

    html_path = os.path.join(ROOT, 'index.html')
    with open(html_path, encoding='utf-8') as f:
        text = f.read()
    text = re.sub(r'신통픽 v[\d.]+', f'신통픽 v{version}', text)
    text = re.sub(r'version-pill">v[\d.]+<',
                  f'version-pill">v{version}<', text)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f'버전 {version} 로 맞췄습니다 (main.py, index.html)')
    if version not in changelog_versions():
        print(f'※ CHANGELOG.md 에 "## v{version}" 단락을 아직 안 적었습니다. '
              '적어야 릴리즈 노트에 들어갑니다.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'현재 버전: {read_version()}')
        print('사용법: bump_version.py <버전>   예) bump_version.py 2.1.1')
        sys.exit(2)
    bump(sys.argv[1])
