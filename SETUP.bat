@echo off
REM ====================================================================
REM  Pixal3D - One-click setup
REM  Detects your GPU, installs every dependency (pipeline deps, custom
REM  node deps, and the prebuilt CUDA wheels), copies the default config
REM  and verifies the install. Run this ONCE before the first START.bat.
REM
REM  Safe to re-run: completed steps are skipped automatically.
REM ====================================================================
setlocal enabledelayedexpansion
title Pixal3D - Setup
cd /d "%~dp0"

set "PY=ComfyUI_windows_portable\python_embeded\python.exe"
set "NODE_DIR=ComfyUI_windows_portable\ComfyUI\custom_nodes\Pixal3D-ComfyUI"
set "WHEELS=_downloads\wheels"
set "MODELS=ComfyUI_windows_portable\ComfyUI\models\Pixal3D"

echo ============================================================
echo   Pixal3D Pipeline - one-click setup
echo ============================================================
echo.

REM ---------------------------------------------------------------
REM  0. ComfyUI portable must be extracted here already
REM ---------------------------------------------------------------
if not exist "%PY%" (
    echo [ERROR] ComfyUI portable not found.
    echo         Expected: %CD%\%PY%
    echo.
    echo Extract the ComfyUI Windows portable build into this folder so the
    echo layout is  Pixal3D-pipeline\ComfyUI_windows_portable\  then re-run.
    echo See README, step 2.
    echo.
    pause
    exit /b 1
)
echo [OK]  ComfyUI embedded Python found.
echo.

REM ---------------------------------------------------------------
REM  1. Detect GPU + recommend a VRAM preset
REM ---------------------------------------------------------------
echo ------------------------------------------------------------
echo  Step 1/6 - GPU detection
echo ------------------------------------------------------------
set "GPUNAME="
set "VRAM="
where nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [WARN] nvidia-smi not found. Cannot read your VRAM.
    echo        An NVIDIA GPU with 12+ GB VRAM is required to run Pixal3D.
) else (
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits > "%TEMP%\pxl_gpu.txt" 2>nul
    for /f "tokens=1,2 delims=," %%a in (%TEMP%\pxl_gpu.txt) do (
        set "GPUNAME=%%a"
        set "VRAM=%%b"
    )
    del "%TEMP%\pxl_gpu.txt" >nul 2>&1
    set "VRAM=!VRAM: =!"
    set "GPUNAME=!GPUNAME:~0,60!"
    if defined VRAM (
        set /a VRAMROUND=!VRAM!+512
        set /a VRAMGB=!VRAMROUND!/1024
        echo  GPU : !GPUNAME!
        echo  VRAM: !VRAMGB! GB ^(!VRAM! MiB^)
        if !VRAM! GEQ 30000 (
            set "PRESET=32 GB+    -  1536_cascade, max_tokens 131072, texture 4096"
        ) else if !VRAM! GEQ 22000 (
            set "PRESET=24 GB     -  1536_cascade, max_tokens 98304, texture 4096"
        ) else if !VRAM! GEQ 15000 (
            set "PRESET=16 GB     -  1024_cascade, max_tokens 65536, texture 4096"
        ) else (
            set "PRESET=12 GB     -  1024_cascade, max_tokens 49152, texture 2048"
        )
        echo  Recommended preset: !PRESET!
        echo  ^(pick it later in the control panel under "VRAM preset"^)
    )
)
echo.

REM ---------------------------------------------------------------
REM  2. Pipeline dependencies (gradio, rembg, pillow)
REM ---------------------------------------------------------------
echo ------------------------------------------------------------
echo  Step 2/6 - Pipeline dependencies ^(gradio, rembg^)
echo ------------------------------------------------------------
"%PY%" -s -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install pipeline requirements. See messages above.
    pause
    exit /b 1
)
echo [OK]  Pipeline dependencies installed.
echo.

REM ---------------------------------------------------------------
REM  3. Pixal3D custom node present? clone if missing
REM ---------------------------------------------------------------
echo ------------------------------------------------------------
echo  Step 3/6 - Pixal3D custom node
echo ------------------------------------------------------------
if exist "%NODE_DIR%\install.py" (
    echo [OK]  Custom node already present.
) else (
    where git >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Custom node missing and git is not installed.
        echo        Install it via the ComfyUI Manager ^(search "Pixal3D" by
        echo        Saganaki22^) or install Git and re-run this script.
    ) else (
        echo [..]  Cloning Pixal3D-ComfyUI ...
        git clone https://github.com/Saganaki22/Pixal3D-ComfyUI.git "%NODE_DIR%"
        if errorlevel 1 (
            echo [WARN] Clone failed. Install the node via ComfyUI Manager instead.
        ) else (
            echo [OK]  Custom node cloned.
        )
    )
)
echo.

