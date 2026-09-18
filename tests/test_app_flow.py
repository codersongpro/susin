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
from unittest.mock import MagicMock, patch


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

    def winfo_rootx(self):
        return 100

    def winfo_rooty(self):
        return 150

    def winfo_width(self):
        return 500

    def winfo_height(self):
        return 180

    def __getattr__(self, name):
        return MagicMock()


class _Listbox:
    def __init__(self, *args, **kwargs):
        self.items = []
        self._mocks = {}

    def insert(self, index, value):
        self.items.append(value)

    def delete(self, *args, **kwargs):
        self.items = []

    def curselection(self):
        return ()

    def get(self, index):
        return self.items[index]

    def winfo_rootx(self):
        return 100

    def winfo_rooty(self):
        return 360

    def winfo_width(self):
        return 500

    def winfo_height(self):
        return 200

    def __getattr__(self, name):
        if name not in self._mocks:
            self._mocks[name] = MagicMock(name=name)
        return self._mocks[name]


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

    def winfo_rootx(self):
        return 80

    def winfo_rooty(self):
        return 120

    def winfo_width(self):
        return 420

    def winfo_height(self):
        return 120

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def winfo_exists(self):
        return True


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


class _FakeShot:
    """pyautogui.screenshot 이 돌려주는 PIL 이미지 흉내."""

    def __init__(self, pixels, width, height):
        self._pixels = list(pixels)
        self.size = (width, height)

    def convert(self, mode):
        return self

    def getdata(self):
        return list(self._pixels)


def _fake_pixels(width, height, painted, color=(40, 40, 40)):
    return [
        color if (row, col) in painted else (255, 255, 255)
        for row in range(height)
        for col in range(width)
    ]


