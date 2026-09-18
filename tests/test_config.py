import json
import os
import tempfile
import unittest
from unittest import mock

import app_config
from app_config import TARGET_EDUFINE, TARGET_MESSENGER


class ConfigTest(unittest.TestCase):
    def _config_with(self, raw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, 'cfg.json')
        if raw is not None:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(raw, f)
        patcher = mock.patch.object(app_config, 'CONFIG_FILE', path)
        patcher.start()
        self.addCleanup(patcher.stop)
        return app_config.Config(), path

    def test_missing_file_gives_defaults(self):
        cfg, _ = self._config_with(None)
        self.assertEqual(cfg.target, TARGET_MESSENGER)
        self.assertFalse(cfg.is_calibrated())

    def test_legacy_flat_coordinates_are_kept(self):
        # 1.7.x 사용자가 좌표를 다시 잡지 않아도 되어야 한다
        cfg, _ = self._config_with({
            'search_field_x': 10, 'search_field_y': 20,
            'result_first_x': 30, 'result_first_y': 40,
            'add_button_x': 50, 'add_button_y': 60,
            'search_delay': 1.2,
        })
        self.assertTrue(cfg.is_calibrated())
        self.assertEqual(cfg.data['search_field_x'], 10)
        self.assertEqual(cfg.data['search_delay'], 1.2)

    def test_profile_shaped_config_is_read(self):
        # 2.0.0/2.0.1 은 출구별 프로필로 저장했다. 메신저 좌표를 이어받는다.
        cfg, _ = self._config_with({
            'profiles': {
                'messenger': {'search_field_x': 7, 'search_field_y': 8,
                              'result_first_x': 9, 'result_first_y': 10,
                              'add_button_x': 11, 'add_button_y': 12},
                'edufine': {'search_field_x': 999},
            },
            'target': 'edufine',
        })
        self.assertTrue(cfg.is_calibrated())
        self.assertEqual(cfg.data['search_field_x'], 7)
        self.assertEqual(cfg.target, TARGET_EDUFINE)

    def test_save_round_trip(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, 'cfg.json')
        with mock.patch.object(app_config, 'CONFIG_FILE', path):
            cfg = app_config.Config()
            cfg.use_target(TARGET_EDUFINE)
            cfg.data['add_button_x'] = 9
            cfg.edufine['사용자ID'] = 'dungst'
            cfg.save()

            again = app_config.Config()
            self.assertEqual(again.target, TARGET_EDUFINE)
            self.assertEqual(again.data['add_button_x'], 9)
            self.assertEqual(again.edufine['사용자ID'], 'dungst')

    def test_registering_office_is_always_chungbuk_office(self):
        cfg, _ = self._config_with({
            'edufine': {
                '등록교육청코드': 'M100000098',
                '사용자ID': 'dungst',
                '사용자명': '송동석',
            },
        })
        self.assertEqual(
            cfg.edufine['등록교육청코드'],
            app_config.CHUNGBUK_OFFICE_CODE,
        )

    def test_guide_seen_state_is_saved(self):
        cfg, path = self._config_with(None)
        cfg.guides_seen[TARGET_MESSENGER] = True
        cfg.save()

        with mock.patch.object(app_config, 'CONFIG_FILE', path):
            again = app_config.Config()
        self.assertTrue(again.guides_seen[TARGET_MESSENGER])
        self.assertFalse(again.guides_seen[TARGET_EDUFINE])

    def test_edufine_ready(self):
        cfg, _ = self._config_with(None)
        self.assertFalse(cfg.edufine_ready())
        cfg.edufine.update({'사용자ID': 'dungst', '사용자명': '송동석'})
        self.assertTrue(cfg.edufine_ready())

    def test_unknown_target_rejected(self):
        cfg, _ = self._config_with(None)
        with self.assertRaises(ValueError):
            cfg.use_target('무언가')
