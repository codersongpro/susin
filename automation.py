"""Small automation status helpers."""

import re

FAIL_NO_USER = '사용자 없음'
FAIL_DUPLICATE = '중복'
FAIL_SEARCH_STALE = '검색 결과 안 바뀜'
FAIL_COORDINATE = '좌표 오류'
FAIL_MANUAL_STOP = '수동 중지'
FAIL_AUTOMATION = '자동화 오류'

# 안내창이 뜨기를 기다리는 시간(초). 이미 선택된 사용자였으면 안내창이 뜬다.
POPUP_WAIT_ADD = 0.5

# 이미 선택된 사용자를 다시 선택할 때 충북소통메신저가 띄우는 안내창 문구.
# 실제 문구는 '선택된 사용자 입니다.' 다. 예전에는 '이미' 만 찾다가 이 안내창을
# 못 알아봐서, 중복도 못 걸러내고 추가 여부도 확인하지 못했다.
DUPLICATE_POPUP_HINTS = ('선택된 사용자', '이미 선택', '이미 추가', '중복')


def looks_like_duplicate_popup(texts) -> bool:
    """안내창에서 긁어온 글에 이미 선택된 사용자라는 말이 있는가."""
    joined = ' '.join(t for t in texts if t)
    return any(hint in joined for hint in DUPLICATE_POPUP_HINTS)


def failure_reason_from_error(exc: Exception) -> str:
    return FAIL_COORDINATE if '좌표' in str(exc) else FAIL_AUTOMATION


# ── 검색 결과가 떴는지 보는 값들 ─────────────────
# 결과 첫 줄의 한 점만 보면, 이름 길이에 따라 글자 사이 빈 칸에 좌표가 떨어져
# 결과가 있는데도 없다고 판정한다. 그래서 그 줄을 가로로 넓게 훑는다.
RESULT_SCAN_WIDTH = 320       # 결과 첫 줄에서 가로로 살펴볼 너비(px)
RESULT_SCAN_HEIGHT = 13       # 세로 높이(px)
RESULT_BACKGROUND_MIN = 235   # 세 채널이 모두 이 값 이상이면 빈 배경으로 본다
RESULT_MIN_COLUMNS = 4        # 글자가 있다고 볼 최소 세로 열 수
RESULT_WAIT_MIN = 1.5         # 결과가 늦게 떠도 최소 이만큼은 기다린다(초)


def _is_background(pixel) -> bool:
    return all(channel >= RESULT_BACKGROUND_MIN for channel in pixel[:3])


def result_text_columns(pixels, width: int, height: int) -> int:
    """결과 영역에서 글자로 보이는 세로 열의 개수를 센다.

    pixels 는 왼쪽 위부터 가로로 읽은 (r, g, b) 목록이다.
    가로로 길게 이어진 단색 줄(표 테두리, 선택 강조 띠)은 글자로 세지 않는다.
    """
    if width <= 0 or height <= 0:
        return 0
    columns = set()
    for row in range(height):
        row_pixels = pixels[row * width:(row + 1) * width]
        if len(row_pixels) < width:
            break
        marks = [x for x, px in enumerate(row_pixels) if not _is_background(px)]
        if not marks:
            continue
        if len(marks) >= width * 0.9:
            tones = {tuple(px[:3]) for px in row_pixels}
            if len(tones) <= 3:
                continue    # 테두리선이나 단색 배경 띠
        columns.update(marks)
    return len(columns)


def looks_like_result(pixels, width: int, height: int,
                      min_columns: int = RESULT_MIN_COLUMNS) -> bool:
    """검색 결과 첫 줄에 글자가 그려져 있는가."""
    return result_text_columns(pixels, width, height) >= min_columns


# ── [선택된 사용자] 목록 세기 ──────────────────
# 소통메신저는 담긴 사람 수를 숫자로 보여 주지 않는다. 목록도 스크롤해야 다 보이고
# 가나다순도 아니라 화면으로는 셀 수 없다. 대신 그 목록이 윈도우 표준 목록 칸이면
# 칸에게 항목 수를 직접 물을 수 있다. 화면에 안 보이는 항목도 함께 센다.
LB_GETCOUNT = 0x018B          # 목록 상자(ListBox) 항목 수
LVM_GETITEMCOUNT = 0x1004     # 목록 보기(ListView) 항목 수


