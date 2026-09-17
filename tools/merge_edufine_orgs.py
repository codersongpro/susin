"""에듀파인 조직도에서 수확한 기관명을 org_db.json 에 보탠다.

org_codes.json 은 전체경로를 키로 쓰지만, org_db 는 사람이 입력할 법한 이름을
정식명에 잇는 사전이다. 그래서 여기서 옮겨 심는다.

주의 — 통째로 넣으면 안 된다.
  sotong_parser.is_person_name() 은 '2~4자 한글이면서 기관이 아닌 것'으로 사람을
  판별한다. '다하' 같은 짧은 부서명을 기관으로 등록하면 그 이름을 가진 사람이
  사람으로 인식되지 않아 소통메신저 기능이 망가진다.

그래서 이렇게 거른다.
  · 전체경로('충청북도교육청 정책기획과')는 전부 넣는다 — 길어서 사람 이름과 겹치지 않는다
  · 짧은 이름은 4자 이상 + 다른 기관과 겹치지 않음 + 일반명사 아님 일 때만 넣는다
  · 기존 별칭은 절대 덮어쓰지 않는다

    python3 tools/merge_edufine_orgs.py            # 미리보기
    python3 tools/merge_edufine_orgs.py --apply
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import edufine  # noqa: E402

ORG_DB = os.path.join(ROOT, 'org_db.json')

MIN_SHORT_LEN = 4

# 3자여도 사람 이름이 될 수 없는 부서 접미사. '원'은 '숭덕원'처럼 사람 이름과
# 헷갈릴 수 있어 넣지 않는다.
DEPT_SUFFIXES = ('과', '관', '부', '실', '팀')

# 여러 기관에 공통으로 쓰여 단독으로는 아무것도 가리키지 못하는 이름
GENERIC_NAMES = {
    '교육과', '행정과', '학교지원센터', '병설유치원', '교육지원과',
    '운영지원과', '총무과', '경영지원과',
}


def build_additions(codes: dict, db: dict):
    """(추가할 {별칭: 정식명}, 건너뛴 [(이름, 사유)])"""
    index = edufine.index_by_short_name(codes)
    additions, skipped = {}, []

    for full in sorted(codes.get('기관', {})):
        short = edufine.short_name(full)

        # 전체경로는 언제나 안전하다.
        # 다만 가리키는 값은 짧은 이름이 유일할 때만 짧은 이름으로 준다.
        # '충청북도청주교육지원청 행정과' 를 '행정과' 로 축약하면 11곳과 뭉쳐
        # 정확한 전체경로를 줬는데도 코드를 못 찾는다.
        unique_short = short and len(index.get(short, [])) == 1
        target = short if unique_short else full
        if additions.get(full) != target and db.get(full) != target:
            additions[full] = target

        if not short or short in db or short in additions:
            continue
        if len(short) < MIN_SHORT_LEN:
            if not (len(short) == 3 and short.endswith(DEPT_SUFFIXES)):
                skipped.append((short, f'{MIN_SHORT_LEN}자 미만 — 사람 이름과 헷갈림'))
                continue
        if short in GENERIC_NAMES:
            skipped.append((short, '여러 기관 공통 명칭'))
            continue
        if len(index.get(short, [])) > 1:
            skipped.append((short, f'{len(index[short])}곳에서 겹침'))
            continue
        additions[short] = short

    return additions, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    codes = edufine.load_codes()
    with open(ORG_DB, 'r', encoding='utf-8') as f:
        db = json.load(f)
    before = len(db)

    additions, skipped = build_additions(codes, db)
    short_adds = {k: v for k, v in additions.items() if ' ' not in k}

    print(f'수확 기관 {len(codes.get("기관", {}))}곳')
    print(f'추가할 별칭 {len(additions)}개 (전체경로 {len(additions) - len(short_adds)}, '
          f'짧은 이름 {len(short_adds)})')
    print(f'별칭 {before} → {before + len(additions)}')
    print()
    print('새로 인식되는 짧은 이름 (앞 25개):')
    for k in sorted(short_adds)[:25]:
        print(f'  + {k}')
    print()
    print(f'안전을 위해 건너뛴 이름 {len(skipped)}개 (앞 15개):')
    for name, why in sorted(set(skipped))[:15]:
        print(f'  - {name}  ({why})')

    if not args.apply:
        print('\n(미리보기입니다. 반영하려면 --apply 를 붙이세요.)')
        return 0

    db.update(additions)
    with open(ORG_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
    print(f'\n{ORG_DB} 에 반영했습니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
