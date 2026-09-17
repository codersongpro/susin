import json
import os
import tempfile
import unittest
from unittest import mock

import app_config
from app_config import TARGET_EDUFINE, TARGET_MESSENGER


class ConfigTest(unittest.TestCase):
    def _config_with(self, raw):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'cfg.json')
            if raw is not None:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(raw, f)
            with mock.patch.object(app_config, 'CONFIG_FILE', path):
                return app_config.Config(), path

    def test_missing_file_gives_defaults(self):
        cfg, _ = self._config_with(None)
        self.assertEqual(cfg.target, TARGET_MESSENGER)
        self.assertFalse(cfg.is_calibrated())

    def test_legacy_flat_coordinates_migrate_to_messenger(self):
        # 기존 사용자가 좌표를 다시 잡지 않아도 되어야 한다
        cfg, _ = self._config_with({
            'search_field_x': 10, 'search_field_y': 20,
            'result_first_x': 30, 'result_first_y': 40,
            'add_button_x': 50, 'add_button_y': 60,
            'search_delay': 1.2,
        })
        self.assertTrue(cfg.is_calibrated(TARGET_MESSENGER))
        self.assertFalse(cfg.is_calibrated(TARGET_EDUFINE))
        self.assertEqual(cfg.data['search_field_x'], 10)
        self.assertEqual(cfg.data['search_delay'], 1.2)

    def test_profiles_are_independent(self):
        cfg, _ = self._config_with(None)
        cfg.data['search_field_x'] = 111
        cfg.use_target(TARGET_EDUFINE)
        self.assertIsNone(cfg.data['search_field_x'])
        cfg.data['search_field_x'] = 222
        cfg.use_target(TARGET_MESSENGER)
        self.assertEqual(cfg.data['search_field_x'], 111)

    def test_save_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'cfg.json')
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

    def test_edufine_ready(self):
        cfg, _ = self._config_with(None)
        self.assertFalse(cfg.edufine_ready())
        cfg.edufine.update({'등록교육청코드': 'M100000098',
                            '사용자ID': 'dungst', '사용자명': '송동석'})
        self.assertTrue(cfg.edufine_ready())


if __name__ == '__main__':
    unittest.main()