def count_message_for(class_name: str):
    """이 종류의 칸에 항목 수를 묻는 메시지. 목록 칸이 아니면 None.

    모르는 칸에는 아무 메시지도 보내지 않는다. 사용자 정의 칸은 같은 번호를
    다른 뜻으로 쓸 수 있다.
    """
    name = (class_name or '').lower()
    if 'listview' in name:
        return LVM_GETITEMCOUNT
    if 'listbox' in name:
        return LB_GETCOUNT
    return None


def pick_selected_list(children, arrow_x: int, arrow_y: int):
    """[선택된 사용자] 목록 칸을 고른다.

    children 은 (핸들, 클래스 이름, (왼, 위, 오른, 아래)) 목록이다.
    오른쪽 화살표 버튼의 오른쪽에 있고, 버튼 높이를 위아래로 걸치는 목록 칸이
    [선택된 사용자] 다. 검색 결과 목록은 버튼 왼쪽에 있어서 걸러진다.
    그런 칸이 여럿이면 버튼에 가장 가까운 것을 고른다. 없으면 None.
    """
    hits = []
    for hwnd, class_name, rect in children:
        if count_message_for(class_name) is None:
            continue
        left, top, right, bottom = rect
        if left >= arrow_x and top <= arrow_y <= bottom and right > left:
            hits.append((left - arrow_x, hwnd, class_name, rect))
    if not hits:
        return None
    hits.sort(key=lambda hit: hit[0])
    _gap, hwnd, class_name, rect = hits[0]
    return hwnd, class_name, rect


# ── 웹 화면으로 된 [사용자 선택] 창 읽기 ─────────
# 소통메신저의 [사용자 선택] 창 안은 크롬(CEF) 웹 화면이다. 윈도우 목록 칸이
# 아니라서 항목 수를 물을 수 없다. 대신 화면 읽어 주기(UI 자동화)로 웹 화면 속
# 요소를 받아 [선택된 사용자] 목록의 줄 수를 센다. 스크롤 밖의 줄도 요소로는
# 남아 있어서 함께 센다.
UIA_TYPE_NAMES = {
    50000: 'Button', 50004: 'Edit', 50005: 'Hyperlink', 50006: 'Image',
    50007: 'ListItem', 50008: 'List', 50018: 'Tab', 50019: 'TabItem',
    50020: 'Text', 50023: 'Tree', 50024: 'TreeItem', 50025: 'Custom',
    50026: 'Group', 50029: 'DataItem', 50030: 'Document', 50032: 'Window',
    50033: 'Pane', 50036: 'Table',
}
SELECTED_LABEL = '선택된 사용자'


def uia_type_name(control_type) -> str:
    return UIA_TYPE_NAMES.get(control_type, str(control_type))


def find_label(nodes, text):
    """화면에 보이는 제목 요소. 이름이 text 와 똑같은 것을 먼저 찾는다.

    '선택된 사용자 입니다.' 같은 숨은 안내문도 text 를 품고 있다. 실제 화면에서
    그것을 제목으로 잘못 잡아 그 아래만 보다가 진짜 목록을 놓친 일이 있다.
    그래서 이름이 똑같고 화면 안에 있는 것, 화면 안에서 text 를 품은 것,
    어디서든 품은 것 순으로 고른다.
    """
    def plain(node):
        return (node.get('name') or '').strip()

    for test in (lambda n: plain(n) == text and not n.get('offscreen'),
                 lambda n: text in plain(n) and not n.get('offscreen'),
                 lambda n: text in plain(n)):
        for node in nodes:
            if test(node):
                return node
    return None


def repeated_containers(nodes) -> list:
    """같은 종류의 자식이 두 개 넘게 있는 요소. 목록일 가능성이 있다.

    돌려주는 값은 (요소, 자식 종류, 개수, 화면 밖 개수) 목록.
    """
    children = {}
    for node in nodes:
        if node.get('parent') is not None and node['parent'] >= 0:
            children.setdefault(node['parent'], []).append(node)
    found = []
    for parent_id, kids in children.items():
        counts = {}
        for kid in kids:
            counts[kid['type']] = counts.get(kid['type'], 0) + 1
        kid_type, count = max(counts.items(), key=lambda pair: pair[1])
        if count < 2:
            continue
        offscreen = sum(1 for kid in kids if kid['type'] == kid_type and kid.get('offscreen'))
        found.append((nodes[parent_id], kid_type, count, offscreen))
    return found


