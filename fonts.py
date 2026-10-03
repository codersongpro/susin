"""앱 글꼴 Pretendard 를 이 프로그램 안에서만 쓰도록 올린다.

글꼴 파일은 `assets/fonts/` 에 그대로 들어 있다 (SIL OFL 1.1, 이름을 바꾸지 않아야
해서 줄이거나 고치지 않았다). Windows 에서는 프로세스 전용으로 등록하므로 PC 에
설치되지 않고 프로그램을 닫으면 사라진다. 등록하지 못하면 맑은 고딕으로 돌아간다.

tkinter 없이 import 할 수 있다 (테스트가 돈다).
"""

import logging
import os
import sys

FAMILY = 'Pretendard'
FALLBACK = '맑은 고딕'
FILES = ('Pretendard-Regular.ttf', 'Pretendard-Bold.ttf')
_FR_PRIVATE = 0x10


def font_dir() -> str:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'assets', 'fonts')


def font_paths() -> list:
    return [os.path.join(font_dir(), name) for name in FILES]


def register() -> bool:
    """글꼴을 쓸 수 있으면 True. Windows 가 아니면 시스템 글꼴 설정에 맡긴다."""
    paths = font_paths()
    if not all(os.path.exists(p) for p in paths):
        logging.info('Pretendard 글꼴 파일이 없어 %s 을 씁니다', FALLBACK)
        return False
    if sys.platform != 'win32':
        return True
    try:
        import ctypes
        added = sum(ctypes.windll.gdi32.AddFontResourceExW(p, _FR_PRIVATE, 0) for p in paths)
    except Exception as exc:
        logging.info('Pretendard 등록 실패 (%s), %s 을 씁니다', exc, FALLBACK)
        return False
    return added >= len(paths)


def family() -> str:
    return FAMILY if register() else FALLBACK
