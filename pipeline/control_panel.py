"""Pixal3D - Control panel (Gradio).

Browser UI: start/stop/restart ComfyUI and the watcher, configure folders
(local or NAS) and all generation parameters, display the watcher log live.

Launched by START.bat. Opens http://127.0.0.1:7860 in the browser.
"""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import gradio as gr

# ------------------------------- Paths ------------------------------------
ROOT = Path(__file__).resolve().parent                 # pipeline/
PORTABLE = ROOT.parent / "ComfyUI_windows_portable"
PYTHON = PORTABLE / "python_embeded" / "python.exe"
COMFY_MAIN = PORTABLE / "ComfyUI" / "main.py"
WATCHER = ROOT / "watch_pixal3d.py"
CONFIG_PATH = ROOT / "config.json"
WATCHER_LOG = ROOT / "watcher.log"
COMFY_LOG = ROOT / "comfyui.log"
COMFY_URL = "http://127.0.0.1:8188"

CREATE_NO_WINDOW = 0x08000000

DEFAULTS = {
    "inbox_dir": "",
    "output_dir": "",
    "nas_user": "",
    "nas_password": "",
    "rembg_model": "isnet-general-use",
    "pipeline_type": "1024_cascade",
    "camera_mode": "moge",
    "steps": 20,
    "guidance": 7.5,
    "max_num_tokens": 49152,
    "mesh_scale": 1.0,
    "camera_resolution": 512,
    "remesh": True,
    "decimation_target": 2500000,
    "texture_guidance": 1.0,
    "texture_size": 4096,
}

PROC: dict[str, subprocess.Popen | None] = {"comfyui": None, "watcher": None}
LOGFILES: dict[str, object] = {}


# ------------------------------- Config -------------------------------------
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(inbox_dir, output_dir, nas_user, nas_password,
                rembg_model, camera_mode, pipeline_type, steps, guidance,
                max_num_tokens, mesh_scale, camera_resolution, remesh,
                decimation_target, texture_guidance, texture_size) -> str:
    cfg = {
        "inbox_dir": (inbox_dir or "").strip(),
        "output_dir": (output_dir or "").strip(),
        "nas_user": (nas_user or "").strip(),
        "nas_password": nas_password or "",
        "rembg_model": rembg_model,
        "pipeline_type": pipeline_type,
        "camera_mode": camera_mode,
        "steps": int(steps),
        "guidance": round(float(guidance), 2),
        "max_num_tokens": int(max_num_tokens),
        "mesh_scale": round(float(mesh_scale), 2),
        "camera_resolution": int(camera_resolution),
        "remesh": bool(remesh),
        "decimation_target": int(decimation_target),
        "texture_guidance": round(float(texture_guidance), 2),
        "texture_size": int(texture_size),
    }
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return "**Settings saved.** Applied to the next image processed."


# --------------------------- Process management -----------------------------
def comfy_reachable() -> bool:
    try:
        urllib.request.urlopen(COMFY_URL + "/system_stats", timeout=4)
        return True
    except Exception:
        return False


def alive(name: str) -> bool:
    p = PROC.get(name)
    return p is not None and p.poll() is None


def _open_log(name: str, path: Path):
    old = LOGFILES.pop(name, None)
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
    fh = open(path, "w", encoding="utf-8", errors="replace")
    LOGFILES[name] = fh
    return fh


