# Downloads the prebuilt CUDA kernel wheels for the Pixal3D pipeline.
#
# These are pinned to the ComfyUI Windows portable stack: CUDA 13.0,
# PyTorch 2.11, Python 3.13 (cu130 / torch2.11 / cp313, win_amd64). They are
# NOT built here -- they come from Andrea Pozzetti's public wheel repository:
#     https://github.com/PozzettiAndrea/cuda-wheels
#
# SETUP.bat calls this automatically when _downloads\wheels is empty. You can
# also run it by hand:
#     powershell -ExecutionPolicy Bypass -File get_wheels.ps1 -Dest ..\_downloads\wheels
param(
    [Parameter(Mandatory = $true)][string]$Dest
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # huge speedup for large files
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$base = 'https://github.com/PozzettiAndrea/cuda-wheels/releases/download'
# <release-tag>/<asset-name>  -- '+' is a valid literal in a URL path.
$wheels = @(
    'flex_gemm_ap-latest/flex_gemm_ap-1.0.0+cu130torch2.11-cp313-cp313-win_amd64.whl',
    'cumesh_vb-latest/cumesh_vb-1.0+cu130torch2.11-cp313-cp313-win_amd64.whl',
    'o_voxel_vb_ap-latest/o_voxel_vb_ap-0.0.1+cu130torch2.11-cp313-cp313-win_amd64.whl',
    'drtk-latest/drtk-0.1.0+cu130torch2.11-cp313-cp313-win_amd64.whl',
    'flash_attn-latest/flash_attn-2.8.3+cu130torch2.11-cp313-cp313-win_amd64.whl'
)

if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Force $Dest | Out-Null }

$fail = 0
foreach ($w in $wheels) {
    $name = Split-Path $w -Leaf
    $out = Join-Path $Dest $name
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 0)) {
        Write-Host "  SKIP  $name  (already present)"
        continue
    }
    $url = "$base/$w"
    Write-Host "  GET   $name"
    try {
        $tmp = "$out.part"
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Move-Item -Force $tmp $out
        Write-Host ("  DONE  {0}  ({1} MB)" -f $name, [math]::Round((Get-Item $out).Length / 1MB))
    } catch {
        Write-Host "  FAIL  $name : $($_.Exception.Message)"
        if (Test-Path "$out.part") { Remove-Item "$out.part" -Force -ErrorAction SilentlyContinue }
        $fail++
    }
}

if ($fail -gt 0) {
    Write-Host ""
    Write-Host "[WARN] $fail wheel(s) failed to download."
    exit 1
}
exit 0
