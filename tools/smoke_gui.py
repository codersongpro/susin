"""화면 없이 앱이 실제로 뜨는지 확인한다 (CI용).

exe 를 만들기 전에 여기서 걸러야 한다. 안 그러면 사용자가 받고 나서야 안다.
탭을 다 만들고 출구를 양쪽으로 전환해 보는 것까지 한다.

대화상자는 전부 막는다. CI 에는 누를 사람이 없어서 모달이 뜨면 영영 멈춘다.
"""

import os
import sys
import tkinter
from tkinter import filedialog, messagebox

# tools/ 에서 실행되므로 저장소 루트를 경로에 넣어야 main 을 찾는다
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 콘솔 기본 인코딩(cp1252)에서는 한글을 찍다가 UnicodeEncodeError 로 죽는다.
# 확인 메시지 때문에 빌드가 멈추면 안 되므로 출력 인코딩을 고정한다.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


def _blocked(name):
    def stub(*args, **kwargs):
        raise AssertionError(f'조용히 떠야 할 화면에서 {name} 이(가) 호출됐습니다: {args[:2]}')
    return stub


def main():
    # 뜨자마자 대화상자를 띄우면 그 자체가 버그다. 막지 말고 터뜨린다.
    for mod, names in ((messagebox, ('showerror', 'showwarning', 'showinfo',
                                     'askyesno', 'askokcancel')),
                       (filedialog, ('askopenfilename', 'asksaveasfilename'))):
        for name in names:
            setattr(mod, name, _blocked(f'{mod.__name__}.{name}'))

    import main as app_module

    root = tkinter.Tk()
    root.withdraw()
    app = app_module.App(root)
    print(f'App 생성 ok — {app_module.APP_NAME} v{app_module.APP_VERSION}')

    # 두 출구를 오가며 탭이 제대로 남는지 본다.
    # 진짜 tkinter 로만 드러나는 문제가 있었다 — 등록하지 않은 탭에 hide() 를
    # 부르면 예외가 나면서 탭이 1번 하나만 남았다.
    from app_config import TARGET_EDUFINE, TARGET_MESSENGER
    expected = {TARGET_MESSENGER: 4, TARGET_EDUFINE: 3}
    for target in (TARGET_EDUFINE, TARGET_MESSENGER, TARGET_EDUFINE):
        app._choose_target(target)
        labels = [app.nb.tab(t, 'text').strip() for t in app.nb.tabs()]
        assert len(labels) == expected[target], (target, labels)
        assert labels[0].endswith('명단 입력'), labels
        expected_help = '수신픽 사용법' if target == TARGET_EDUFINE else '소통픽 사용법'
        assert labels[-1].endswith(expected_help), labels
        print(f'출구 전환 ok — {target}: {labels}')

    # 명단 추출까지 돌려 본다 (기관 경로)
    app.input_text.insert('1.0', '학성초\n청주교육지원청 행정과\n행정과')
    app._parse()
    grades = [i.get('grade') for i in app.names_list]
    print(f'명단 추출 ok — {len(app.names_list)}건 {grades}')
    assert grades.count('exact') == 2, grades
    assert 'ambiguous' in grades, grades

    # 도구 선택은 탭 밖(창 맨 위)에 있어야 한다.
    # 위젯 경로 문자열을 부분 비교하면 늘 참이 되어 아무것도 못 잡는다.
    # 카드를 담은 틀이 창의 직계 자식인지, 탭보다 위 행에 있는지로 본다.
    card = app.target_cards['edufine'][0]
    picker = card.nametowidget(card.winfo_parent())
    assert picker.winfo_parent() == str(root), (
        '선택 카드가 창 바로 아래에 있지 않습니다', picker.winfo_parent())
    picker_row = int(picker.grid_info()['row'])
    tabs_row = int(app.nb.grid_info()['row'])
    assert picker_row < tabs_row, ('선택 카드가 탭보다 아래에 있습니다', picker_row, tabs_row)
    print(f'도구 선택 위치 ok — 선택 {picker_row}행, 탭 {tabs_row}행')

    # 탭 내용이 스크롤 틀 안에 있어야 한다. 안내 그림이 들어가면서 [설정 저장]
    # 버튼이 창 밖으로 밀려난 적이 있다.
    inner = app.calib_msg.nametowidget(app.calib_msg.winfo_parent())
    holder = inner.nametowidget(inner.winfo_parent())
    assert holder.winfo_class() == 'Canvas', (
        '위치 설정 탭이 스크롤 틀 안에 있지 않습니다', holder.winfo_class())
    print(f'스크롤 틀 ok — 위치 설정 탭이 {holder.winfo_class()} 안에 있습니다')

    # 안내 그림이 실제로 읽히는지. 이름이 어긋나면 조용히 글만 나온다.
    for step in app_module.GUIDE_IMAGES:
        assert app_module.guide_image(step) is not None, (
            f'{step}번 안내 그림을 읽지 못했습니다')
    print(f'안내 그림 ok — {len(app_module.GUIDE_IMAGES)}장')

    root.destroy()
    print('스모크 테스트 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())
