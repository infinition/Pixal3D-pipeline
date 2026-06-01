@echo off
title Pixal3D Watcher
cd /d "%~dp0"
"..\ComfyUI_windows_portable\python_embeded\python.exe" -s "watch_pixal3d.py"
echo.
echo Watcher arrete.
pause
