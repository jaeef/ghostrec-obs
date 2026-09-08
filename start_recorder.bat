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

rem --- setup (dependencies + config) -------------------------------------------
echo [i] Running setup (checks deps, config, OBS connection)...
%PY% setup.py
if errorlevel 1 (
    echo [!] Setup failed. Please check output above.
    pause
    exit /b 1
)

rem --- run the recorder (interactive window picker in THIS console) -------------
%PY% record.py %*

echo.
echo [i] Recorder closed.
pause
