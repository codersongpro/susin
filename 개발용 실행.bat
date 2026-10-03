@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem 고치는 중에 쓰는 실행 파일이다.
rem 최신 코드를 받고 바로 실행한다. exe 를 만들 필요가 없다.
rem 배포용으로 처음 설치하는 분은 '시작.bat' 을 쓴다.
rem
rem 이 파일 하나만 받아도 된다. 옆에 신통픽 코드(main.py)가 없으면 GitHub 에서
rem 최신 코드를 받아 %USERPROFILE%\sintongpick-dev 에 풀고 거기서 실행한다.
rem 실행할 때마다 새로 받으므로 늘 최신이다. 설정은 다른 곳에 있어 지워지지 않는다.

title 신통픽 개발용 실행
set "REPO_ZIP=https://github.com/codersongpro/susin/archive/refs/heads/main.zip"

echo ============================================
echo   신통픽 개발용 실행
echo ============================================
echo.

rem ---- 1. 최신 코드 받기 ----
echo [1/3] 최신 코드 받기
if exist "%~dp0main.py" (
    set "APPDIR=%~dp0"
    call :pull_with_git
) else (
    set "APPDIR=%USERPROFILE%\sintongpick-dev"
    call :download_zip
)
echo.

if not exist "%APPDIR%\main.py" (
    echo 신통픽 코드를 찾지 못해 실행할 수 없습니다.
    echo 인터넷이 되는 곳에서 다시 실행해 주세요.
    pause
    exit /b 1
)
cd /d "%APPDIR%"

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
    echo "%APPDIR%" 폴더의 '시작.bat' 을 한 번 실행하면 파이썬까지 깔아 줍니다.
    pause
    exit /b 1
)

rem ---- 3. 빠진 패키지만 설치 ----
rem 무엇을 깔지는 함께 받은 코드의 requirements.txt 가 정한다. 부품이 늘어도
rem 이 파일을 새로 받을 필요가 없다.
echo [2/3] 필요한 패키지 확인
if exist "tools\ensure_packages.py" (
    "%PYTHON%" tools\ensure_packages.py
) else (
    "%PYTHON%" -c "import pyautogui, pyperclip, openpyxl, win32gui, olefile, comtypes" >nul 2>&1
    if errorlevel 1 (
        echo    빠진 것이 있어 설치합니다. 처음 한 번만 걸립니다.
        "%PYTHON%" -m pip install --disable-pip-version-check pyautogui pyperclip openpyxl pywin32 olefile comtypes
    ) else (
        echo    다 있습니다.
    )
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
exit /b 0


rem ---- 저장소 안에서 실행할 때: git 으로 최신 코드 받기 ----
:pull_with_git
cd /d "%APPDIR%"
where git >nul 2>&1
if errorlevel 1 (
    echo    Git 이 없어 건너뜁니다. 지금 폴더에 있는 코드로 실행합니다.
    echo    https://git-scm.com/download/win 에서 설치하면 이 단계가 자동으로 됩니다.
    exit /b 0
)
git pull --ff-only
if errorlevel 1 (
    echo.
    echo    최신 코드를 받지 못했습니다.
    echo    이 폴더에서 고친 파일이 있으면 그것 때문입니다.
    echo    지금 폴더에 있는 코드로 이어서 실행합니다.
)
exit /b 0


rem ---- 이 파일만 받았을 때: GitHub 에서 코드 묶음을 받아 풀기 ----
rem PowerShell 진행 막대(ProgressPreference)를 끄지 않으면 Windows Terminal 에서 위에 찍은 한글이 겹쳐 두 번씩 보인다.
:download_zip
echo    GitHub 에서 최신 코드를 받습니다. 받는 곳: %APPDIR%
set "ZIP=%TEMP%\sintongpick-main.zip"
set "SRC=%TEMP%\sintongpick-src"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%REPO_ZIP%' -OutFile '%ZIP%'; if (Test-Path '%SRC%') { Remove-Item -Recurse -Force '%SRC%' }; Expand-Archive -Path '%ZIP%' -DestinationPath '%SRC%' -Force"
if errorlevel 1 (
    if exist "%APPDIR%\main.py" (
        echo    받지 못했습니다. 지난번에 받아 둔 코드로 실행합니다.
    ) else (
        echo    받지 못했습니다. 인터넷 연결이나 github.com 접속이 막혀 있는지 확인해 주세요.
    )
    exit /b 0
)
robocopy "%SRC%\susin-main" "%APPDIR%" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo    받은 코드를 옮기지 못했습니다. 지난번에 받아 둔 코드가 있으면 그것으로 실행합니다.
) else (
    echo    받았습니다.
)
exit /b 0
