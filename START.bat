@echo off
REM ====================================================================
REM  Pixal3D - Lanceur
REM  Ouvre le panneau de controle (navigateur). Le panneau demarre
REM  automatiquement ComfyUI + le watcher, et permet de tout piloter.
REM  Garde CETTE fenetre ouverte : la fermer arrete tout.
REM ====================================================================
title Pixal3D - Panneau de controle
cd /d "%~dp0pipeline"
"..\ComfyUI_windows_portable\python_embeded\python.exe" -s "control_panel.py"
echo.
echo Panneau ferme - ComfyUI et le watcher ont ete arretes.
pause
