@echo off
rem ============================================================
rem  WINDOW RECORDER - one-click launcher
rem  1. finds Python, installs deps if missing (first run only)
rem  2. waits for the OBS WebSocket (port 4455); can start OBS
rem  3. runs record.py - the window picker appears here
rem
rem  You can open OBS before or after double-clicking this.
rem  Optional:  start_recorder.bat --list   (just list windows)
rem ============================================================
setlocal
title Window Recorder
chcp 65001 >nul
cd /d "%~dp0"

rem --- find python ------------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo [!] Python not found in PATH - install Python 3.10+ first.
    pause
    exit /b 1
)

rem --- utf-8 safe output (window titles, status line) --------------------------
set "PYTHONUTF8=1"

rem --- deps (first run only) ---------------------------------------------------
%PY% -c "import obsws_python, win32gui" >nul 2>nul
if errorlevel 1 (
    echo [i] Installing requirements - one time only...
    %PY% -m pip install -r requirements.txt
)

rem --- wait for the OBS WebSocket ----------------------------------------------
set /a n=0
:wait_obs
netstat -ano | findstr /r /c:":4455 .*LISTENING" >nul 2>nul && goto obs_ok
set /a n+=1
if %n%==8 (
    echo [!] OBS WebSocket not detected on port 4455.
    echo     Is OBS Studio open?  Tools -^> WebSocket Server Settings -^> Enable.
    choice /c YN /n /m "    Start OBS now? [Y/N] "
    if not errorlevel 2 (
        if exist "C:\Program Files\obs-studio\bin\64bit\obs64.exe" (
            start "" "C:\Program Files\obs-studio\bin\64bit\obs64.exe" --startminimized
        ) else (
            echo     OBS not found at its default path - start it manually.
        )
    )
)
if %n% geq 90 (
    echo [!] Giving up: OBS WebSocket never appeared on port 4455.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_obs

:obs_ok
echo [i] OBS WebSocket detected.
echo.

rem --- run the recorder (interactive window picker in THIS console) -------------
%PY% record.py %*

echo.
echo [i] Recorder closed.
pause
