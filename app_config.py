"""Persistent application configuration.

좌표는 출구별로 따로 저장한다. 소통메신저의 [사용자 선택] 창과 에듀파인의
[수신자 지정] 팝업은 화면이 다르지만 구조는 같다 — 검색칸 / 첫 결과 / 추가 버튼.
그래서 같은 자동화 엔진을 쓰되 좌표만 프로필로 나눈다.

data 는 '현재 프로필'을 가리키는 창이라, 기존 config.data['search_field_x'] 코드는
그대로 동작한다.
"""

import json
import logging
import os


CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".chungbuk_auto_config.json")

TARGET_MESSENGER = 'messenger'
TARGET_EDUFINE = 'edufine'
TARGETS = (TARGET_MESSENGER, TARGET_EDUFINE)

TARGET_LABELS = {
    TARGET_MESSENGER: '소통메신저',
    TARGET_EDUFINE: '에듀파인',
}

# 좌표 프로필에 들어가는 키
PROFILE_DEFAULTS = {
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
    DEFAULTS = PROFILE_DEFAULTS      # 하위 호환

    def __init__(self):
        self.profiles = {t: dict(PROFILE_DEFAULTS) for t in TARGETS}
        self.edufine = dict(EDUFINE_DEFAULTS)
        self.target = TARGET_MESSENGER
        self._load()

    # ── 현재 프로필 ──────────────────────────
    @property
    def data(self) -> dict:
        """현재 출구의 좌표 설정. 기존 호출부가 이 이름으로 접근한다."""
        return self.profiles[self.target]

    def use_target(self, target: str):
        if target not in TARGETS:
            raise ValueError(f'알 수 없는 출구: {target}')
        self.target = target

    def profile(self, target: str) -> dict:
        return self.profiles[target]

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

        if 'profiles' in raw:
            for name, values in (raw.get('profiles') or {}).items():
                if name in self.profiles and isinstance(values, dict):
                    self.profiles[name].update(values)
        else:
            # 1.7.x 이전: 좌표가 최상위에 평평하게 있었다. 메신저 프로필로 옮긴다.
            # 이미 좌표를 잡아 둔 사용자가 다시 설정하지 않아도 되게 한다.
            legacy = {k: v for k, v in raw.items() if k in PROFILE_DEFAULTS}
            if legacy:
                self.profiles[TARGET_MESSENGER].update(legacy)

        if isinstance(raw.get('edufine'), dict):
            self.edufine.update(
                {k: v for k, v in raw['edufine'].items() if k in EDUFINE_DEFAULTS})

        if raw.get('target') in TARGETS:
            self.target = raw['target']

    def save(self):
        payload = {
            'profiles': self.profiles,
            'edufine': self.edufine,
            'target': self.target,
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ── 상태 확인 ────────────────────────────
    def is_calibrated(self, target: str = None) -> bool:
        values = self.profiles[target or self.target]
        return all(values.get(k) is not None for k in CALIBRATION_KEYS)

    def edufine_ready(self) -> bool:
        """일괄등록 엑셀을 만들 수 있을 만큼 개인 설정이 채워졌는가."""
        return all(str(self.edufine.get(k, '')).strip()
                   for k in ('등록교육청코드', '사용자ID', '사용자명'))
