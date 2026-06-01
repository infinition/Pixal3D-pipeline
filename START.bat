@echo off
REM ====================================================================
REM  Pixal3D - Launcher
REM  Opens the control panel in your browser. The panel starts ComfyUI
REM  and the watcher automatically.
REM  Keep this window open -- closing it stops everything.
REM ====================================================================
title Pixal3D - Control Panel
cd /d "%~dp0pipeline"
"..\ComfyUI_windows_portable\python_embeded\python.exe" -s "control_panel.py"
echo.
echo Control panel closed - ComfyUI and the watcher have been stopped.
pause
