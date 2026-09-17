"""나이스 학교기본정보 CSV로 org_db.json 을 보강한다.

기존 항목은 절대 덮어쓰지 않는다 (손으로 다듬은 별칭을 잃지 않기 위해 추가만 한다).
CSV 에는 유치원과 기관(교육지원청·직속기관)이 없으므로, org_db 에만 있는 항목은 그대로 둔다.

    python3 tools/merge_neis.py              # 무엇이 추가될지 보여주기만 함
    python3 tools/merge_neis.py --apply      # 실제로 org_db.json 에 반영
"""

import argparse
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORG_DB = os.path.join(ROOT, 'org_db.json')
DEFAULT_CSV = os.path.join(ROOT, 'data', 'schools_neis_20260831.csv')

SIDO = '충청북도'
SCHOOL_SUFFIXES = [('초등학교', '초'), ('중학교', '중'), ('고등학교', '고')]

# 실제로 널리 쓰이는 복합 약칭. 일반 초/중/고 규칙보다 먼저 적용한다.
# (충북외국어고등학교 → 충북외고. 일반 규칙만 쓰면 '충북외고'가 '충북고등학교'로
#  잘못 퍼지매칭되므로 별칭을 명시적으로 심어 둔다.)
COMPOUND_SUFFIXES = [
    ('여자중학교', '여중'),
    ('여자고등학교', '여고'),
    ('외국어고등학교', '외고'),
    ('공업고등학교', '공고'),
    ('상업고등학교', '상고'),
    ('농업고등학교', '농고'),
    ('과학고등학교', '과고'),
    ('예술고등학교', '예고'),
    ('체육고등학교', '체고'),
    ('국제고등학교', '국제고'),
    ('관광고등학교', '관광고'),
    ('디자인고등학교', '디자인고'),
    ('정보고등학교', '정보고'),
    ('방송통신고등학교', '방통고'),
    ('방송통신중학교', '방통중'),
]
# 각종학교 표기의 꼬리표: 다다예술학교(고) → 다다예술학교
KIND_TAG_RE = re.compile(r'\((?:초|중|고)\)$')


def canonical_name(raw: str) -> str:
    """CSV 학교명 → org_db 정식명 표기."""
    return KIND_TAG_RE.sub('', raw.strip()).strip()


def _shorten(name: str) -> list:
    """학교명 → 약칭들. 복합 약칭을 일반 초/중/고 규칙보다 먼저 적용한다."""
    out = []
    for suffix, short in COMPOUND_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            out.append(name[: -len(suffix)] + short)
            break
    for suffix, short in SCHOOL_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            out.append(name[: -len(suffix)] + short)
            break
    return out


def aliases_for(name: str) -> list:
    """정식명에서 사람이 실제로 입력할 법한 별칭들을 만든다."""
    out = [name]
    out.extend(_shorten(name))
    for prefix in (SIDO, '충북'):
        if name.startswith(prefix) and len(name) > len(prefix):
            stripped = name[len(prefix):]
            out.append(stripped)
            out.extend(_shorten(stripped))
    # '학력인정 예일미용고등학교' 처럼 앞에 자격 표기가 붙은 경우
    if ' ' in name:
        tail = name.split(' ', 1)[1].strip()
        if tail and tail != name:
            out.append(tail)
            out.extend(_shorten(tail))
    seen, uniq = set(), []
    for a in out:
        if a and a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq


def load_csv_schools(path: str) -> list:
    with open(path, 'r', encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    names, seen = [], set()
    for r in rows:
        if not r.get('시도교육청명', '').startswith(SIDO):
            continue
        name = canonical_name(r.get('학교명', ''))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def merge(db: dict, names: list):
    """(갱신된 db, 추가된 정식명 목록, 추가된 별칭 수)"""
    existing_canon = set(db.values())
    added_names, added_aliases = [], 0
    for name in names:
        is_new = name not in existing_canon
        for alias in aliases_for(name):
            if alias in db:          # 기존 별칭은 건드리지 않는다
                continue
            db[alias] = name
            added_aliases += 1
        if is_new:
            added_names.append(name)
            existing_canon.add(name)
    return db, added_names, added_aliases


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--csv', default=DEFAULT_CSV)
    ap.add_argument('--db', default=ORG_DB)
    ap.add_argument('--apply', action='store_true', help='실제로 파일에 쓴다')
    args = ap.parse_args(argv)

    with open(args.db, 'r', encoding='utf-8') as f:
        db = json.load(f)
    before = len(db)

    names = load_csv_schools(args.csv)
    db, added_names, added_aliases = merge(db, names)

    print(f'CSV 충북 학교: {len(names)}개')
    print(f'새로 추가되는 학교: {len(added_names)}개')
    for n in added_names:
        print(f'  + {n}')
    print(f'별칭 {before} → {len(db)} (+{added_aliases})')

    if not args.apply:
        print('\n(미리보기입니다. 반영하려면 --apply 를 붙이세요.)')
        return 0

    with open(args.db, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    print(f'\n{args.db} 에 반영했습니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
