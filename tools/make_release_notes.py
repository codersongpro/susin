"""CHANGELOG.md 에서 해당 버전 단락을 뽑아 릴리즈 본문을 만든다.

릴리즈 노트를 워크플로 안에 박아 두면 버전이 바뀌어도 그대로 남는다.
CHANGELOG 를 고치면 다음 릴리즈에 자동으로 반영되도록 여기서 조립한다.

    python3 tools/make_release_notes.py v2.1.0 [출력경로]
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

CHANGELOG = os.path.join(ROOT, 'CHANGELOG.md')
FOOTER = os.path.join(ROOT, 'docs', 'release_footer.md')


def normalise(version: str) -> str:
    return 'v' + (version or '').strip().lstrip('vV')


def section_for(version: str, text: str):
    """해당 버전 단락. 없으면 None."""
    want = normalise(version)
    pattern = re.compile(r'^##\s+(v[\d.]+)\s*$', re.M)
    marks = list(pattern.finditer(text))
    for i, mark in enumerate(marks):
        if normalise(mark.group(1)) != want:
            continue
        start = mark.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        return text[start:end].strip()
    return None


def build(version: str) -> str:
    with open(CHANGELOG, encoding='utf-8') as f:
        body = section_for(version, f.read())
    with open(FOOTER, encoding='utf-8') as f:
        footer = f.read().strip()

    if not body:
        # 적어 두지 않았다고 릴리즈를 막지는 않는다. 대신 눈에 띄게 남긴다.
        body = (f'{normalise(version)} 변경 내용이 CHANGELOG.md 에 없습니다.\n'
                '아래 커밋 목록을 참고하세요.')
    return f'{body}\n\n---\n\n{footer}\n'


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print('사용법: make_release_notes.py <버전> [출력경로]', file=sys.stderr)
        return 2
    version = argv[0]
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, 'release_notes.md')
    text = build(version)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'{out} ({normalise(version)}, {len(text)}자)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
