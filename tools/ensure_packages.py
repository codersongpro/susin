"""개발용 실행.bat 이 부르는 부품 확인. requirements.txt 를 읽어 빠진 것만 깐다.

bat 파일에 부품 이름을 적어 두면, 부품이 늘 때마다 bat 를 새로 받아야 한다.
실제로 comtypes 를 더했을 때 예전 bat 를 쓰던 PC 에서 깔리지 않았다.
이 파일은 코드와 함께 새로 받아지므로 bat 는 그대로 써도 된다.
"""

import importlib.util
import os
import re
import subprocess
import sys

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 앱을 띄우는 데는 필요 없는 것
SKIP = {'pyinstaller'}
# 설치 이름과 불러오는 이름이 다른 것
IMPORT_NAMES = {'pywin32': 'win32gui', 'pillow': 'PIL'}


def requirements(path=None) -> list:
    """requirements.txt 의 부품 이름. 버전 조건과 주석은 뗀다."""
    path = path or os.path.join(ROOT, 'requirements.txt')
    names = []
    with open(path, encoding='utf-8') as fp:
        for line in fp:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            name = re.split(r'[<>=!~\[; ]', line, maxsplit=1)[0].strip()
            if name and name.lower() not in SKIP:
                names.append(name)
    return names


def missing(names) -> list:
    """깔려 있지 않은 부품."""
    return [name for name in names
            if importlib.util.find_spec(IMPORT_NAMES.get(name.lower(), name)) is None]


def main() -> int:
    need = missing(requirements())
    if not need:
        print('   다 있습니다.')
        return 0
    print('   빠진 것이 있어 설치합니다: ' + ', '.join(need))
    return subprocess.call([sys.executable, '-m', 'pip', 'install',
                            '--disable-pip-version-check', *need])


if __name__ == '__main__':
    sys.exit(main())
