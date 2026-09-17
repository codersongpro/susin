"""앱 흐름 테스트 — tkinter 없이 돈다.

화면은 못 그려 보지만 속성 이름 오타와 로직 오류는 여기서 잡힌다.
Windows 러너까지 가서야 아는 일이 없도록, 리눅스 테스트 단계에서 먼저 걸른다.
실제 위젯 동작(탭 숨김, 콤보 목록)은 tools/smoke_gui.py 가 CI 에서 확인한다.
"""

import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock


class _Var:
    def __init__(self, master=None, value=None, **kwargs):
        self._value = '' if value is None else value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def trace_add(self, *args, **kwargs):
        pass


class _Text:
    def __init__(self, *args, **kwargs):
        self._text = ''

    def insert(self, index, text):
        self._text += text

    def get(self, *args, **kwargs):
        return self._text

    def delete(self, *args, **kwargs):
        self._text = ''

    def __getattr__(self, name):
        return MagicMock()


class _Listbox:
    def __init__(self, *args, **kwargs):
        self.items = []

    def insert(self, index, value):
        self.items.append(value)

    def delete(self, *args, **kwargs):
        self.items = []

    def curselection(self):
        return ()

    def get(self, index):
        return self.items[index]

    def __getattr__(self, name):
        return MagicMock()


class _Widget:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return MagicMock()

    def __setitem__(self, key, value):
        pass


def install_tk_stubs():
    """tkinter 를 동작하는 스텁으로 갈아끼운다. 이미 깔려 있어도 스텁을 쓴다."""
    names = ('tkinter', 'tkinter.ttk', 'tkinter.messagebox',
             'tkinter.scrolledtext', 'tkinter.filedialog')
    saved = {n: sys.modules.get(n) for n in names}
    saved['main'] = sys.modules.get('main')

    for name in names:
        module = types.ModuleType(name)
        module.__getattr__ = lambda attr, _m=module: MagicMock()
        sys.modules[name] = module

    tk = sys.modules['tkinter']
    for attr in ('Tk', 'Toplevel', 'Frame', 'Label', 'Button', 'Entry', 'Menu',
                 'Radiobutton', 'Checkbutton', 'Canvas', 'PhotoImage'):
        setattr(tk, attr, _Widget)
    tk.StringVar = tk.DoubleVar = tk.BooleanVar = tk.IntVar = _Var
    tk.Text = _Text
    tk.Listbox = _Listbox
    tk.ttk = sys.modules['tkinter.ttk']
    tk.messagebox = sys.modules['tkinter.messagebox']
    tk.scrolledtext = sys.modules['tkinter.scrolledtext']
    tk.filedialog = sys.modules['tkinter.filedialog']
    tk.scrolledtext.ScrolledText = _Text
    for attr in ('Frame', 'Notebook', 'Entry', 'Scrollbar', 'Style', 'LabelFrame',
                 'Progressbar', 'Spinbox', 'Label', 'Button', 'Combobox'):
        setattr(tk.ttk, attr, _Widget)
    return saved


