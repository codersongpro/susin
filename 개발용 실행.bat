@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem 고치는 중에 쓰는 실행 파일이다.
rem 최신 코드를 받고 바로 실행한다. exe 를 만들 필요가 없다.
rem 배포용으로 처음 설치하는 분은 '시작.bat' 을 쓴다.

cd /d "%~dp0"
title 신통픽 개발용 실행

echo ============================================
echo   신통픽 개발용 실행
echo ============================================
echo.

rem ---- 1. 최신 코드 받기 ----
echo [1/3] 최신 코드 받기
where git >nul 2>&1
if errorlevel 1 (
    echo    Git 이 없어 건너뜁니다. 지금 폴더에 있는 코드로 실행합니다.
    echo    https://git-scm.com/download/win 에서 설치하면 이 단계가 자동으로 됩니다.
) else (
    git pull --ff-only
    if errorlevel 1 (
        echo.
        echo    최신 코드를 받지 못했습니다.
        echo    이 폴더에서 고친 파일이 있으면 그것 때문입니다.
        echo    지금 폴더에 있는 코드로 이어서 실행합니다.
    )
)
echo.

rem ---- 2. 파이썬 찾기 ----
set "PYTHON="
python --version >nul 2>&1
if not errorlevel 1 set "PYTHON=python"

if not defined PYTHON (
    py --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=py"
)

if not defined PYTHON (
    for %%V in (313 312 311 310 39) do (
        if not defined PYTHON (
            if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
                set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            )
        )
    )
)

if not defined PYTHON (
    echo 파이썬을 찾지 못했습니다.
    echo '시작.bat' 을 한 번 실행하면 파이썬까지 깔아 줍니다.
    pause
    exit /b 1
)

rem ---- 3. 빠진 패키지만 설치 ----
echo [2/3] 필요한 패키지 확인
"%PYTHON%" -c "import pyautogui, pyperclip, openpyxl, win32gui, olefile" >nul 2>&1
if errorlevel 1 (
    echo    빠진 것이 있어 설치합니다. 처음 한 번만 걸립니다.
    "%PYTHON%" -m pip install --disable-pip-version-check pyautogui pyperclip openpyxl pywin32 olefile
) else (
    echo    다 있습니다.
)
echo.

rem ---- 4. 실행 ----
echo [3/3] 신통픽 실행
echo.
"%PYTHON%" main.py
set "CODE=%errorlevel%"

if not "%CODE%"=="0" (
    echo.
    echo ============================================
    echo   오류로 끝났습니다 ^(코드 %CODE%^)
    echo   위에 찍힌 내용을 복사해서 알려 주세요.
    echo ============================================
    pause
)

endlocal