def start_comfyui() -> str:
    if comfy_reachable():
        return "ComfyUI is already running."
    if alive("comfyui"):
        return "ComfyUI is already starting..."
    env = dict(os.environ)
    env["HF_HUB_DISABLE_XET"] = "1"
    fh = _open_log("comfyui", COMFY_LOG)
    PROC["comfyui"] = subprocess.Popen(
        [str(PYTHON), "-s", str(COMFY_MAIN), "--windows-standalone-build"],
        cwd=str(PORTABLE), env=env, stdout=fh, stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    return "ComfyUI starting (~40 s before it is ready)."


def start_watcher() -> str:
    if alive("watcher"):
        return "Watcher is already running."
    fh = _open_log("watcher", WATCHER_LOG)
    PROC["watcher"] = subprocess.Popen(
        [str(PYTHON), "-s", str(WATCHER)],
        cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    return "Watcher started."


def stop_proc(name: str) -> str:
    p = PROC.get(name)
    if p is None or p.poll() is not None:
        PROC[name] = None
        return f"{name} was not running."
    p.terminate()
    try:
        p.wait(timeout=10)
    except Exception:
        p.kill()
    PROC[name] = None
    return f"{name} stopped."


def restart_watcher() -> str:
    stop_proc("watcher")
    start_watcher()
    return "Watcher restarted (config.json reloaded)."


def cleanup() -> None:
    for name in ("watcher", "comfyui"):
        p = PROC.get(name)
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


atexit.register(cleanup)


# ------------------------------- Display ------------------------------------
def status_markdown() -> str:
    if comfy_reachable():
        comfy = "**ComfyUI** : \U0001F7E2 running (ready)"
    elif alive("comfyui"):
        comfy = "**ComfyUI** : \U0001F7E1 starting..."
    else:
        comfy = "**ComfyUI** : \U0001F534 stopped"
    watcher = ("**Watcher** : \U0001F7E2 running" if alive("watcher")
               else "**Watcher** : \U0001F534 stopped")
    return f"{comfy}  &nbsp;&nbsp;|&nbsp;&nbsp;  {watcher}"


def tail_log(path: Path, lines: int = 200) -> str:
    if not path.exists():
        return "(empty log)"
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return f"(could not read log: {exc})"
    return "\n".join(content[-lines:]) or "(empty log)"


def refresh():
    return status_markdown(), tail_log(WATCHER_LOG)


def open_folder(which: str) -> str:
    cfg = load_config()
    if which == "inbox":
        target = cfg["inbox_dir"].strip() or str(ROOT / "inbox")
    else:
        target = cfg["output_dir"].strip() or str(ROOT / "results")
    try:
        os.startfile(target)
        return f"Opened: {target}"
    except Exception as exc:
        return f"Could not open: {target} ({exc})"


# --------------------------------- UI ---------------------------------------
def build_ui() -> gr.Blocks:
    cfg = load_config()
    with gr.Blocks(title="Pixal3D - Control Panel") as app:
        gr.Markdown("# Pixal3D - Control Panel")
        gr.Markdown(
            "Drop images into the **inbox folder** and `.glb` models will appear "
            "in the **output folder** (both configurable below)."
        )

        status = gr.Markdown(status_markdown())
        action_msg = gr.Markdown("")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### ComfyUI (3D engine)")
                with gr.Row():
                    comfy_start = gr.Button("Start", variant="primary")
                    comfy_stop = gr.Button("Stop")
            with gr.Column():
                gr.Markdown("### Watcher (pipeline)")
                with gr.Row():
                    watcher_start = gr.Button("Start", variant="primary")
                    watcher_stop = gr.Button("Stop")
                    watcher_restart = gr.Button("Restart")

        with gr.Accordion("Folders & NAS", open=True):
            inbox_dir = gr.Textbox(
                value=cfg["inbox_dir"], label="Inbox folder (images to process)",
                placeholder="Empty = pipeline/inbox (local)",
                info="Watched folder. Local (D:\\images) or network "
                     "(\\\\server\\share\\in). Leave empty for the local default.",
            )
            output_dir = gr.Textbox(
                value=cfg["output_dir"], label="Output folder (.glb models)",
                placeholder="Empty = pipeline/results (local)",
                info="Where generated .glb files are placed. Local or network. "
                     "Leave empty for the local default.",
            )
            with gr.Row():
                nas_user = gr.Textbox(
                    value=cfg["nas_user"], label="NAS username",
                    info="For a password-protected network share. Leave empty for local folders.",
                )
                nas_password = gr.Textbox(
                    value=cfg["nas_password"], label="NAS password",
                    type="password", info="Stored in plain text in config.json.",
                )

        with gr.Accordion("Generation settings", open=True):
            gr.Markdown("#### Geometry / mesh precision")
            pipeline_type = gr.Dropdown(
                ["1024_cascade", "1536_cascade"],
                value=cfg["pipeline_type"], label="Pipeline type",
                info="Internal resolution. 1024 = recommended (12 GB VRAM). "
                     "1536 = more detail but risks CUDA out of memory.",
            )
            steps = gr.Slider(
                4, 50, value=int(cfg["steps"]), step=1,
                label="Steps",
                info="Denoising iterations (shape and texture). Higher = more detail, slower. "
                     "12 = fast, 20 = quality.",
            )
            guidance = gr.Slider(
                1.0, 15.0, value=float(cfg["guidance"]), step=0.5, label="Guidance",
                info="How closely the 3D shape follows the image. 7.5 is a balanced default. "
                     "Too high = artifacts, too low = imprecise shape.",
            )
            max_num_tokens = gr.Slider(
                16384, 131072, value=int(cfg["max_num_tokens"]), step=16384,
                label="Max tokens (geometric precision)",
                info="Token budget for the 3D structure. Higher = finer mesh but much more VRAM. "
                     "Stay below ~65000 on 12 GB.",
            )
            mesh_scale = gr.Slider(
                0.1, 5.0, value=float(cfg["mesh_scale"]), step=0.1, label="Mesh scale",
                info="Scale of the exported 3D model. 1.0 = normal size.",
            )
            camera_resolution = gr.Dropdown(
                [384, 512, 768, 1024],
                value=int(cfg["camera_resolution"]), label="Analysis resolution",
                info="Resolution at which the image is analysed. Higher = more detail captured. "
                     "512 is standard.",
            )
            remesh = gr.Checkbox(
                value=bool(cfg["remesh"]), label="Remesh (clean topology)",
                info="Recomputes a clean, uniform mesh topology. Recommended for usable assets.",
            )
            decimation_target = gr.Slider(
                100_000, 5_000_000, value=int(cfg["decimation_target"]), step=100_000,
                label="Decimation target (triangles)",
                info="Target triangle count for the final mesh. Higher = denser mesh, larger .glb.",
            )

            gr.Markdown("#### Texture")
            texture_guidance = gr.Slider(
                0.5, 3.0, value=float(cfg["texture_guidance"]), step=0.1,
                label="Texture guidance",
                info="How closely the texture follows the source image. "
                     "Higher = closer to the original photo.",
            )
            texture_size = gr.Dropdown(
                [1024, 2048, 4096],
                value=int(cfg["texture_size"]), label="Texture size (pixels)",
                info="Texture resolution. 2048 = standard. 4096 = sharp detail, larger file.",
            )

            gr.Markdown("#### Background removal & framing")
            rembg_model = gr.Dropdown(
                ["isnet-general-use", "birefnet-general", "u2net"],
                value=cfg["rembg_model"], label="Background removal model",
                info="Removes the image background. isnet = good default. "
                     "birefnet = more precise but heavier. u2net = lightweight.",
            )
            camera_mode = gr.Dropdown(
                ["moge", "manual"],
                value=cfg["camera_mode"], label="Camera mode",
                info="moge = depth and framing estimated automatically. "
                     "manual = fixed framing.",
            )

            save_btn = gr.Button("Save settings", variant="primary")
            save_msg = gr.Markdown("")

        gr.Markdown("### Watcher log")
        log_box = gr.Textbox(
            value=tail_log(WATCHER_LOG), lines=18, max_lines=18, autoscroll=True,
            show_label=False, interactive=False,
        )

        with gr.Row():
            open_inbox = gr.Button("Open inbox folder")
            open_results = gr.Button("Open output folder")
        gr.Markdown(f"ComfyUI interface (optional): [{COMFY_URL}]({COMFY_URL})")

        # --- Wiring ---
        comfy_start.click(lambda: start_comfyui(), outputs=action_msg)
        comfy_stop.click(lambda: stop_proc("comfyui"), outputs=action_msg)
        watcher_start.click(lambda: start_watcher(), outputs=action_msg)
        watcher_stop.click(lambda: stop_proc("watcher"), outputs=action_msg)
        watcher_restart.click(lambda: restart_watcher(), outputs=action_msg)
        open_inbox.click(lambda: open_folder("inbox"), outputs=action_msg)
        open_results.click(lambda: open_folder("output"), outputs=action_msg)
        save_btn.click(
            save_config,
            inputs=[inbox_dir, output_dir, nas_user, nas_password,
                    rembg_model, camera_mode, pipeline_type, steps, guidance,
                    max_num_tokens, mesh_scale, camera_resolution, remesh,
                    decimation_target, texture_guidance, texture_size],
            outputs=save_msg,
        )

        timer = gr.Timer(2.0)
        timer.tick(refresh, outputs=[status, log_box])

    return app


if __name__ == "__main__":
    print("Auto-starting ComfyUI and watcher...", flush=True)
    print(" - " + start_comfyui(), flush=True)
    print(" - " + start_watcher(), flush=True)
    print("Opening panel at http://127.0.0.1:7860 ...", flush=True)
    build_ui().launch(
        server_name="127.0.0.1", server_port=7860,
        inbrowser=True, quiet=True, theme=gr.themes.Soft(),
    )