def restore(saved):
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class AppFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 앱은 설정을 바꿀 때마다 저장한다. 테스트가 개발자의 실제 설정을
        # 덮어쓰지 않도록 임시 경로로 돌려놓는다.
        import app_config
        cls._tmp = tempfile.TemporaryDirectory()
        cls._real_config = app_config.CONFIG_FILE
        app_config.CONFIG_FILE = os.path.join(cls._tmp.name, 'config.json')

        cls._saved = install_tk_stubs()
        import tkinter
        import main as app_module
        cls.app_module = app_module
        cls.app = app_module.App(tkinter.Tk())

    @classmethod
    def tearDownClass(cls):
        restore(cls._saved)
        import app_config
        app_config.CONFIG_FILE = cls._real_config
        cls._tmp.cleanup()

    def test_config_is_isolated(self):
        import app_config
        self.assertNotEqual(app_config.CONFIG_FILE, self._real_config)
        self.assertFalse(os.path.exists(self._real_config),
                         '테스트가 실제 설정 파일을 만들었습니다')

    def setUp(self):
        from app_config import TARGET_EDUFINE
        self.app.target_var.set(TARGET_EDUFINE)
        self.app.config.use_target(TARGET_EDUFINE)
        self.app._apply_target()
        self.app.input_text.delete('1.0', 'end')
        self.app.names_list.clear()

    def parse(self, text):
        self.app.input_text.delete('1.0', 'end')
        self.app.input_text.insert('1.0', text)
        self.app._parse()
        return self.app.names_list

    def test_app_builds(self):
        self.assertEqual(self.app_module.APP_NAME, '신통픽')

    def test_target_switching_does_not_crash(self):
        from app_config import TARGET_EDUFINE, TARGET_MESSENGER
        for target in (TARGET_MESSENGER, TARGET_EDUFINE, TARGET_MESSENGER):
            self.app.target_var.set(target)
            self.app._on_target_change()
            self.assertEqual(self.app.config.target, target)

    def test_switching_target_clears_the_list(self):
        from app_config import TARGET_MESSENGER
        self.parse('학성초')
        self.assertTrue(self.app.names_list)
        self.app.target_var.set(TARGET_MESSENGER)
        self.app._on_target_change()
        self.assertEqual(self.app.names_list, [])

    def test_org_parsing_grades(self):
        rows = self.parse('학성초\n청주교육지원청 행정과\n행정과')
        grades = [r['grade'] for r in rows]
        self.assertEqual(grades.count('exact'), 2, grades)
        self.assertIn('ambiguous', grades, grades)

    def test_only_confirmed_rows_are_exported(self):
        self.parse('학성초\n행정과')
        ready, missing = self.app._split_confirmed()
        self.assertEqual([r['name'] for r in ready],
                         ['충청북도진천교육지원청 학성초등학교'])
        self.assertEqual(missing, [])          # 미확정 행은 애초에 넘어가지 않는다

    def test_department_keeps_its_full_path(self):
        rows = self.parse('청주교육지원청 행정과')
        self.assertEqual(rows[0]['org'], '충청북도청주교육지원청 행정과')

    def test_messenger_parsing_still_works(self):
        from app_config import TARGET_MESSENGER
        self.app.target_var.set(TARGET_MESSENGER)
        self.app._on_target_change()
        rows = self.parse('충주중학교\t홍길동')
        self.assertEqual(rows, [{'org': '충주중학교', 'name': '홍길동'}])

    def test_registering_office_choices_are_loaded(self):
        names = [n for n, _ in self.app.office_choices]
        self.assertIn('충청북도진천교육지원청', names)

    def test_picking_an_office_fills_the_code(self):
        self.app.office_var.set('충청북도진천교육지원청')
        self.app._on_office_selected()
        self.assertEqual(self.app.edufine_vars['등록교육청코드'].get(), 'M100000098')


if __name__ == '__main__':
    unittest.main()


class SmokeScriptTest(unittest.TestCase):
    """CI 의 스모크 스크립트 자체가 깨지지 않는지."""

    def test_runs_under_a_non_utf8_console(self):
        # Windows 러너 콘솔은 cp1252 다. 한글 확인 메시지를 찍다가 죽으면
        # 앱은 멀쩡한데 빌드가 실패한다 (실제로 한 번 그랬다).
        import os
        import subprocess

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(root, 'tools', 'smoke_gui.py')
        source = open(script, encoding='utf-8').read()
        self.assertIn('reconfigure', source,
                      '출력 인코딩 보정이 빠졌습니다')

        # 보정 부분만 떼어 cp1252 환경에서 실제로 돌려 본다
        probe = (
            'import sys\n'
            'for stream in (sys.stdout, sys.stderr):\n'
            '    try:\n'
            "        stream.reconfigure(encoding='utf-8', errors='replace')\n"
            '    except (AttributeError, ValueError):\n'
            '        pass\n'
            "print('한글 출력 확인')\n"
        )
        result = subprocess.run(
            [sys.executable, '-c', probe],
            capture_output=True, text=True,
            env=dict(os.environ, PYTHONIOENCODING='cp1252'),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('한글 출력 확인', result.stdout)