REM ---------------------------------------------------------------
REM  4. Custom node dependencies
REM     The node's requirements.txt pins natten==0.21.6. natten has no Windows
REM     wheel and fails to build from source -- and because pip installs from a
REM     -r file atomically, that one failure aborts the whole install and takes
REM     diffusers / trimesh / accelerate / timm / utils3d down with it. natten
REM     is optional at runtime (the node falls back when it is absent), so we
REM     install everything EXCEPT natten. triton (triton-windows) is needed by
REM     flex_gemm and is deliberately kept out of the node requirements, so we
REM     add it explicitly here.
REM ---------------------------------------------------------------
echo ------------------------------------------------------------
echo  Step 4/6 - Custom node dependencies
echo ------------------------------------------------------------
if exist "%NODE_DIR%\requirements.txt" (
    findstr /v /i "natten" "%NODE_DIR%\requirements.txt" > "%TEMP%\pxl_reqs.txt"
    echo [..]  Installing node dependencies ^(natten skipped: optional, no Windows build^)...
    "%PY%" -s -m pip install -r "%TEMP%\pxl_reqs.txt"
    set "REQ_ERR=!errorlevel!"
    del "%TEMP%\pxl_reqs.txt" >nul 2>&1
    REM triton-windows (flex_gemm) and zstandard (o_voxel) are runtime deps of the
    REM CUDA wheels but are not in the node requirements; the wheels install with
    REM --no-deps so we add them here.
    echo [..]  Installing triton-windows + zstandard ^(CUDA wheel runtime deps^)...
    "%PY%" -s -m pip install triton-windows zstandard
    if errorlevel 1 set "REQ_ERR=1"
    if "!REQ_ERR!"=="0" (
        echo [OK]  Custom node dependencies installed.
    ) else (
        echo [WARN] Some node dependencies failed to install. Check the log above.
    )
) else (
    echo [SKIP] Custom node not found; skipping its dependencies.
)
echo.

REM ---------------------------------------------------------------
REM  5. CUDA kernel wheels (flash_attn, cumesh, drtk, o_voxel, flex_gemm)
REM     Prefer the bundled exact-stack wheels (cu130 / torch2.11 / cp313).
REM     There are two flash_attn builds in the folder; install only the
REM     newest one (highest version sorts last by name).
REM ---------------------------------------------------------------
echo ------------------------------------------------------------
echo  Step 5/6 - CUDA kernel wheels
echo ------------------------------------------------------------
REM On a fresh clone _downloads\wheels is empty (the wheels are git-ignored and
REM ~370 MB each). Fetch the exact-stack wheels (cu130 / torch2.11 / cp313) from
REM PozzettiAndrea/cuda-wheels. No manual wheel hunting required.
if not exist "%WHEELS%\*.whl" (
    echo [..]  No local wheels found. Downloading from PozzettiAndrea/cuda-wheels ...
    powershell -ExecutionPolicy Bypass -NoProfile -File "_downloads\get_wheels.ps1" -Dest "%WHEELS%"
    if errorlevel 1 echo [WARN] Wheel download had problems; see messages above.
)

if exist "%WHEELS%\*.whl" (
    echo [..]  Installing wheels from %WHEELS% ...
    REM Two flash_attn builds may be present; install only the newest (name sorts last).
    set "FA="
    for /f "delims=" %%w in ('dir /b /o-n "%WHEELS%\flash_attn*.whl" 2^>nul') do (
        if not defined FA set "FA=%%w"
    )
    set "OTHERS="
    for /f "delims=" %%w in ('dir /b "%WHEELS%\*.whl" ^| findstr /v /i "flash_attn"') do (
        set "OTHERS=!OTHERS! "%WHEELS%\%%w""
    )
    if defined FA (
        "%PY%" -s -m pip install --no-deps !OTHERS! "%WHEELS%\!FA!"
    ) else (
        "%PY%" -s -m pip install --no-deps !OTHERS!
    )
    if errorlevel 1 (
        echo [WARN] Some wheels failed to install. Check the log above.
    ) else (
        echo [OK]  CUDA wheels installed.
    )
) else (
    echo [WARN] No wheels available and the download did not succeed.
    echo        Install them by hand from PozzettiAndrea/cuda-wheels ^(README step 5B^).
)
echo.

REM ---------------------------------------------------------------
REM  6. Config + verification + model weights reminder
REM ---------------------------------------------------------------
echo ------------------------------------------------------------
echo  Step 6/6 - Config, verification, model weights
echo ------------------------------------------------------------
if exist "pipeline\config.json" (
    echo [OK]  pipeline\config.json already exists ^(left untouched^).
) else (
    copy "pipeline\config.json.example" "pipeline\config.json" >nul
    echo [OK]  Created pipeline\config.json from the example.
)

echo [..]  Verifying CUDA kernels are importable...
if exist "%NODE_DIR%\install.py" (
    "%PY%" -s "%NODE_DIR%\install.py" --check
)
echo.

if exist "%MODELS%\" (
    echo [OK]  Model folder present: %MODELS%
    echo       ^(if a job fails with "model not found", re-run hf_grab.ps1^)
) else (
    echo [TODO] Model weights are NOT downloaded yet ^(~24 GB^).
    set /p DLNOW="       Download them now with hf_grab.ps1? [y/N] "
    if /i "!DLNOW!"=="y" (
        echo [..]  Starting download ^(resumable; safe to interrupt^)...
        powershell -ExecutionPolicy Bypass -NoProfile -File "_downloads\hf_grab.ps1" -Base "ComfyUI_windows_portable\ComfyUI\models\Pixal3D" -Repos "TencentARC/Pixal3D"
    ) else (
        echo       Skipped. Download later by re-running SETUP.bat, or directly:
        echo         powershell -ExecutionPolicy Bypass -File "_downloads\hf_grab.ps1" -Base "ComfyUI_windows_portable\ComfyUI\models\Pixal3D" -Repos "TencentARC/Pixal3D"
    )
)
echo.

echo ============================================================
echo   Setup complete.
if defined PRESET echo   Your card: !PRESET!
echo   Next: double-click START.bat to launch the control panel.
echo ============================================================
echo.
pause
endlocal
