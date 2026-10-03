"""추출한 명단과 실제로 들어간 명단을 맞춰 본다.

소통픽은 소통메신저 [선택된 사용자] 에, 수신픽은 수신그룹 엑셀에 실제로 몇이
들어갔는지 세어 추출한 수와 비교한다. 모자라면 누가 왜 빠졌는지 돌려준다.

화면 없이 도는 순수 함수만 둔다. 창은 main.py 의 ResultReport 가 그린다.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

import edufine
from automation import FAIL_DUPLICATE
from sotong_parser import AUTO_GRADES

# 소통픽: 워커가 결과를 남기지 못한 항목
NOT_TRIED = '중지되어 시도 안 함'
NOT_CHECKED = '결과를 확인하지 못함'

# 수신픽: 엑셀에 들어가지 못한 사유
UNCONFIRMED = '확정 안 됨 (후보 중에서 골라야 함)'
NO_ORG = '기관 미확정'
NO_CODE = '코드 없음'
AMBIGUOUS = '동명 기관 여럿'
NOT_WRITTEN = '엑셀에 써지지 않음'


@dataclass
class Tally:
    """한 번 돌린 결과.

    total    추출한 수
    placed   들어간 항목
    already  원래 들어 있던 항목 (소통픽 '이미 선택된 사용자')
    missing  빠진 항목과 사유 [(item, reason)]
    extra    명단에 없는데 들어간 줄 수 (수신픽 엑셀 대조용)
    """
    total: int
    placed: list = field(default_factory=list)
    already: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    extra: int = 0

    @property
    def reflected(self) -> int:
        """받는 쪽에 들어 있는 수. 원래 있던 것도 들어 있는 것이다."""
        return len(self.placed) + len(self.already)

    @property
    def short(self) -> int:
        return len(self.missing)


def item_label(item: dict) -> str:
    """사람이 알아볼 이름. 따로 만든 검색어가 있으면 그것을 쓴다."""
    org = item.get('org') or ''
    name = item.get('name') or ''
    return (item.get('search')
            or f'{org} {name}'.strip()
            or item.get('raw')
            or '(이름 없음)')


# ── 소통픽 ─────────────────────────────────────

def messenger_tally(items, stopped: bool = False) -> Tally:
    """소통픽 실행 결과를 센다.

    워커는 담은 항목에 added 를, 못 담은 항목에 failure_reason 을 남긴다.
    둘 다 없는 항목은 조용히 넘어가지 않고 사유를 붙여 빠진 쪽에 넣는다.
    중지했다면 그 뒤 항목은 시도조차 안 한 것이다.
    """
    items = list(items)
    tally = Tally(total=len(items))
    for item in items:
        reason = item.get('failure_reason')
        if item.get('added'):
            tally.placed.append(item)
        elif reason == FAIL_DUPLICATE:
            tally.already.append(item)
        else:
            tally.missing.append(
                (item, reason or (NOT_TRIED if stopped else NOT_CHECKED)))
    return tally


# ── 수신픽 ─────────────────────────────────────

def edufine_tally(items, codes: dict, written_codes) -> Tally:
    """추출한 기관과 실제로 엑셀에 써진 기관코드를 맞춰 본다.

    written_codes 는 저장한 엑셀을 다시 열어 읽은 기관코드 목록이다. 만들려던
    목록이 아니라 파일에 실제로 남은 것과 비교해야 '들어갔다' 고 말할 수 있다.
    """
    items = list(items)
    tally = Tally(total=len(items))
    index = edufine.index_by_short_name(codes)
    left = Counter(code for code in written_codes if code)

    for item in items:
        if item.get('grade') not in AUTO_GRADES:
            tally.missing.append((item, UNCONFIRMED))
            continue
        org = item.get('org')
        if not org:
            tally.missing.append((item, NO_ORG))
            continue
        entry, ambiguous = edufine.lookup_code(codes, org, index)
        if not entry:
            tally.missing.append((item, AMBIGUOUS if ambiguous else NO_CODE))
            continue
        if left[entry['code']] > 0:
            left[entry['code']] -= 1
            tally.placed.append(item)
        else:
            tally.missing.append((item, NOT_WRITTEN))

    tally.extra = sum(left.values())
    return tally


# ── 글로 풀기 ──────────────────────────────────

def summary_line(tally: Tally, unit: str) -> str:
    """'추출 50명 · 들어감 45명 · 빠짐 5명' 처럼 한 줄로."""
    parts = [f'추출 {tally.total}{unit}', f'들어감 {tally.reflected}{unit}']
    if tally.already:
        parts.append(f'(원래 있던 {len(tally.already)}{unit} 포함)')
    parts.append(f'빠짐 {tally.short}{unit}')
    if tally.extra:
        parts.append(f'명단에 없는 줄 {tally.extra}개')
    return '  ·  '.join(parts)


def grouped_missing(tally: Tally) -> list:
    """사유별로 묶는다. 많은 사유가 위로 온다."""
    buckets = {}
    for item, reason in tally.missing:
        buckets.setdefault(reason, []).append(item)
    return sorted(buckets.items(), key=lambda pair: -len(pair[1]))


def missing_text(tally: Tally, unit: str) -> str:
    lines = []
    for reason, rows in grouped_missing(tally):
        lines.append(f'[{reason}]  {len(rows)}{unit}')
        lines.extend(f'  {item_label(item)}' for item in rows)
        lines.append('')
    return '\n'.join(lines).strip()


def placed_text(tally: Tally) -> str:
    """들어간 명단. 받는 쪽 목록과 하나씩 대조할 때 쓴다."""
    rows = [item_label(item) for item in tally.placed]
    rows += [f'{item_label(item)}  (원래 있던)' for item in tally.already]
    return '\n'.join(rows)


def compare_count(expected: int, shown: int, where: str, unit: str, who: str):
    """받는 쪽 화면에 보이는 수와 들어갔다고 본 수를 비교한다.

    돌려주는 값은 (판정, 안내문). 판정은 match / short / over.
    모자랄 때는 신통픽이 어느 것인지 알 수 없다. 클릭이 빗나가도 받는 쪽은
    아무 말을 하지 않기 때문이다. 그래서 대조할 목록을 복사하라고 안내한다.
    """
    if shown == expected:
        return 'match', f'{where} 수와 같습니다. 빠진 {who}이 없습니다.'
    if shown < expected:
        gap = expected - shown
        return 'short', (
            f'{gap}{unit}이 모자랍니다. 신통픽은 넣었다고 봤지만 {where}에는 없는 '
            f'{who}이 있습니다. [들어간 명단 복사] 로 목록을 복사해 하나씩 대조해 보세요.')
    gap = shown - expected
    return 'over', (
        f'{gap}{unit}이 더 많습니다. 시작하기 전부터 들어 있던 {who}일 수 있습니다.')


# ── 소통메신저 [선택된 사용자] 와 소통픽 명단 맞춰 보기 ──
# [선택된 사용자] 한 줄은 '이경숙 [교사(초등)] [1학년] 안전/통학버스 ...' 처럼
# 이름 뒤에 직위가 괄호로 붙고, 학교 이름은 나오지 않는다. 그래서 이름으로만
# 맞출 수 있다. 같은 이름이 소통픽 명단에 다른 학교로 여럿 있으면 누가
# 들어갔는지 가릴 수 없으므로 '확인 필요' 로 따로 둔다. 짐작해서 넘기지 않는다.
NOT_IN_MESSENGER = '소통메신저에 없음'
SAME_NAME_UNSURE = '동명이인 확인 필요'

_NAME_BEFORE_BRACKET = re.compile(r'([가-힣]{2,5})\s*[\[(]')
_HANGUL_WORD = re.compile(r'[가-힣]{2,5}')


def person_name_from_row(text: str):
    """[선택된 사용자] 한 줄에서 사람 이름을 뽑는다. 못 뽑으면 None."""
    text = text or ''
    found = _NAME_BEFORE_BRACKET.search(text)
    if found:
        return found.group(1)
    found = _HANGUL_WORD.search(text)
    return found.group(0) if found else None


def _plain(text) -> str:
    return re.sub(r'\s+', '', text or '')


@dataclass
class MessengerCompare:
    """소통픽 명단과 소통메신저 [선택된 사용자] 를 맞춰 본 결과.

    inside   들어간 소통픽 항목
    missing  빠진 소통픽 항목
    unsure   (이름, 그 이름의 소통픽 항목들, 소통메신저에 있는 수) 동명이인이라 못 가림
    extra    소통메신저에만 있는 줄 (시작 전부터 있었거나 손으로 넣은 사람)
    no_name  이름이 없어 맞춰 볼 수 없는 소통픽 항목
    rows     소통메신저에서 읽은 줄 수
    """
    inside: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    unsure: list = field(default_factory=list)
    extra: list = field(default_factory=list)
    no_name: list = field(default_factory=list)
    rows: int = 0


def compare_with_messenger(items, rows) -> MessengerCompare:
    """소통픽 명단(items) 과 소통메신저에서 읽은 줄(rows) 을 이름으로 맞춘다.

    같은 사람이 명단에 두 번 있으면(학교와 이름이 같으면) 한 사람으로 센다.
    이름이 같고 학교가 다르면 다른 사람이다. 소통메신저에 그 이름이 사람 수만큼
    있으면 다 들어간 것이고, 하나도 없으면 다 빠진 것이고, 그 사이면 누가 들어갔는지
    알 수 없어 확인 필요로 둔다.
    """
    result = MessengerCompare(rows=len(rows))
    found = Counter()
    rows_by_name = {}
    for text in rows:
        name = person_name_from_row(text)
        if name:
            found[name] += 1
            rows_by_name.setdefault(name, []).append(text)
        else:
            result.extra.append(text)

    by_name = {}
    for item in items:
        name = _plain(item.get('name'))
        if not name:
            result.no_name.append(item)
            continue
        by_name.setdefault(name, []).append(item)

    for name, people in by_name.items():
        distinct = len({_plain(item.get('org')) for item in people})
        have = found.get(name, 0)
        if have >= distinct:
            result.inside.extend(people)
        elif have == 0:
            result.missing.extend(people)
        else:
            result.unsure.append((name, people, have))

    for name, have in found.items():
        people = by_name.get(name, [])
        expected = len({_plain(item.get('org')) for item in people})
        if have > expected:
            result.extra.extend(rows_by_name[name][expected:])
    return result


def compare_text(result: MessengerCompare) -> str:
    """빠진 사람, 확인 필요, 소통메신저에만 있는 사람 순으로 글로 푼다."""
    lines = []
    if result.missing:
        lines.append(f'[{NOT_IN_MESSENGER}]  {len(result.missing)}명')
        lines.extend(f'  {item_label(item)}' for item in result.missing)
        lines.append('')
    if result.unsure:
        count = sum(len(people) for _name, people, _have in result.unsure)
        lines.append(f'[{SAME_NAME_UNSURE}]  {count}명')
        for name, people, have in result.unsure:
            lines.append(f'  {name}: 명단에 {len(people)}명, 소통메신저에 {have}명')
            lines.extend(f'    {item_label(item)}' for item in people)
        lines.append('')
    if result.no_name:
        lines.append(f'[이름이 없어 맞춰 보지 못함]  {len(result.no_name)}건')
        lines.extend(f'  {item_label(item)}' for item in result.no_name)
        lines.append('')
    if result.extra:
        lines.append(f'[소통메신저에만 있음]  {len(result.extra)}명')
        lines.extend(f'  {text[:40]}' for text in result.extra)
        lines.append('')
    if result.inside:
        lines.append(f'[들어감]  {len(result.inside)}명')
        lines.extend(f'  {item_label(item)}' for item in result.inside)
    return '\n'.join(lines).strip()
