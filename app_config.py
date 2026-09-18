"""Persistent application configuration.

좌표는 소통픽(소통메신저)에서만 쓴다. 수신픽(에듀파인)은 엑셀을 만들어 올리는
방식이라 마우스 위치를 잡을 일이 없다.

data 는 예전처럼 좌표를 담은 평평한 딕셔너리라, 기존 호출부가 그대로 동작한다.
"""

import json
import logging
import os


CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".chungbuk_auto_config.json")

TARGET_MESSENGER = 'messenger'
TARGET_EDUFINE = 'edufine'
TARGETS = (TARGET_MESSENGER, TARGET_EDUFINE)

# 신통픽은 두 도구를 합친 것이다. 화면에서는 각각의 이름으로 부른다.
TARGET_LABELS = {
    TARGET_MESSENGER: '소통픽',
    TARGET_EDUFINE: '수신픽',
}

TARGET_SYSTEMS = {
    TARGET_MESSENGER: '소통메신저',
    TARGET_EDUFINE: '에듀파인',
}

TARGET_SUMMARIES = {
    TARGET_MESSENGER: '소통메신저에서 쪽지·대화 상대를 자동으로 골라 담습니다',
    TARGET_EDUFINE: '에듀파인 공문 수신그룹 엑셀을 만들어 올립니다',
}

COORD_DEFAULTS = {
    'search_field_x': None, 'search_field_y': None,
    'result_first_x': None, 'result_first_y': None,
    'add_button_x':   None, 'add_button_y':   None,
    'empty_pixel_rgb': None,
    'search_delay': 0.5,
    'manual_confirm': True,
}

# 에듀파인 일괄등록 양식에 매번 들어가지만 사람마다 고정인 값
EDUFINE_DEFAULTS = {
    '등록교육청코드': '',
    '사용자ID': '',
    '사용자명': '',
    '그룹명': '',
    '그룹기호': '',
}

CALIBRATION_KEYS = ('search_field_x', 'search_field_y',
                    'result_first_x', 'result_first_y',
                    'add_button_x', 'add_button_y')


class Config:
    DEFAULTS = COORD_DEFAULTS      # 하위 호환

    def __init__(self):
        self.data = dict(COORD_DEFAULTS)
        self.edufine = dict(EDUFINE_DEFAULTS)
        self.target = TARGET_MESSENGER
        self._load()

    def use_target(self, target: str):
        if target not in TARGETS:
            raise ValueError(f'알 수 없는 도구: {target}')
        self.target = target

    # ── 저장/불러오기 ────────────────────────
    def _load(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                return
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except Exception as exc:
            logging.warning("설정 파일을 읽지 못했습니다: %s", exc)
            return

        # 2.0.x 는 좌표를 도구별 프로필로 나눠 뒀다. 수신픽 좌표는 이제 쓰지 않으므로
        # 소통픽 것만 가져온다. 그 이전 판은 최상위에 평평하게 있었다.
        source = (raw.get('profiles') or {}).get(TARGET_MESSENGER)
        if not isinstance(source, dict):
            source = raw
        self.data.update({k: v for k, v in source.items() if k in COORD_DEFAULTS})

        if isinstance(raw.get('edufine'), dict):
            self.edufine.update(
                {k: v for k, v in raw['edufine'].items() if k in EDUFINE_DEFAULTS})

        if raw.get('target') in TARGETS:
            self.target = raw['target']

    def save(self):
        payload = {
            'coords': self.data,
            'edufine': self.edufine,
            'target': self.target,
        }
        # 예전 판이 읽을 수 있도록 좌표를 최상위에도 둔다
        payload.update(self.data)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ── 상태 확인 ────────────────────────────
    def is_calibrated(self) -> bool:
        return all(self.data.get(k) is not None for k in CALIBRATION_KEYS)

    def edufine_ready(self) -> bool:
        """일괄등록 엑셀을 만들 수 있을 만큼 개인 설정이 채워졌는가."""
        return all(str(self.edufine.get(k, '')).strip()
                   for k in ('등록교육청코드', '사용자ID', '사용자명'))
