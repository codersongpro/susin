"""Parsing and organization lookup helpers for SotongPick."""

import difflib
import json
import os
import re
import sys


def _resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, name)


def load_org_lookup(path: str | None = None) -> dict[str, str]:
    db_path = path or _resource_path("org_db.json")
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {str(k): str(v) for k, v in data.items()}


_ORG_LOOKUP: dict[str, str] = load_org_lookup()


ORG_END_RE = re.compile(
    r'(학교|초등학교|중학교|고등학교|특수학교|유치원|교육청|교육지원청|'
    r'교육원|교육관|연구원|연구소|도청|시청|군청|구청|교육부|본청|센터|지원청)$'
)
SCHOOL_ABBR_RE = re.compile(r'^[가-힣]{1,6}(초|중|고)$')
TIMESTAMP_RE = re.compile(r'^\[\d{4}[-/]\d{2}[-/]\d{2}[\d\s:.,\-]*\]\s*')
JUNK_RE = re.compile(r'^\d+$|\d{2,4}-\d{3,4}-\d{4}|^https?://|[!@#$%^*()\[\]{}<>|\\/?~`]')


def abbreviate_school(s: str) -> str:
    """풀 학교명 → 검색용 약칭 (백곡초등학교 → 백곡초)"""
    s = s.strip()
    for suffix, short in [("초등학교", "초"), ("중학교", "중"), ("고등학교", "고")]:
        if s.endswith(suffix) and len(s) > len(suffix):
            return s[:-len(suffix)] + short
    return s


