"""PyInstaller 용 버전 정보 리소스를 만든다.

exe 에 제품명·회사명·설명이 비어 있으면 (빌드 로그의 'Copying 0 resources')
백신이 의심 점수를 더 준다. 정상 프로그램은 이 값을 채운다.

버전은 main.py 의 APP_VERSION 에서 읽어 오므로 따로 관리할 필요가 없다.

    python3 tools/make_version_file.py [출력경로]
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows 콘솔 기본 인코딩(cp1252)에서 한글을 찍으면 UnicodeEncodeError 로 죽는다
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

COMPANY = '송동석'
PRODUCT = '신통픽'
DESCRIPTION = '신통픽 — 소통메신저·에듀파인 수신자 선택 도우미'
EXE_NAME = 'sintongpick.exe'
HOMEPAGE = 'https://github.com/codersongpro/susin'

# 0x0412 = 한국어, 1200(0x04B0) = 유니코드
LANG_CODEPAGE = '041204B0'
LANG_ID, CODEPAGE_ID = 0x0412, 1200

TEMPLATE = '''# PyInstaller 버전 정보 리소스 — tools/make_version_file.py 가 만든다. 직접 고치지 말 것.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tup},
    prodvers={tup},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '{langcp}',
        [StringStruct('CompanyName', {company!r}),
         StringStruct('FileDescription', {description!r}),
         StringStruct('FileVersion', {version!r}),
         StringStruct('InternalName', {internal!r}),
         StringStruct('LegalCopyright', {copyright!r}),
         StringStruct('OriginalFilename', {original!r}),
         StringStruct('ProductName', {product!r}),
         StringStruct('ProductVersion', {version!r}),
         StringStruct('Comments', {comments!r})])
    ]),
    VarFileInfo([VarStruct('Translation', [{lang}, {codepage}])])
  ]
)
'''


def read_app_version(path: str = None) -> str:
    path = path or os.path.join(ROOT, 'main.py')
    with open(path, encoding='utf-8') as f:
        match = re.search(r"^APP_VERSION\s*=\s*'([^']+)'", f.read(), re.M)
    if not match:
        raise RuntimeError('main.py 에서 APP_VERSION 을 찾지 못했습니다')
    return match.group(1)


def version_tuple(version: str) -> tuple:
    parts = [int(p) for p in version.split('.')[:4] if p.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def render(version: str) -> str:
    return TEMPLATE.format(
        tup=version_tuple(version),
        langcp=LANG_CODEPAGE,
        lang=LANG_ID,
        codepage=CODEPAGE_ID,
        company=COMPANY,
        description=DESCRIPTION,
        version=version,
        internal='sintongpick',
        copyright=f'© 2026 {COMPANY}',
        original=EXE_NAME,
        product=PRODUCT,
        comments=HOMEPAGE,
    )


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out = argv[0] if argv else os.path.join(ROOT, 'version_info.txt')
    version = read_app_version()
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(render(version))
    print(f'{out} (버전 {version})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
