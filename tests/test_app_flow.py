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


class _WidgetBase:
    """위젯 스텁. 같은 이름은 같은 mock 을 돌려줘야 호출 기록을 검사할 수 있다."""

    def __init__(self, *args, **kwargs):
        object.__setattr__(self, '_mocks', {})

    def __getattr__(self, name):
        mocks = object.__getattribute__(self, '_mocks')
        if name not in mocks:
            mocks[name] = MagicMock(name=name)
        return mocks[name]

    def __setitem__(self, key, value):
        pass


class _Notebook(_WidgetBase):
    """ttk.Notebook 스텁 — add/hide/insert 를 진짜처럼 흉내 낸다.

    tkinter 는 등록하지 않은 탭에 hide()/insert() 를 부르면 TclError 를 던진다.
    스텁이 조용히 넘어가면, 탭이 하나만 남는 버그를 여기서 못 잡는다. 실제로 놓쳤다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, 'managed', [])     # 등록된 순서
        object.__setattr__(self, 'visible', [])     # 화면에 보이는 순서

    def add(self, tab, **kwargs):
        if tab not in self.managed:
            self.managed.append(tab)
        if tab not in self.visible:
            self.visible.append(tab)

    def forget(self, tab):
        if tab not in self.managed:
            raise RuntimeError('등록되지 않은 탭은 뗄 수 없습니다')
        self.managed.remove(tab)
        if tab in self.visible:
            self.visible.remove(tab)

    def hide(self, tab):
        if tab not in self.managed:
            raise RuntimeError('등록되지 않은 탭은 숨길 수 없습니다')
        if tab in self.visible:
            self.visible.remove(tab)

    def insert(self, index, tab, **kwargs):
        if tab not in self.managed:
            raise RuntimeError('등록되지 않은 탭은 배치할 수 없습니다')
        # 실제 Tk 에서는 insert 가 감춰 둔 탭까지 되살렸다. 그래서 이 방식을 버렸다.
        if tab in self.visible:
            self.visible.remove(tab)
        if index == 'end':
            self.visible.append(tab)
        else:
            self.visible.insert(int(index), tab)

    def tabs(self):
        return list(self.visible)


class _Widget(_WidgetBase):
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
    for attr in ('Frame', 'Entry', 'Scrollbar', 'Style', 'LabelFrame',
                 'Progressbar', 'Spinbox', 'Label', 'Button', 'Combobox'):
        setattr(tk.ttk, attr, _Widget)
    tk.ttk.Notebook = _Notebook
    return saved


def restore(saved):
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def edufine_module():
    import edufine
    return edufine


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
            self.app._choose_target(target)
            self.assertEqual(self.app.config.target, target)
            self.assertEqual(self.app.target_var.get(), target)

    def test_each_target_shows_its_own_tabs(self):
        """탭이 1번만 남고 사라지던 버그의 회귀 방지선."""
        from app_config import TARGET_EDUFINE, TARGET_MESSENGER

        self.app._choose_target(TARGET_MESSENGER)
        visible = self.app.nb.tabs()
        self.assertIn(self.app.tab_input, visible)
        for tab, _ in self.app.messenger_tabs:
            self.assertIn(tab, visible, '소통메신저 탭이 없습니다')
        for tab, _ in self.app.edufine_tabs:
            self.assertNotIn(tab, visible)
        self.assertIs(visible[-1], self.app.tab_help, '사용 방법은 맨 뒤여야 합니다')
        self.assertEqual(len(visible), 4)

        self.app._choose_target(TARGET_EDUFINE)
        visible = self.app.nb.tabs()
        self.assertIn(self.app.tab_input, visible)
        for tab, _ in self.app.edufine_tabs:
            self.assertIn(tab, visible, '에듀파인 탭이 없습니다')
        for tab, _ in self.app.messenger_tabs:
            self.assertNotIn(tab, visible)
        self.assertIs(visible[-1], self.app.tab_help)
        self.assertEqual(len(visible), 3)

    def test_switching_back_and_forth_keeps_tabs(self):
        from app_config import TARGET_EDUFINE, TARGET_MESSENGER
        for target in (TARGET_MESSENGER, TARGET_EDUFINE) * 3:
            self.app._choose_target(target)
            self.assertGreaterEqual(len(self.app.nb.tabs()), 3,
                                    f'{target} 에서 탭이 사라졌습니다')

    def test_edufine_buttons_are_shown_and_hidden(self):
        """pack 을 빠뜨려 버튼이 아예 안 보이던 적이 있다."""
        from app_config import TARGET_EDUFINE, TARGET_MESSENGER

        self.app._choose_target(TARGET_EDUFINE)
        for name in ('browse_btn', 'make_excel_btn'):
            btn = getattr(self.app, name)
            self.assertTrue(btn.pack.called, f'{name} 이 화면에 붙지 않았습니다')
            btn.pack.reset_mock()
            btn.pack_forget.reset_mock()

        self.app._choose_target(TARGET_MESSENGER)
        for name in ('browse_btn', 'make_excel_btn'):
            btn = getattr(self.app, name)
            self.assertTrue(btn.pack_forget.called, f'{name} 이 감춰지지 않았습니다')

    def test_edited_list_is_what_reaches_the_excel(self):
        """목록에서 지우고 고친 결과가 그대로 엑셀로 가야 한다."""
        self.parse('학성초\n한천초\n백곡초')
        self.assertEqual(len(self.app.names_list), 3)

        # 가운데 항목을 지운다
        self.app.parsed_list.curselection = lambda: (1,)
        self.app._delete_selected()
        self.assertEqual([i['org'] for i in self.app.names_list],
                         ['충청북도진천교육지원청 학성초등학교',
                          '충청북도진천교육지원청 백곡초등학교'])

        # 지운 항목은 엑셀로 넘어가는 목록에도 없어야 한다
        ready, missing = self.app._split_confirmed()
        self.assertEqual([r['name'] for r in ready],
                         ['충청북도진천교육지원청 학성초등학교',
                          '충청북도진천교육지원청 백곡초등학교'])
        self.assertEqual(missing, [])
        self.assertTrue(all('한천초' not in r['name'] for r in ready))

    def test_confirming_an_ambiguous_row_feeds_the_excel(self):
        self.parse('행정과')
        row = self.app.names_list[0]
        self.assertEqual(row['grade'], 'ambiguous')
        self.assertEqual(self.app._split_confirmed()[0], [])

        # 사용자가 후보 하나를 고른 것과 같은 상태로 만든다
        row.update({'org': '충청북도청주교육지원청 행정과', 'grade': 'exact',
                    'search': '충청북도청주교육지원청 행정과', 'candidates': []})
        self.app._after_list_edit()

        ready, _ = self.app._split_confirmed()
        self.assertEqual([r['name'] for r in ready],
                         ['충청북도청주교육지원청 행정과'])

    def test_blank_template_exists_to_be_saved(self):
        import os
        self.assertTrue(os.path.exists(edufine_module().TEMPLATE_FILE),
                        '동봉된 빈 양식이 없습니다')

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


class VersionFileTest(unittest.TestCase):
    """exe 버전 정보 리소스 — 비어 있으면 백신 오탐이 늘어난다."""

    @classmethod
    def setUpClass(cls):
        import os
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
        import make_version_file
        cls.mod = make_version_file

    def test_version_follows_the_app(self):
        # main 은 tkinter 를 쓰므로 스텁을 끼워 읽는다
        saved = install_tk_stubs()
        try:
            import main as app_module
            self.assertEqual(self.mod.read_app_version(), app_module.APP_VERSION)
        finally:
            restore(saved)

    def test_tuple_padding(self):
        self.assertEqual(self.mod.version_tuple('2.0.1'), (2, 0, 1, 0))
        self.assertEqual(self.mod.version_tuple('2.1'), (2, 1, 0, 0))

    def test_rendered_file_is_valid_python_and_filled_in(self):
        text = self.mod.render('2.0.1')
        compile(text, 'version_info.txt', 'eval')      # PyInstaller 가 eval 한다
        for needed in ('ProductName', '신통픽', 'CompanyName', 'FileDescription',
                       "StringStruct('FileVersion', '2.0.1')"):
            self.assertIn(needed, text, needed)
        self.assertIn('(2, 0, 1, 0)', text)
