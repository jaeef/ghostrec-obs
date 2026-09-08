@echo off
REM ============================================================
REM  Opens a dedicated GPU-disabled Chrome for class recording.
REM  Window-capture only works on this PC (Intel iGPU) when the
REM  browser runs with --disable-gpu. Uses a separate profile so
REM  your normal Chrome is untouched and the flag actually applies.
REM
REM  Join your class in THIS window (Teams web / Meet / Zoom web).
REM  Then run:  python record.py
REM ============================================================

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

start "" "%CHROME%" ^
  --disable-gpu ^
  --user-data-dir="%USERPROFILE%\class-rec-chrome" ^
  --new-window "https://teams.microsoft.com"
