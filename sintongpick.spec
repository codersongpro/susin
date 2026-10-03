# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('org_db.json', '.'), ('org_codes.json', '.'),
           ('assets/수신그룹_양식.xlsx', 'assets'),
           ('assets/guide', 'assets/guide'),
           ('assets/fonts', 'assets/fonts'),
           ('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.'),
           ('licenses', 'licenses')],
    hiddenimports=['pyperclip', 'openpyxl', 'PIL', 'win32com.client',
                   'win32gui', 'win32api', 'win32con', 'olefile'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # MouseInfo(GPL-3.0) 는 PyAutoGUI 가 딸고 오지만 쓰지 않는다. GPL 부품이 exe 에 묶이면
    # 신통픽 사용 허가서와 맞지 않으므로 뺀다. pyautogui 는 없어도 import 된다.
    excludes=['mouseinfo'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='sintongpick',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