def is_org(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if ORG_END_RE.search(s):
        return True
    if SCHOOL_ABBR_RE.match(s):
        return True
    if s in _ORG_LOOKUP:
        return True
    abbr = abbreviate_school(s)
    return abbr in _ORG_LOOKUP


def is_person_name(s: str) -> bool:
    """2~4자 한글, 학교명 아닌 것"""
    s = s.strip()
    if not re.match(r'^[가-힣]{2,4}$', s):
        return False
    return not is_org(s)


def _split_school_suffix(s: str):
    """학교명에서 접두어·종류 분리. '진천상신초등학교' → ('진천상신', '초')"""
    for suffix, short in [("초등학교", "초"), ("중학교", "중"), ("고등학교", "고")]:
        if s.endswith(suffix) and len(s) > len(suffix):
            return s[:-len(suffix)], short
    for short in ["초", "중", "고"]:
        if s.endswith(short) and len(s) > 1:
            return s[:-len(short)], short
    return s, ""


def lookup_org(s: str):
    """소속명 → DB 기준 표준 약칭. 오타 자동 보정."""
    s = s.strip()
    if not s:
        return None
    if s in _ORG_LOOKUP:
        return _ORG_LOOKUP[s]
    abbr = abbreviate_school(s)
    if abbr in _ORG_LOOKUP:
        return _ORG_LOOKUP[abbr]
    keys = list(_ORG_LOOKUP.keys())
    prefix, suffix = _split_school_suffix(s)
    if suffix:
        # Exact prefix+type match first
        for k, v in _ORG_LOOKUP.items():
            kpre, ksuf = _split_school_suffix(k)
            if kpre == prefix and ksuf == suffix:
                return v
        # Type-aware fuzzy: only match keys with same school type to prevent
        # 초/중/고 names from resolving to 유치원 entries (e.g. 오송솔미초 → 오송솔미초병설유치원)
        type_keys = [k for k in keys if _split_school_suffix(k)[1] == suffix]
        matches = difflib.get_close_matches(s, type_keys, n=1, cutoff=0.75)
        if not matches and len(abbr) > 1:
            matches = difflib.get_close_matches(abbr, type_keys, n=1, cutoff=0.75)
    else:
        matches = difflib.get_close_matches(s, keys, n=1, cutoff=0.75)
        if not matches and len(abbr) > 1:
            matches = difflib.get_close_matches(abbr, keys, n=1, cutoff=0.75)
    if matches:
        return _ORG_LOOKUP[matches[0]]
    return None


def best_org_from(tokens: list) -> str:
    """토큰 목록에서 소속명 추출"""
    for tok in tokens:
        if is_org(tok):
            result = lookup_org(tok)
            if result:
                return result
    for tok in tokens:
        if re.match(r'^[가-힣]{2,}$', tok) and not is_person_name(tok):
            result = lookup_org(tok)
            if result:
                return result
    return ''


def extract_pair(tokens: list):
    """토큰 목록 → (소속, 이름) 또는 None"""
    tokens = [t for t in tokens if not JUNK_RE.search(t)]
    name_idx = None
    for i, tok in enumerate(tokens):
        if is_person_name(tok):
            name_idx = i
            break
    if name_idx is None:
        return None
    other = [t for i, t in enumerate(tokens) if i != name_idx]
    org = best_org_from(other) if other else ''
    return (org, tokens[name_idx])


def _tokenize(line: str) -> list:
    """줄 → 정제된 토큰 목록"""
    line = line.strip().replace(' : ', '\t')
    parts = line.split('\t')
    tokens = [t.strip() for t in parts if t.strip()]
    if len(tokens) <= 1:
        tokens = [t.strip() for t in line.split(' ') if t.strip()]
    return [t for t in tokens if not JUNK_RE.search(t)]


def parse_input(text: str) -> list:
    """
    스마트 파서: 표에서 복붙할 때 소속/이름이 별도 행으로 오는 경우를
    pending_org 버퍼로 연결.

    지원 패턴:
    ① 탭 구분 (Excel 표 복붙)       : 소속      이름
    ② 행 교대 (HWP 표 복붙)         : 소속\n이름\n소속\n이름
    ③ 한 행에 소속+이름 (공백 구분)  : 백곡초등학교 김순범
    ④ 타임스탬프 채팅 로그           : [2026-04-02 ...] 이름 소속
    """
    results = []
    pending_org = ''
    for raw_line in text.strip().splitlines():
        line = TIMESTAMP_RE.sub('', raw_line).strip()
        line = re.sub(r'^\d+[.)]\s*', '', line)
        if not line:
            continue
        tokens = _tokenize(line)
        if not tokens:
            continue
        if len(tokens) == 1:
            tok = tokens[0]
            if is_person_name(tok):
                results.append({'org': pending_org, 'name': tok})
                pending_org = ''
                continue
            if is_org(tok):
                resolved = lookup_org(tok)
                pending_org = resolved if resolved else tok
                continue
        if all(is_person_name(t) for t in tokens):
            for t in tokens:
                results.append({'org': pending_org, 'name': t})
            pending_org = ''
            continue
        pair = extract_pair(tokens)
        if pair:
            org, name = pair
            if not org and pending_org:
                org = pending_org
            pending_org = ''
            results.append({'org': org, 'name': name})
            continue
        org = best_org_from(tokens)
        names = [t for t in tokens if is_person_name(t)]
        if org and names:
            for n in names:
                results.append({'org': org, 'name': n})
            pending_org = ''
        elif org:
            pending_org = org
        elif names:
            for n in names:
                results.append({'org': pending_org, 'name': n})
    return results


# ─────────────────────────────────────────────
#  기관 전용 경로 (에듀파인 수신자용)
#
#  기존 parse_input 은 (소속, 이름) 쌍을 뽑으므로 사람 이름이 없으면 결과를
#  만들지 않는다. 에듀파인은 기관명만 있는 명단이 정상 입력이라 별도 경로가 필요하다.
#
#  그리고 lookup_org 는 difflib 퍼지 결과도 그냥 반환한다. 메신저는 틀려도 화면에서
#  눈에 띄지만, 에듀파인 엑셀은 그대로 파일로 나가 등록되므로 조용한 오매칭이 위험하다.
#  그래서 등급을 함께 돌려주는 lookup_org_graded 를 두고, 호출하는 쪽에서 'fuzzy' 는
#  사용자 확인을 받게 한다. 기존 lookup_org 는 손대지 않는다.
# ─────────────────────────────────────────────

GRADE_EXACT = 'exact'    # 정식명 또는 등록된 별칭과 정확히 일치
GRADE_ABBR = 'abbr'      # 약칭 확장 후 일치 (백곡초 → 백곡초등학교)
GRADE_PREFIX = 'prefix'  # 접두어 + 학교급이 모두 일치
GRADE_FUZZY = 'fuzzy'    # 편집거리 기반 추정 — 자동 확정 금지
GRADE_NONE = 'none'      # 후보 없음

AUTO_GRADES = (GRADE_EXACT, GRADE_ABBR, GRADE_PREFIX)

BULLET_RE = re.compile(r'^\s*(?:[-*•·]|\d+\s*[.)])\s*')
QUOTE_RE = re.compile(r'^["\'“‘]+|["\'”’]+$')


def candidate_orgs(s: str, limit: int = 5) -> list:
    """정식명 후보 목록. 학교급이 뚜렷하면 같은 급 안에서만 찾는다."""
    s = s.strip()
    if not s:
        return []
    keys = list(_ORG_LOOKUP.keys())
    _, suffix = _split_school_suffix(s)
    if suffix:
        keys = [k for k in keys if _split_school_suffix(k)[1] == suffix] or keys
    names, seen = [], set()
    for key in difflib.get_close_matches(s, keys, n=limit * 3, cutoff=0.5):
        name = _ORG_LOOKUP[key]
        if name not in seen:
            seen.add(name)
            names.append(name)
        if len(names) >= limit:
            break
    return names


def lookup_org_graded(s: str):
    """소속명 → (정식명 또는 None, 등급).

    lookup_org 와 같은 순서로 찾되 어느 단계에서 맞았는지 함께 알려준다.
    """
    s = s.strip()
    if not s:
        return None, GRADE_NONE
    if s in _ORG_LOOKUP:
        return _ORG_LOOKUP[s], GRADE_EXACT

    abbr = abbreviate_school(s)
    if abbr in _ORG_LOOKUP:
        return _ORG_LOOKUP[abbr], GRADE_ABBR

    prefix, suffix = _split_school_suffix(s)
    if suffix:
        for k, v in _ORG_LOOKUP.items():
            kpre, ksuf = _split_school_suffix(k)
            if kpre == prefix and ksuf == suffix:
                return v, GRADE_PREFIX

    resolved = lookup_org(s)
    if resolved:
        return resolved, GRADE_FUZZY
    return None, GRADE_NONE


def _clean_line(line: str) -> str:
    line = TIMESTAMP_RE.sub('', line.strip())
    line = BULLET_RE.sub('', line)
    return QUOTE_RE.sub('', line).strip()


def _org_from_line(line: str):
    """한 줄 → (원문, 정식명|None, 등급) 또는 None(건너뜀).

    줄 전체가 바로 해석되면 그것을 쓰고, 아니면 토큰으로 나눠 기관으로 해석되는
    토큰 중 **마지막** 것을 고른다. 에듀파인 수신기관명이 '충청북도진천교육지원청
    학성초등학교' 처럼 상위조직 + 조직명 순서라서 뒤쪽이 실제 대상이다.

    사람 이름은 is_person_name 으로 미리 걸러내지 않는다. '오송솔미', '청주중앙'
    처럼 학교명 접두어도 2~4자 한글이라 사람 이름과 형태가 같기 때문이다.
    대신 '기관으로 해석되는가'를 필터로 쓰고, 끝까지 해석 안 된 토큰만
    사람 이름 여부를 따진다.
    """
    if not line:
        return None

    name, grade = lookup_org_graded(line)
    if grade in AUTO_GRADES:
        return line, name, grade

    tokens = [t for t in _tokenize(line) if t]
    if not tokens:
        return None

    best = None
    for tok in tokens:
        tok_name, tok_grade = lookup_org_graded(tok)
        if tok_grade in AUTO_GRADES:
            best = (tok, tok_name, tok_grade)
    if best:
        return best

    # 아무것도 확정되지 않았다. 사람 이름처럼 보이는 토큰을 빼고 남는 것을 본다.
    rest = [t for t in tokens if not is_person_name(t)]
    target = (rest or tokens)[-1]

    name, grade = lookup_org_graded(target)
    if grade == GRADE_NONE and is_person_name(target):
        # 해석도 안 되고 후보도 없으면 사람 이름으로 보고 건너뛴다.
        # 후보가 있으면 사용자가 판단하도록 남긴다 ('오송솔미' 같은 경우).
        if not candidate_orgs(target, limit=1):
            return None
    return target, name, grade


def parse_orgs(text: str) -> list:
    """명단 텍스트 → 기관 목록.

    반환: [{'raw', 'name', 'grade', 'candidates'}, ...]
    입력 순서를 유지하고 중복은 제거한다. 사람 이름만 있는 줄은 건너뛴다.
    해석에 실패한 줄도 grade='none' 으로 남긴다 — 조용히 삼키지 않는다.
    """
    results, seen = [], set()
    for raw_line in (text or '').splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue
        # 쉼표·세미콜론으로 여러 기관을 한 줄에 쓴 경우를 먼저 나눈다
        chunks = [c.strip() for c in re.split(r'[,;]', line) if c.strip()] or [line]
        for chunk in chunks:
            found = _org_from_line(chunk)
            if not found:
                continue
            raw, name, grade = found
            key = name or f'?{raw}'
            if key in seen:
                continue
            seen.add(key)
            results.append({
                'raw': raw,
                'name': name,
                'grade': grade,
                'candidates': [] if grade in AUTO_GRADES else candidate_orgs(raw),
            })
    return results
