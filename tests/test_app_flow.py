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
        object.__setattr__(self, 'master', args[0] if args else None)

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

    def test_picker_lives_above_the_tabs(self):
        """도구 선택은 탭 안이 아니라 창 맨 위에 있어야 어느 화면에서든 바꾼다."""
        for target, (card, title, desc) in self.app.target_cards.items():
            picker = card.master
            self.assertIsNot(picker, self.app.tab_input,
                             f'{target} 카드가 명단 입력 탭 안에 있습니다')
            self.assertIs(picker.master, self.app.root,
                          f'{target} 카드를 담은 틀이 창의 직계 자식이 아닙니다')

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


class CaptureEnterTest(unittest.TestCase):
    """위치 캡처에서 Enter 가 먹는지.

    소통메신저를 눌러 앞으로 꺼내면 캡처 창이 키를 못 받아 Enter 로 확정이
    안 됐다. 그래서 창 밖의 Enter 도 보도록 고쳤다.
    """

    @classmethod
    def setUpClass(cls):
        cls._saved = install_tk_stubs()
        import main as app_module
        cls.app_module = app_module

    @classmethod
    def tearDownClass(cls):
        restore(cls._saved)

    def _dialog(self, keys):
        """키 상태를 흉내 낸 캡처 창. keys 는 폴링 때마다 돌려줄 값의 목록."""
        m = self.app_module
        dlg = m.CaptureDialog.__new__(m.CaptureDialog)
        dlg._finished = False
        dlg._enter_released = False
        dlg.captured = []
        dlg.on_captured = lambda x, y: dlg.captured.append((x, y))
        dlg.status = MagicMock()
        dlg.winfo_exists = lambda: True
        dlg.destroy = MagicMock()
        dlg.after = MagicMock()
        dlg.grab_release = MagicMock()
        return dlg

    def _run(self, dlg, key_sequence):
        """key_sequence 의 상태를 하나씩 먹이며 폴링을 돌린다."""
        m = self.app_module
        pos = types.SimpleNamespace(x=100, y=200)
        real_key, real_auto = m.key_is_down, m.pyautogui
        m.pyautogui = types.SimpleNamespace(position=lambda: pos)
        try:
            for down in key_sequence:
                m.key_is_down = lambda vk, d=down: d.get(vk, False)
                dlg._poll_position()
                if dlg._finished or dlg.destroy.called:
                    break
        finally:
            m.key_is_down, m.pyautogui = real_key, real_auto

    def test_enter_outside_the_window_confirms(self):
        m = self.app_module
        dlg = self._dialog(None)
        dlg._enter_released = True
        self._run(dlg, [{}, {m.VK_RETURN: True}])
        self.assertEqual(dlg.captured, [(100, 200)])

    def test_enter_still_held_from_the_button_does_not_confirm(self):
        """[캡처 시작] 을 Enter 로 눌렀다면 그 Enter 로 바로 확정되면 안 된다."""
        m = self.app_module
        dlg = self._dialog(None)
        dlg._enter_released = False
        self._run(dlg, [{m.VK_RETURN: True}, {m.VK_RETURN: True}])
        self.assertEqual(dlg.captured, [], '누른 채로 있던 Enter 가 확정됐습니다')
        # 한 번 뗐다가 다시 누르면 그때는 확정된다
        self._run(dlg, [{}, {m.VK_RETURN: True}])
        self.assertEqual(dlg.captured, [(100, 200)])

    def test_escape_outside_the_window_cancels(self):
        m = self.app_module
        dlg = self._dialog(None)
        dlg._enter_released = True
        self._run(dlg, [{m.VK_ESCAPE: True}])
        self.assertTrue(dlg.destroy.called)
        self.assertEqual(dlg.captured, [])

    def test_capture_releases_the_mouse_grab(self):
        """캡처 중에는 마우스를 놓아야 소통메신저 위에서 마우스가 먹는다."""
        m = self.app_module
        dlg = self._dialog(None)
        dlg.start_btn = MagicMock()
        dlg.bind = MagicMock()
        dlg.attributes = MagicMock()
        dlg.focus_force = MagicMock()
        real_key, real_auto = m.key_is_down, m.pyautogui
        m.key_is_down = lambda vk: False
        m.pyautogui = types.SimpleNamespace(
            position=lambda: types.SimpleNamespace(x=1, y=2))
        try:
            dlg._begin()
        finally:
            m.key_is_down, m.pyautogui = real_key, real_auto
        self.assertTrue(dlg.grab_release.called,
                        '캡처를 시작하면서 마우스를 놓지 않았습니다')
        dlg.attributes.assert_called_with('-topmost', True)

    def test_done_closes_even_if_saving_fails(self):
        """좌표를 넘기다 터져도 창이 남아 앱을 막으면 안 된다."""
        m = self.app_module
        dlg = self._dialog(None)
        dlg.on_captured = MagicMock(side_effect=RuntimeError('저장 실패'))
        dlg._done(types.SimpleNamespace(x=10, y=20))
        self.assertTrue(dlg.after.called, '창을 닫는 예약이 걸리지 않았습니다')
        self.assertTrue(dlg.grab_release.called)

    def test_key_is_down_is_false_without_pywin32(self):
        m = self.app_module
        real = m.win32api
        m.win32api = None
        try:
            self.assertFalse(m.key_is_down(m.VK_RETURN))
        finally:
            m.win32api = real


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


class VersionConsistencyTest(unittest.TestCase):
    """버전이 세 곳에 흩어져 있어 어긋나기 쉽다. 실제로 v1.7.2 가 남아 있었다."""

    def setUp(self):
        import os
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
        import bump_version
        self.mod = bump_version

    def test_landing_page_matches_the_app(self):
        version = self.mod.read_version()
        found = self.mod.html_versions()
        self.assertTrue(found, '랜딩페이지에서 버전 표기를 찾지 못했습니다')
        for shown in found:
            self.assertEqual(shown, version,
                             f'랜딩페이지 v{shown} 와 앱 v{version} 이 다릅니다')

    def test_changelog_has_the_current_version(self):
        version = self.mod.read_version()
        self.assertIn(version, self.mod.changelog_versions(),
                      f'CHANGELOG.md 에 "## v{version}" 단락이 없습니다')

    def test_changelog_is_newest_first(self):
        def key(v):
            return [int(p) for p in v.split('.')]
        versions = self.mod.changelog_versions()
        self.assertEqual(versions, sorted(versions, key=key, reverse=True),
                         'CHANGELOG 는 최신 버전이 맨 위여야 합니다')


class ReleaseNotesTest(unittest.TestCase):
    def setUp(self):
        import os
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
        import make_release_notes
        self.mod = make_release_notes

    def test_picks_the_right_section(self):
        text = ('## v2.0.0\n첫판\n\n## v2.1.0\n둘째판\n')
        self.assertEqual(self.mod.section_for('v2.1.0', text), '둘째판')
        self.assertEqual(self.mod.section_for('2.0.0', text), '첫판')
        self.assertIsNone(self.mod.section_for('v9.9.9', text))

    def test_body_includes_changelog_and_footer(self):
        version = __import__('bump_version').read_version()
        body = self.mod.build(version)
        self.assertIn('백신이 막는다면', body, '고정 안내문이 빠졌습니다')
        self.assertIn('받는 방법', body)
        self.assertNotIn('CHANGELOG.md 에 없습니다', body,
                         '현재 버전의 변경 내용이 CHANGELOG 에 없습니다')
