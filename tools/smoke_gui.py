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

    # 두 출구를 오가며 탭 표시 전환이 터지지 않는지 본다
    from app_config import TARGET_EDUFINE, TARGET_MESSENGER
    for target in (TARGET_EDUFINE, TARGET_MESSENGER, TARGET_EDUFINE):
        app.target_var.set(target)
        app._on_target_change()
        print(f'출구 전환 ok — {target}')

    # 명단 추출까지 돌려 본다 (기관 경로)
    app.input_text.insert('1.0', '학성초\n청주교육지원청 행정과\n행정과')
    app._parse()
    grades = [i.get('grade') for i in app.names_list]
    print(f'명단 추출 ok — {len(app.names_list)}건 {grades}')
    assert grades.count('exact') == 2, grades
    assert 'ambiguous' in grades, grades

    root.destroy()
    print('스모크 테스트 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())
