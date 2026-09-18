@echo off
setlocal

set "SCRIPT=%~dp0main.py"
set "PYTHON="

rem ---- Find Python in PATH ----
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python"
    goto :install_pkgs
)

python3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python3"
    goto :install_pkgs
)

py --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py"
    goto :install_pkgs
)

rem ---- Find Python in common install locations ----
for %%V in (314 313 312 311 310 39 38) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :install_pkgs
    )
    if exist "C:\Python%%V\python.exe" (
        set "PYTHON=C:\Python%%V\python.exe"
        goto :install_pkgs
    )
    if exist "%PROGRAMFILES%\Python%%V\python.exe" (
        set "PYTHON=%PROGRAMFILES%\Python%%V\python.exe"
        goto :install_pkgs
    )
)

if exist "%USERPROFILE%\Anaconda3\python.exe" (
    set "PYTHON=%USERPROFILE%\Anaconda3\python.exe"
    goto :install_pkgs
)

if exist "%USERPROFILE%\miniconda3\python.exe" (
    set "PYTHON=%USERPROFILE%\miniconda3\python.exe"
    goto :install_pkgs
)

rem ---- Python not found: download and install ----
echo Python not found. Downloading Python 3.11...

powershell -NoProfile -Command "(New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe','C:\py311setup.exe')"

if not exist "C:\py311setup.exe" (
    echo Download failed. Check internet connection.
    pause
    exit /b 1
)

echo Installing Python 3.11...
C:\py311setup.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
del /f /q "C:\py311setup.exe" >nul 2>&1

rem ---- Find again after install ----
for %%V in (311 314 313 312 310 39 38) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :install_pkgs
    )
)

echo Python install failed. Restart PC and try again.
pause
exit /b 1

rem ---- Install packages ----
:install_pkgs
echo Found: %PYTHON%
echo.
echo [1/4] Installing pyautogui...
"%PYTHON%" -m pip install --disable-pip-version-check pyautogui
echo [2/4] Installing pyperclip...
"%PYTHON%" -m pip install --disable-pip-version-check pyperclip
echo [3/4] Installing openpyxl...
"%PYTHON%" -m pip install --disable-pip-version-check openpyxl
echo [4/5] Installing pywin32 + olefile (HWP support)...
"%PYTHON%" -m pip install --disable-pip-version-check pywin32 olefile
echo [5/5] Installing pyinstaller...
"%PYTHON%" -m pip install --disable-pip-version-check pyinstaller
echo.
"%PYTHON%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Package install failed.
    pause
    exit /b 1
)

rem ---- Build EXE ----
echo Building exe...
"%PYTHON%" -m PyInstaller --onefile --windowed --name "sintongpick" --add-data "%~dp0org_db.json;." --add-data "%~dp0org_codes.json;." --add-data "%~dp0assets\수신그룹_양식.xlsx;assets" --hidden-import pyperclip --hidden-import openpyxl --hidden-import PIL --hidden-import win32com.client --hidden-import win32gui --hidden-import win32api --hidden-import win32con --hidden-import olefile "%SCRIPT%"

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\sintongpick.exe
echo.
pause
