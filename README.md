# Pixal3D Pipeline

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![Windows](https://img.shields.io/badge/Windows-0078D4?style=flat&logo=windows&logoColor=white) [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/infinition)

A batch automation layer that turns images into 3D assets (.glb) with no
manual intervention. Drop an image into a watched folder and a ready-to-use
GLB file comes out the other end, background removed and mesh decimated.

Built on top of [Pixal3D](https://huggingface.co/TencentARC/Pixal3D) via the [Saganaki22/Pixal3D-ComfyUI](https://github.com/Saganaki22/Pixal3D-ComfyUI) custom node for the ComfyUI API. Tested on an RTX 4070 Ti (12 GB VRAM). Each asset takes roughly 5 to 6 minutes end to end.


<img width="1686" height="1165" alt="image" src="https://github.com/user-attachments/assets/1c62b1aa-4e1e-4c88-a096-8b4a02b54d4e" />
<img width="1597" height="783" alt="image" src="https://github.com/user-attachments/assets/d547abc4-2eb4-444f-a7cd-817f8539c373" />
<img width="1592" height="782" alt="image" src="https://github.com/user-attachments/assets/6e2e384b-5e46-4756-bc81-451510de3d62" />

---

## How it works

```
image dropped into inbox folder
        |
        v
[Watcher]  removes background (rembg)
        |
        v
[Watcher]  submits job to ComfyUI HTTP API
        |
        v
[ComfyUI]  structure -> geometry -> texture -> mesh -> .glb
        |
        v
[Watcher]  .glb -> output folder   |   source image -> processed/
```

Background removal runs inside the watcher process, not inside ComfyUI. Drop
a regular photo and the alpha cutout is handled automatically.

---

## Requirements

- Windows 10/11
- NVIDIA GPU with at least 12 GB VRAM (16 GB recommended for higher settings)
- ComfyUI Windows portable build with the [Saganaki22/Pixal3D-ComfyUI](https://github.com/Saganaki22/Pixal3D-ComfyUI) custom node installed
- Python packages & CUDA wheels: installed automatically via the custom node's installer or manual wheel installation
- Gradio: `pip install gradio` (installed automatically via `requirements.txt`)

---

## Setup

### Quick path (recommended)

If you just want it running, three steps:

1. **Clone the repo** and **extract the ComfyUI portable build** into it (steps 1
   and 2 below).
2. Double-click **`SETUP.bat`**. It detects your GPU, installs every dependency
   (pipeline + custom node + the prebuilt CUDA wheels, downloaded automatically
   from [Pozzetti's cuda-wheels](https://github.com/PozzettiAndrea/cuda-wheels) —
   no manual wheel hunting), copies the default config, verifies the kernels, and
   offers to download the ~24 GB model weights. Safe to re-run — finished steps
   are skipped.
3. Double-click **`START.bat`**.

`SETUP.bat` also prints the **VRAM preset** that matches your card. Select it later
in the control panel (see [VRAM presets](#vram-presets)).

If `SETUP.bat` reports a problem, or you want to understand each piece, follow the
manual steps below.

### 1. Clone the repo

```bash
git clone https://github.com/infinition/Pixal3D-pipeline.git
cd Pixal3D-pipeline
```

### 2. Install ComfyUI portable

Download the ComfyUI Windows portable build and extract it so the layout is:

```
Pixal3D-pipeline/
  ComfyUI_windows_portable/
  pipeline/
  START.bat
```

### 3. Install the Pixal3D custom node

Install the **Pixal3D-ComfyUI** custom node by **Saganaki22**. You can do this in two ways:
- **Recommended**: Open ComfyUI, go to the **ComfyUI Manager**, search for **"Pixal3D"** by `Saganaki22`, and click **Install**.
- **Manual**: Clone the repository into ComfyUI's custom nodes folder:
  ```bash
  cd ComfyUI_windows_portable/ComfyUI/custom_nodes/
  git clone https://github.com/Saganaki22/Pixal3D-ComfyUI.git
  ```

### 4. Download the model weights

The models are **not downloaded automatically** at runtime. Run `hf_grab.ps1`
once before the first use. It handles resumable downloads and skips files that
are already complete.

```powershell
# Optional: set a HuggingFace token for gated repos
$env:HF_TOKEN = "hf_your_token_here"

cd _downloads
.\hf_grab.ps1 `
  -Base "..\ComfyUI_windows_portable\ComfyUI\models\Pixal3D" `
  -Repos @("TencentARC/Pixal3D")
```

Total size is roughly 24 GB. The script prints progress and resumes from where
it left off if the download is interrupted.

### 5. Install Python dependencies & CUDA wheels

The custom node relies on specialized CUDA kernels (`flash_attn`, `cumesh`, `drtk`, `o_voxel`, `flex_gemm`) that are highly environment-dependent (they must match your exact Python, PyTorch, and CUDA versions).

#### A. Install Pipeline Dependencies
Install the required packages for the watcher and control panel (Gradio, rembg, etc.) in the ComfyUI embedded Python environment:

```bat
ComfyUI_windows_portable\python_embeded\python.exe -m pip install -r requirements.txt
```

#### B. Install Custom Node Dependencies & CUDA Wheels

The custom node needs five prebuilt CUDA kernel wheels. **You do not have to build
them yourself** — `SETUP.bat` (or the helper below) downloads exact-match wheels for
this stack (**CUDA 13.0 / PyTorch 2.11 / Python 3.13**, `win_amd64`) from
[Andrea Pozzetti's cuda-wheels repo](https://github.com/PozzettiAndrea/cuda-wheels).

- **Automatic (recommended)** — already handled by `SETUP.bat`. To do just this
  step on its own:
  ```bat
  cd _downloads
  powershell -ExecutionPolicy Bypass -File get_wheels.ps1 -Dest .\wheels
  ..\ComfyUI_windows_portable\python_embeded\python.exe -m pip install --no-deps wheels\*.whl
  ```
  Then install the node's own Python deps:
  ```bat
  ComfyUI_windows_portable\python_embeded\python.exe ComfyUI\custom_nodes\Pixal3D-ComfyUI\install.py
  ```

- **Manual (direct links)** — the exact wheels for this stack
  (`cu130 / torch2.11 / cp313 / win_amd64`):
  | Kernel | Wheel |
  |--------|-------|
  | flash_attn | [flash_attn-2.8.3](https://github.com/PozzettiAndrea/cuda-wheels/releases/download/flash_attn-latest/flash_attn-2.8.3+cu130torch2.11-cp313-cp313-win_amd64.whl) |
  | flex_gemm | [flex_gemm_ap-1.0.0](https://github.com/PozzettiAndrea/cuda-wheels/releases/download/flex_gemm_ap-latest/flex_gemm_ap-1.0.0+cu130torch2.11-cp313-cp313-win_amd64.whl) |
  | cumesh | [cumesh_vb-1.0](https://github.com/PozzettiAndrea/cuda-wheels/releases/download/cumesh_vb-latest/cumesh_vb-1.0+cu130torch2.11-cp313-cp313-win_amd64.whl) |
  | o_voxel | [o_voxel_vb_ap-0.0.1](https://github.com/PozzettiAndrea/cuda-wheels/releases/download/o_voxel_vb_ap-latest/o_voxel_vb_ap-0.0.1+cu130torch2.11-cp313-cp313-win_amd64.whl) |
  | drtk | [drtk-0.1.0](https://github.com/PozzettiAndrea/cuda-wheels/releases/download/drtk-latest/drtk-0.1.0+cu130torch2.11-cp313-cp313-win_amd64.whl) |

  ```bat
  ComfyUI_windows_portable\python_embeded\python.exe -m pip install --no-deps <path_to_wheel>.whl
  ```
  If you are on a **different** Python/PyTorch/CUDA combination, browse the
  [cuda-wheels releases](https://github.com/PozzettiAndrea/cuda-wheels/releases)
  for a matching `cpXXX / torchX.Y / cuXXX` build.

  *(Once installed, use the **Pixal3D Environment Check** node inside ComfyUI to
  verify that all kernels load.)*

### 6. Configure

Copy the example config and edit it:

```bat
copy pipeline\config.json.example pipeline\config.json
```

For a fully local setup, leave `inbox_dir` and `output_dir` empty. The
watcher will use `pipeline/inbox/` and `pipeline/results/` automatically.

```json
{
  "inbox_dir": "",
  "output_dir": "",
  "nas_user": "",
  "nas_password": ""
}
```

You can also set any path you like:

```json
{
  "inbox_dir": "D:\\3D\\in",
  "output_dir": "D:\\3D\\out"
}
```

NAS paths work too (`\\server\share\...`). Fill in `nas_user` and
`nas_password` only if the share requires authentication.

All settings can be changed live from the control panel without restarting
anything.

---

## Running

Double-click `START.bat`.

This opens a console window (keep it open; closing it stops everything) and
launches the control panel at `http://127.0.0.1:7860`.

The panel starts ComfyUI and the watcher automatically. Wait about 40 seconds
for ComfyUI to finish loading, then drop images into the inbox folder.

---

## Control panel

Everything is managed from `http://127.0.0.1:7860`:

- **Status**: ComfyUI and Watcher indicators, refreshed live.
- **Start / Stop / Restart**: controls for both processes independently.
- **Folders**: inbox and output paths (local or network). Leave empty to
  use the default local folders inside `pipeline/`.
- **NAS credentials**: fill in only if using a password-protected network share.
- **Generation settings**: all parameters with explanations, applied on
  the next image after saving.
- **Watcher log**: live feed of rembg, queue, success, and failure events.
- **Open folder buttons**: opens inbox or output in Explorer.

---

## Generation parameters

### VRAM presets

The control panel has a **VRAM preset** dropdown at the top of *Generation
settings*. It auto-detects your card (via `nvidia-smi`) and suggests the closest
preset. Picking one fills `pipeline_type`, `max_num_tokens` and `texture_size` in
one click; press **Save settings** to apply it to the next image.

| Preset | Example cards | `pipeline_type` | `max_num_tokens` | `texture_size` |
|--------|---------------|-----------------|------------------|----------------|
| **12 GB** | RTX 3060, 4070 Ti | `1024_cascade` | 49152 | 2048 |
| **16 GB** | RTX 4080, 4060 Ti 16G | `1024_cascade` | 65536 | 4096 |
| **24 GB** | RTX 3090, 4090 | `1536_cascade` | 98304 | 4096 |
| **32 GB+** | RTX 5090 | `1536_cascade` | 131072 | 4096 |

Only the **12 GB** row is hardware-tested (RTX 4070 Ti). The larger rows scale up
from there — bigger cards can afford the `1536_cascade` and a larger token budget.
They are solid starting points, not guarantees: if a card hits CUDA out of memory,
drop `max_num_tokens` by one step and retry. Choose **Custom** to leave the values
below untouched and tune by hand.

**Running on a 5090 / 32 GB?** Yes — there is no hard requirement for a 5090, the
pipeline was built and tested on a 12 GB card, but a 32 GB card lets you run the
full-detail `1536_cascade` at 131072 tokens without OOM. Pick the **32 GB+**
preset and go.

### Geometry

| Parameter | Effect |
|-----------|--------|
| `pipeline_type` | Internal resolution. `1024_cascade` fits 12 GB VRAM. `1536_cascade` adds detail but risks OOM. |
| `steps` | Diffusion steps for shape and texture. Higher = more detail, slower. 12 is fast, 20 is quality. |
| `guidance` | How closely geometry follows the source image. 7.5 is a balanced default. |
| `max_num_tokens` | Geometric precision of the mesh. Higher = finer but needs more VRAM. Stay below ~65000 on 12 GB. |
| `mesh_scale` | Scale of the exported model. |
| `camera_resolution` | Resolution used for image analysis. 512 is standard. |
| `remesh` | Recomputes clean mesh topology after generation. |
| `decimation_target` | Target triangle count. Higher = denser mesh. |

### Texture

| Parameter | Effect |
|-----------|--------|
| `texture_guidance` | How closely the texture follows the source image. |
| `texture_size` | Texture resolution in pixels. 2048 standard, 4096 for fine detail. |

### Background removal and framing

| Parameter | Effect |
|-----------|--------|
| `rembg_model` | Background removal model. `isnet-general-use` is a good default. `birefnet-general` is more precise but heavier. |
| `camera_mode` | `moge` estimates depth and framing automatically. `manual` uses fixed framing. |

---

## File layout

```
Pixal3D-pipeline/
  SETUP.bat                         # Run once: installs deps, wheels, config
  START.bat                         # Double-click to launch everything
  README.md
  .gitignore
  pipeline/
    control_panel.py                # Gradio control panel
    watch_pixal3d.py                # Watcher and ComfyUI API client
    config.json.example             # Template; copy to config.json
    config.json                     # Your local config (git-ignored)
    run_watcher.bat                 # Launch watcher alone (debugging)
    inbox/                          # Default input folder (git-ignored)
    working/                        # In-progress transit (git-ignored)
    processed/                      # Source images after success (git-ignored)
    results/                        # Default output folder (git-ignored)
    failed/                         # Images that failed processing (git-ignored)
  workflows/
    pixal3d_pipeline.json                            # Pipeline workflow (JSON)
    pixal3d_example_workflow.png                     # Drag into ComfyUI to load
    pixal3d_low_vram_cam_control_example_workflow.png # Low VRAM variant with camera control
  requirements.txt                    # Pipeline deps (gradio, rembg); install first
  _downloads/
    hf_grab.ps1                     # HuggingFace batch downloader (model weights)
    get_wheels.ps1                  # Downloads the CUDA wheels from Pozzetti's repo
    requirements-comfyui-node.txt   # Pixal3D node deps (no flash_attn)
    requirements-pixal3d-nonatten.txt  # Same file, legacy name
    wheels/                         # Pre-built CUDA wheels (git-ignored, fetched by get_wheels.ps1)
  ComfyUI_windows_portable/         # ComfyUI install (git-ignored, install separately)
```

---

## ComfyUI workflow

The `workflows/` folder contains two formats:

- **PNG files** (`pixal3d_example_workflow.png`, `pixal3d_low_vram_cam_control_example_workflow.png`) --
  drag these directly into the ComfyUI canvas to load the embedded workflow.
  This is the standard ComfyUI sharing format: the image is a screenshot of the
  graph and the JSON is embedded in the PNG metadata simultaneously.
- **JSON file** (`pixal3d_pipeline.json`): the pipeline-specific workflow,
  load via ComfyUI menu > Load.

To generate a PNG version of your own workflow (after customising it), open it
in ComfyUI then use Menu > Export (image PNG). Drop the result into `workflows/`.

The workflow contains:

- **Pixal3DModelLoader**: loads the model weights with `dynamic_vram` and `flash_attn` auto-selection
- **LoadImage**: manual image input for testing outside the watcher
- **Pixal3DImageTo3D**: geometry and texture generation
- **Pixal3DExportGLB**: exports the result as a `.glb` with decimation and remesh
- **Preview3D**: 3D preview directly in the ComfyUI canvas
- **Pixal3DEnvironmentCheck**: run this first if anything fails; paste the output when reporting issues

When driven by the watcher the `LoadImage` node is bypassed; the watcher
submits the preprocessed (background-removed) image directly via the API and
reads the output `.glb` from the ComfyUI output folder.

---

## Monitoring

| Location | What you see |
|----------|--------------|
| Control panel: Status | ComfyUI and Watcher running or stopped |
| Control panel: Watcher log | Live processing events |
| Output folder | .glb files appearing as jobs complete |
| `pipeline/failed/` | Images that could not be processed |
| `http://127.0.0.1:8188` | ComfyUI queue (optional, for debugging) |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Panel not accessible | Check that the START.bat console is open. Reload `http://127.0.0.1:7860`. |
| NAS connection failure in log | Check credentials in the panel and verify the share is reachable. |
| "ComfyUI not responding" in log | Normal for the first ~40 s or during heavy jobs. The watcher retries automatically. |
| CUDA out of memory | Lower `max_num_tokens`. Keep `pipeline_type` at `1024_cascade`. |
| Image lands in `failed/` | Check `pipeline/comfyui.log` for the root cause. |
| Full restart | Close the START.bat console, relaunch START.bat. |

`run_watcher.bat` launches the watcher alone without the control panel, useful
for debugging.

---

## Technical notes

- Stack: ComfyUI portable 0.22, Python 3.13, PyTorch 2.11, CUDA 13.
- Background removal runs in the watcher via `rembg`, independent of ComfyUI.
- `download_if_missing` is set to `False` in the ComfyUI node config.
  Models must be downloaded in advance with `hf_grab.ps1`. Downloading 24 GB
  mid-job would cause a timeout.
- The built-in RMBG-2.0 node inside Pixal3D is disabled (incompatible with
  transformers 5.x). Two patches marked `# PATCH:` in
  `pixal3d_comfy/runtime.py` handle this.
- `hf_grab.ps1` supports resumable downloads, parallel-safe partial files,
  and HuggingFace token auth via the `HF_TOKEN` environment variable.

---

## Star History

<a href="https://www.star-history.com/?repos=infinition%2FPixal3D-pipeline&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=infinition/Pixal3D-pipeline&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=infinition/Pixal3D-pipeline&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=infinition/Pixal3D-pipeline&type=date&legend=top-left" />
 </picture>
</a>

---

## Credits & Attribution

- **Original Models & Research**: [TencentARC/Pixal3D](https://huggingface.co/TencentARC/Pixal3D)
- **ComfyUI Node Integration**: Developed by [Saganaki22](https://github.com/Saganaki22) in [Pixal3D-ComfyUI](https://github.com/Saganaki22/Pixal3D-ComfyUI). This pipeline operates as an automation layer specifically designed around these custom nodes.

## License

MIT
