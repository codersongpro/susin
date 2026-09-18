"""Small automation status helpers."""

FAIL_NO_USER = '사용자 없음'
FAIL_DUPLICATE = '중복'
FAIL_COORDINATE = '좌표 오류'
FAIL_MANUAL_STOP = '수동 중지'
FAIL_AUTOMATION = '자동화 오류'


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