def guess_selected_list(nodes, split_x: int):
    """[선택된 사용자] 목록으로 보이는 요소를 고른다. 못 고르면 None.

    split_x 는 오른쪽 화살표 버튼의 화면 x 다. 그보다 왼쪽(조직도, 검색 결과)은
    뺀다. '선택된 사용자' 제목이 읽히면 그 아래, 그 열에 있는 것만 본다.
    남은 것 가운데 같은 종류의 줄이 가장 많은 요소가 목록이다. 한 줄 안의 글자나
    단추는 많아야 서너 개라서, 담긴 사람이 그보다 많으면 목록이 이긴다.
    """
    label = find_label(nodes, SELECTED_LABEL)
    right_side = [c for c in repeated_containers(nodes) if c[0]['rect'][0] >= split_x]
    below = right_side
    if label is not None:
        l_left, l_top, _l_right, _l_bottom = label['rect']
        below = [c for c in right_side
                 if c[0]['rect'][1] >= l_top and c[0]['rect'][2] >= l_left]
    # 제목을 잘못 잡아 다 걸러지면 제목 없이 다시 고른다
    candidates = below or right_side
    best, best_score = None, None
    for node, kid_type, count, offscreen in candidates:
        # 줄마다 '이름 [직위]' 가 있는 요소가 목록이다. 그런 줄이 없으면 줄 수로 고른다.
        persons = person_rows(nodes, node['id'], kid_type)
        score = (persons, count)
        if best is None or score > best_score:
            best, best_score = (node, kid_type, count, offscreen), score
    return best


def row_texts(nodes, container_id: int, row_type: int) -> list:
    """목록 요소의 줄마다 그 안의 글을 차례대로 이어 붙인다.

    크롬 화면은 줄 자체 이름에 안쪽 글을 다 붙여 두기도 하고 비워 두기도 해서,
    줄과 그 안쪽 요소의 이름을 모두 모으되 똑같은 글은 한 번만 넣는다.
    """
    children = {}
    for node in nodes:
        children.setdefault(node.get('parent'), []).append(node)
    rows = []
    for row in children.get(container_id, []):
        if row['type'] != row_type:
            continue
        pieces = []
        stack = [row]
        while stack:
            node = stack.pop()
            name = (node.get('name') or '').strip()
            if name and name not in pieces:
                pieces.append(name)
            stack.extend(reversed(children.get(node['id'], [])))
        rows.append(' '.join(pieces))
    return rows


PERSON_ROW = re.compile(r'[가-힣]{2,5}\s*\[')


def person_rows(nodes, container_id: int, row_type: int) -> int:
    """'정수신 [부장교사]' 처럼 이름 뒤에 직위가 붙은 줄의 수."""
    return sum(1 for text in row_texts(nodes, container_id, row_type)
               if PERSON_ROW.search(text))


# ── 동명이인: 검색 결과가 여럿이면 멈춘다 ──────
# 소속 없이 이름만 있거나 같은 학교에 같은 이름이 있으면 검색 결과가 여럿 나온다.
# 첫 사람을 그대로 누르면 엉뚱한 사람이 받는 사람에 들어간다. 그래서 결과가
# 둘 넘으면 누르지 않고 사람이 고르게 한다.
FAIL_SAME_NAME_SKIPPED = '동명이인이라 건너뜀'


def search_count_in(nodes, pattern):
    """화면 읽어 주기로 읽은 요소에서 '검색 결과(N명)' 의 N. 없으면 None.

    화면에 보이는 것을 먼저 본다. 숨은 요소에 예전 수가 남아 있을 수 있다.
    """
    for visible_only in (True, False):
        for node in nodes:
            if visible_only and node.get('offscreen'):
                continue
            found = pattern.search(node.get('name') or '')
            if found:
                return int(found.group(1))
    return None
