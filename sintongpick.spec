# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('org_db.json', '.'), ('org_codes.json', '.'),
           ('assets/수신그룹_양식.xlsx', 'assets'),
           ('assets/guide', 'assets/guide')],
    hiddenimports=['pyperclip', 'openpyxl', 'PIL', 'win32com.client',
                   'win32gui', 'win32api', 'win32con', 'olefile'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
