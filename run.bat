@echo off
REM Auto Reels - Easy launcher
REM Double-click this file OR run from command prompt: run.bat [args]
REM
REM Examples:
REM   run.bat                         -- generate reels for ALL channels
REM   run.bat --channel gaming        -- gaming channel only
REM   run.bat --channel gaming --dry-run  -- test script generation only
REM   run.bat --channel drawing
REM   run.bat --channel informative

set PYTHON="C:\Users\nikhi\AppData\Local\Programs\Python\Python311\python.exe"
set SCRIPT=main.py
set PYTHONUTF8=1

echo.
echo ===================================================
echo   Auto Reels Generator
echo ===================================================
echo.

%PYTHON% %SCRIPT% %*

echo.
pause
