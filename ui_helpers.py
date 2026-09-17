"""UI formatting helpers."""

GRADE_MARKS = {
    'exact':  '',
    'abbr':   '',
    'prefix': '',
    'fuzzy':  '?  추정 — 확인 필요',
    'ambiguous': '?  같은 이름이 여럿 — 골라야 함',
    'none':   '!  찾지 못함 — 확인 필요',
}


def format_item_label(item: dict) -> str:
    org = item.get('org', '')
    name = item.get('name', '')
    reason = item.get('failure_reason', '')

    if 'grade' in item and not name:
        # 에듀파인 기관 항목: 사람 이름이 없다
        raw = item.get('raw', '')
        shown = item.get('search') or org or raw
        label = shown
        if org and raw and raw not in (org, shown):
            label = f'{shown}   ← {raw}'
        mark = GRADE_MARKS.get(item.get('grade'), '')
        if mark:
            label = f'{label}      {mark}'
    else:
        label = f'[{org}]  {name}' if org else f'{name}  (소속없음)'

    return f'{label}  — 실패: {reason}' if reason else label