def _fake_screen(pixels, width, height, screen=(1920, 1080)):
    return types.SimpleNamespace(
        size=lambda: screen,
        screenshot=lambda region=None: _FakeShot(pixels, width, height),
        pixel=lambda x, y: (255, 255, 255),
    )


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
        self.assertTrue(
            os.path.abspath(app_config.CONFIG_FILE).startswith(
                os.path.abspath(self._tmp.name)),
            '테스트 설정 파일이 임시 폴더 밖을 가리킵니다',
        )

    def setUp(self):
        from app_config import TARGET_EDUFINE
        self.app.target_var.set(TARGET_EDUFINE)
        self.app.config.use_target(TARGET_EDUFINE)
        self.app._apply_target()
        self.app.input_text.delete('1.0', 'end')
        self.app.names_list.clear()
        self.app.last_org_duplicates = []

    def parse(self, text):
        self.app.input_text.delete('1.0', 'end')
        self.app.input_text.insert('1.0', text)
        self.app._parse()
        return self.app.names_list

    def test_app_builds(self):
        self.assertEqual(self.app_module.APP_NAME, '신통픽')

    def test_each_product_has_its_own_video_guide(self):
        self.assertEqual(
            self.app_module.GUIDE_VIDEO_URLS['messenger'],
            'https://youtu.be/shZnB5NRN5g',
        )
        self.assertEqual(
            self.app_module.GUIDE_VIDEO_URLS['edufine'],
            'https://youtu.be/IcFX3UKdMEw',
        )
        self.assertIn('소통픽 사용법', self.app_module.HELP_TEXTS['messenger'])
        self.assertNotIn(
            '■ 에듀파인 — 수신그룹 일괄등록',
            self.app_module.HELP_TEXTS['messenger'],
        )
        self.assertIn('수신픽 사용법', self.app_module.HELP_TEXTS['edufine'])
        self.assertIn(
            '[확인 필요 기관 일괄 수정]',
            self.app_module.HELP_TEXTS['edufine'],
        )

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
        messenger_help, messenger_title = self.app.help_tabs[TARGET_MESSENGER]
        self.assertIs(visible[-1], messenger_help, '소통픽 사용법은 맨 뒤여야 합니다')
        self.assertIn('소통픽 사용법', messenger_title)
        self.assertEqual(len(visible), 4)

        self.app._choose_target(TARGET_EDUFINE)
        visible = self.app.nb.tabs()
        self.assertIn(self.app.tab_input, visible)
        for tab, _ in self.app.edufine_tabs:
            self.assertIn(tab, visible, '에듀파인 탭이 없습니다')
        for tab, _ in self.app.messenger_tabs:
            self.assertNotIn(tab, visible)
        edufine_help, edufine_title = self.app.help_tabs[TARGET_EDUFINE]
        self.assertIs(visible[-1], edufine_help)
        self.assertIn('수신픽 사용법', edufine_title)
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

        self.assertFalse(
            hasattr(self.app, 'make_excel_btn'),
            '명단 입력 화면에 수신그룹 엑셀 만들기 버튼이 다시 생겼습니다',
        )

        self.app._choose_target(TARGET_EDUFINE)
        for name in ('browse_btn', 'bulk_fix_btn', 'org_history_btn'):
            btn = getattr(self.app, name)
            self.assertTrue(btn.pack.called, f'{name} 이 화면에 붙지 않았습니다')
            btn.pack.reset_mock()
            btn.pack_forget.reset_mock()

        self.app._choose_target(TARGET_MESSENGER)
        for name in ('browse_btn', 'bulk_fix_btn', 'org_history_btn'):
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

    def test_duplicate_orgs_are_counted_named_and_kept_once(self):
        before = len(self.app.config.org_extract_history)
        rows = self.parse('학성초\n학성초\n학성초\n한천초')

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['source_count'], 3)
        self.assertEqual(
            self.app.last_org_duplicates,
            [{'name': '학성초등학교', 'count': 3}],
        )
        self.assertIn('입력 3회', self.app.parsed_list.items[0])

        history = self.app.config.org_extract_history
        self.assertEqual(len(history), before + 1)
        self.assertEqual(history[-1]['duplicates'][0]['count'], 3)
        self.assertEqual(history[-1]['items'][0]['name'], '학성초등학교')

    def test_review_required_orgs_are_red_and_bulk_fix_is_enabled(self):
        self.app.parsed_list.itemconfig.reset_mock()
        row = self.parse('행정과')[0]

        self.assertTrue(self.app._org_needs_review(row))
        self.app.parsed_list.itemconfig.assert_called_with(
            'end', {'bg': '#FFEBEE', 'fg': '#B71C1C'})
        self.app.bulk_fix_btn.config.assert_called_with(state='normal')

    def test_bulk_confirmation_updates_the_original_row(self):
        row = self.parse('행정과')[0]
        picked = '충청북도청주교육지원청 행정과'

        self.assertTrue(self.app._confirm_org_item(row, picked))
        self.assertEqual(row['org'], picked)
        self.assertEqual(row['grade'], 'exact')
        self.assertFalse(row['code_missing'])
        self.assertFalse(self.app._org_needs_review(row))

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

    def test_registering_office_is_fixed_to_chungbuk(self):
        """수신픽 화면에서 교육청을 고르지 않아도 충북교육청 코드가 적용된다."""
        from app_config import CHUNGBUK_OFFICE_CODE

        self.assertFalse(hasattr(self.app, 'office_combo'))
        self.assertFalse(hasattr(self.app, 'office_var'))
        self.assertEqual(
            self.app.edufine_vars['등록교육청코드'].get(),
            CHUNGBUK_OFFICE_CODE,
        )

        # 저장 직전에 잘못된 값이 들어와도 고정 코드를 다시 적용한다.
        self.app.edufine_vars['등록교육청코드'].set('M100000098')
        self.app._save_edufine_fields()
        self.assertEqual(
            self.app.config.edufine['등록교육청코드'],
            CHUNGBUK_OFFICE_CODE,
        )

    def test_both_tools_have_a_step_by_step_guide(self):
        from app_config import TARGET_EDUFINE, TARGET_MESSENGER

        targets = self.app._guide_target_map()
        for target in (TARGET_MESSENGER, TARGET_EDUFINE):
            steps = self.app_module.GUIDE_STEPS[target]
            self.assertGreaterEqual(len(steps), 4)
            for tab_key, widget_key, heading, body in steps:
                self.assertIn(tab_key, {'input', 'calib', 'auto', 'edufine'})
                self.assertIn(widget_key, targets)
                self.assertTrue(heading.strip())
                self.assertTrue(body.strip())

    def test_guide_does_not_open_automatically(self):
        """앱 실행과 도구 전환만으로 안내창이 나타나면 안 된다."""
        from app_config import TARGET_EDUFINE, TARGET_MESSENGER

        self.assertIsNone(self.app.guide_dialog)
        self.app._choose_target(TARGET_MESSENGER)
        self.assertIsNone(self.app.guide_dialog)
        self.app._choose_target(TARGET_EDUFINE)
        self.assertIsNone(self.app.guide_dialog)

    def test_guide_highlights_each_real_control_and_cleans_up(self):
        """가이드 단계가 실제 위젯을 강조하고 종료할 때 테두리를 치운다."""
        from app_config import TARGET_EDUFINE

        self.app._show_onboarding(TARGET_EDUFINE)
        guide = self.app.guide_dialog
        self.assertIsNotNone(guide)
        self.assertIs(guide.highlight_target, self.app.input_text)
        self.assertTrue(all(border.place.called for border in guide.highlight_frames))

        guide.next()
        self.assertIs(guide.highlight_target, self.app.parse_button)

        borders = list(guide.highlight_frames)
        guide.finish()
        self.assertIsNone(self.app.guide_dialog)
        self.assertTrue(all(border.place_forget.called for border in borders))
        self.assertTrue(all(border.destroy.called for border in borders))

    def test_clipboard_walker_receives_only_code_missing_orgs(self):
        self.app.names_list = [
            {'org': '코드 있는 기관', 'grade': 'exact'},
            {'org': '코드 없는 기관', 'grade': 'exact'},
        ]
        split = (
            [{'name': '코드 있는 기관', 'code': 'M100000001'}],
            [{'name': '코드 없는 기관', 'reason': '코드 없음'}],
        )
        with patch.object(self.app, '_split_confirmed', return_value=split), \
                patch.object(self.app_module, 'ClipboardWalker') as walker:
            self.app._open_clipboard_walker()
        walker.assert_called_once_with(self.app.root, ['코드 없는 기관'])

    def test_stop_keeps_start_disabled_until_worker_finishes(self):
        worker = MagicMock()
        worker.is_alive.return_value = True
        self.app.worker_thread = worker
        try:
            self.app._stop()
            self.app.start_btn.config.assert_called_with(state='disabled')
            self.assertTrue(self.app.stop_flag.is_set())
        finally:
            self.app.worker_thread = None
            self.app.stop_flag.clear()

    def test_start_keeps_previous_screen_log(self):
        """새 실행을 시작해도 앞선 실패 기록을 자동으로 지우지 않는다."""
        from app_config import CALIBRATION_KEYS

        old_coords = {key: self.app.config.data.get(key) for key in CALIBRATION_KEYS}
        self.app.names_list = [{'org': '학교', 'name': '홍길동'}]
        for key in CALIBRATION_KEYS:
            self.app.config.data[key] = 10

        thread = MagicMock()
        thread.is_alive.return_value = False
        try:
            with patch.object(self.app_module, 'pyautogui', MagicMock()), \
                    patch.object(self.app_module, 'pyperclip', MagicMock()), \
                    patch.object(self.app_module.threading, 'Thread', return_value=thread), \
                    patch.object(self.app, '_log_clear') as clear_log, \
                    patch.object(self.app, '_log') as append_log:
                self.app._start()

            clear_log.assert_not_called()
            self.assertIn('자동 선택 시작', append_log.call_args.args[0])
            thread.start.assert_called_once_with()
        finally:
            self.app.worker_thread = None
            self.app.names_list = []
            for key, value in old_coords.items():
                self.app.config.data[key] = value

    def test_failed_addition_is_written_to_application_log(self):
        self.app.names_list = [{'org': '학교', 'name': '홍길동'}]
        with self.assertLogs(level='WARNING') as captured:
            self.app._mark_failed(0, '검색 결과 없음')
        self.assertTrue(any('명단 추가 실패' in line for line in captured.output))

    # ── 검색 결과 판정 ─────────────────────────
    def _use_result_coords(self, x=500, y=400):
        """결과 좌표를 임시로 정해 두고, 테스트가 끝나면 되돌린다."""
        keys = ('result_first_x', 'result_first_y')
        saved = {k: self.app.config.data.get(k) for k in keys}
        self.app.config.data['result_first_x'] = x
        self.app.config.data['result_first_y'] = y
        self.addCleanup(lambda: self.app.config.data.update(saved))

    def test_result_is_found_when_the_exact_point_is_blank(self):
        """좌표 한 점이 글자 사이 빈 칸이어도 옆의 글자를 보고 결과로 판정한다."""
        from automation import RESULT_SCAN_HEIGHT, RESULT_SCAN_WIDTH

        width, height = RESULT_SCAN_WIDTH, RESULT_SCAN_HEIGHT
        mid_row, mid_col = height // 2, width // 2
        painted = {(mid_row, mid_col + off) for off in range(6, 20)}
        pixels = _fake_pixels(width, height, painted)
        self.assertEqual(pixels[mid_row * width + mid_col], (255, 255, 255),
                         '좌표 한 점은 빈 칸이어야 하는 상황입니다')

        self._use_result_coords()
        with patch.object(self.app_module, 'pyautogui',
                          _fake_screen(pixels, width, height)):
            self.assertTrue(self.app._has_result())

    def test_blank_result_area_is_reported_as_no_user(self):
        from automation import RESULT_SCAN_HEIGHT, RESULT_SCAN_WIDTH

        width, height = RESULT_SCAN_WIDTH, RESULT_SCAN_HEIGHT
        pixels = _fake_pixels(width, height, set())
        self._use_result_coords()
        with patch.object(self.app_module, 'pyautogui',
                          _fake_screen(pixels, width, height)):
            self.assertFalse(self.app._has_result())

    def test_result_region_stays_inside_the_screen(self):
        from automation import RESULT_SCAN_HEIGHT, RESULT_SCAN_WIDTH

        self._use_result_coords(x=2, y=1)
        with patch.object(self.app_module, 'pyautogui',
                          _fake_screen([], 0, 0, screen=(1920, 1080))):
            left, top, width, height = self.app._result_region()
        self.assertEqual((left, top), (0, 0))
        self.assertEqual((width, height), (RESULT_SCAN_WIDTH, RESULT_SCAN_HEIGHT))

    def test_late_result_is_waited_for(self):
        """결과가 늦게 떠도 바로 실패로 넘기지 않는다."""
        self.app.config.data['search_delay'] = 0.1
        with patch.object(self.app_module.time, 'sleep', lambda *_: None), \
                patch.object(self.app, '_has_result',
                             side_effect=[False, False, True]):
            self.assertTrue(self.app._wait_for_result())

    def test_waiting_gives_up_after_the_deadline(self):
        self.app.config.data['search_delay'] = 0.01
        with patch.object(self.app_module, 'RESULT_WAIT_MIN', 0.05), \
                patch.object(self.app_module.time, 'sleep', lambda *_: None), \
                patch.object(self.app, '_has_result', return_value=False):
            self.assertFalse(self.app._wait_for_result())

    # ── 담겼는지 확인 ──────────────────────────
    def _use_verify(self, on=True):
        saved = self.app.config.data.get('verify_add')
        self.app.config.data['verify_add'] = on
        self.addCleanup(lambda: self.app.config.data.__setitem__('verify_add', saved))

    def test_add_is_confirmed_by_the_duplicate_popup(self):
        """두 번째 클릭에서 중복 안내창이 뜨면 첫 클릭이 통한 것이다."""
        self._use_verify(True)
        with patch.object(self.app_module.time, 'sleep', lambda *_: None), \
                patch.object(self.app, '_click_add_once',
                             side_effect=[False, True]) as clicked:
            self.assertEqual(self.app._do_select(), 'ok')
        self.assertEqual(clicked.call_count, 2)

    def test_add_that_never_shows_the_popup_is_a_failure(self):
        """끝까지 안내창이 없으면 담기지 않은 것이라 실패로 남긴다."""
        from automation import VERIFY_ADD_TRIES

        self._use_verify(True)
        with patch.object(self.app_module.time, 'sleep', lambda *_: None), \
                patch.object(self.app, '_click_add_once',
                             return_value=False) as clicked:
            self.assertEqual(self.app._do_select(), 'unverified')
        self.assertEqual(clicked.call_count, 1 + VERIFY_ADD_TRIES)

    def test_already_added_person_is_reported_as_duplicate(self):
        """첫 클릭에서 안내창이 뜨면 돌리기 전부터 담혀 있던 사람이다."""
        self._use_verify(True)
        with patch.object(self.app_module.time, 'sleep', lambda *_: None), \
                patch.object(self.app, '_click_add_once',
                             return_value=True) as clicked:
            self.assertEqual(self.app._do_select(), 'duplicate')
        self.assertEqual(clicked.call_count, 1)

    def test_verification_can_be_turned_off(self):
        self._use_verify(False)
        with patch.object(self.app_module.time, 'sleep', lambda *_: None), \
                patch.object(self.app, '_click_add_once',
                             return_value=False) as clicked:
            self.assertEqual(self.app._do_select(), 'ok')
        self.assertEqual(clicked.call_count, 1)

    def test_verification_stops_when_the_user_stops(self):
        self._use_verify(True)
        self.app.stop_flag.set()
        try:
            with patch.object(self.app_module.time, 'sleep', lambda *_: None), \
                    patch.object(self.app, '_click_add_once', return_value=False):
                self.assertEqual(self.app._do_select(), 'stopped')
        finally:
            self.app.stop_flag.clear()

    def test_missing_coordinates_are_reported(self):
        keys = ('result_first_x', 'result_first_y', 'add_button_x', 'add_button_y')
        saved = {k: self.app.config.data.get(k) for k in keys}
        self.app.config.data['result_first_x'] = None
        try:
            with self.assertRaises(RuntimeError) as caught:
                self.app._click_add_once()
            self.assertIn('좌표', str(caught.exception))
        finally:
            self.app.config.data.update(saved)

    def test_waiting_stops_when_the_user_stops(self):
        self.app.stop_flag.set()
        try:
            with patch.object(self.app, '_has_result') as looked:
                self.assertFalse(self.app._wait_for_result())
            looked.assert_not_called()
        finally:
            self.app.stop_flag.clear()


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

    def test_capture_dialog_never_claims_the_mouse_grab(self):
        """외부 소통메신저를 눌러야 하므로 캡처 창은 처음부터 입력을 독점하면 안 된다."""
        m = self.app_module
        dlg = m.CaptureDialog(_Widget(), lambda _x, _y: None)
        self.assertFalse(
            dlg.grab_set.called,
            '캡처 창을 열기만 해도 마우스 입력을 독점하고 있습니다',
        )

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
        with open(script, encoding='utf-8') as source_file:
            source = source_file.read()
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
