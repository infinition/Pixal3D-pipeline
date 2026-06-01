"""Pixal3D - Panneau de controle (Gradio).

UI navigateur : demarre/arrete/redemarre ComfyUI et le watcher, configure les
dossiers (locaux ou NAS) et tous les parametres de generation, affiche le
journal du watcher en direct.

Lance par START.bat. Ouvre http://127.0.0.1:7860 dans le navigateur.
"""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import gradio as gr

# ------------------------------- Chemins ------------------------------------
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
    return "**Reglages enregistres.** Appliques a la prochaine image traitee."


# --------------------------- Gestion processus ------------------------------
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
        return "ComfyUI est deja en marche."
    if alive("comfyui"):
        return "ComfyUI demarre deja..."
    env = dict(os.environ)
    env["HF_HUB_DISABLE_XET"] = "1"
    fh = _open_log("comfyui", COMFY_LOG)
    PROC["comfyui"] = subprocess.Popen(
        [str(PYTHON), "-s", str(COMFY_MAIN), "--windows-standalone-build"],
        cwd=str(PORTABLE), env=env, stdout=fh, stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    return "ComfyUI demarre (compter ~40 s avant qu'il soit pret)."


def start_watcher() -> str:
    if alive("watcher"):
        return "Le watcher tourne deja."
    fh = _open_log("watcher", WATCHER_LOG)
    PROC["watcher"] = subprocess.Popen(
        [str(PYTHON), "-s", str(WATCHER)],
        cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    return "Watcher demarre."


def stop_proc(name: str) -> str:
    p = PROC.get(name)
    if p is None or p.poll() is not None:
        PROC[name] = None
        return f"{name} n'etait pas en marche."
    p.terminate()
    try:
        p.wait(timeout=10)
    except Exception:
        p.kill()
    PROC[name] = None
    return f"{name} arrete."


def restart_watcher() -> str:
    stop_proc("watcher")
    start_watcher()
    return "Watcher redemarre (recharge config.json)."


def cleanup() -> None:
    for name in ("watcher", "comfyui"):
        p = PROC.get(name)
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


atexit.register(cleanup)


# ------------------------------- Affichage ----------------------------------
def status_markdown() -> str:
    if comfy_reachable():
        comfy = "**ComfyUI** : \U0001F7E2 en marche (pret)"
    elif alive("comfyui"):
        comfy = "**ComfyUI** : \U0001F7E1 demarrage en cours..."
    else:
        comfy = "**ComfyUI** : \U0001F534 arrete"
    watcher = ("**Watcher** : \U0001F7E2 en marche" if alive("watcher")
               else "**Watcher** : \U0001F534 arrete")
    return f"{comfy}  &nbsp;&nbsp;|&nbsp;&nbsp;  {watcher}"


def tail_log(path: Path, lines: int = 200) -> str:
    if not path.exists():
        return "(journal vide)"
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return f"(lecture impossible: {exc})"
    return "\n".join(content[-lines:]) or "(journal vide)"


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
        return f"Dossier ouvert : {target}"
    except Exception as exc:
        return f"Impossible d'ouvrir : {target} ({exc})"


# --------------------------------- UI ---------------------------------------
def build_ui() -> gr.Blocks:
    cfg = load_config()
    with gr.Blocks(title="Pixal3D - Panneau de controle") as app:
        gr.Markdown("# Pixal3D — Panneau de controle")
        gr.Markdown(
            "Depose tes images dans le **dossier d'entree** — les modeles 3D `.glb` "
            "sortent dans le **dossier de sortie** (configurables ci-dessous)."
        )

        status = gr.Markdown(status_markdown())
        action_msg = gr.Markdown("")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### ComfyUI (moteur 3D)")
                with gr.Row():
                    comfy_start = gr.Button("Demarrer", variant="primary")
                    comfy_stop = gr.Button("Arreter")
            with gr.Column():
                gr.Markdown("### Watcher (pipeline)")
                with gr.Row():
                    watcher_start = gr.Button("Demarrer", variant="primary")
                    watcher_stop = gr.Button("Arreter")
                    watcher_restart = gr.Button("Redemarrer")

        with gr.Accordion("Dossiers & NAS", open=True):
            inbox_dir = gr.Textbox(
                value=cfg["inbox_dir"], label="Dossier d'entree (images a traiter)",
                placeholder="Vide = pipeline/inbox (local)",
                info="Dossier surveille. Local (D:\\images) ou reseau "
                     "(\\\\192.168.1.75\\Downloads\\3D\\in). Vide = dossier local par defaut.",
            )
            output_dir = gr.Textbox(
                value=cfg["output_dir"], label="Dossier de sortie (modeles .glb)",
                placeholder="Vide = pipeline/results (local)",
                info="Ou sont deposes les .glb generes. Local ou reseau. "
                     "Vide = dossier local par defaut.",
            )
            with gr.Row():
                nas_user = gr.Textbox(
                    value=cfg["nas_user"], label="NAS - identifiant",
                    info="Pour un dossier reseau protege. Vide si dossiers locaux.",
                )
                nas_password = gr.Textbox(
                    value=cfg["nas_password"], label="NAS - mot de passe",
                    type="password", info="Stocke en clair dans config.json.",
                )

        with gr.Accordion("Reglages de generation", open=True):
            gr.Markdown("#### Geometrie / precision du modele 3D")
            pipeline_type = gr.Dropdown(
                ["1024_cascade", "1536_cascade"],
                value=cfg["pipeline_type"], label="Type de pipeline",
                info="Resolution interne. 1024 = recommande (12 Go VRAM). "
                     "1536 = plus de detail mais risque de CUDA out of memory.",
            )
            steps = gr.Slider(
                4, 50, value=int(cfg["steps"]), step=1,
                label="Steps (etapes de generation)",
                info="Iterations de debruitage (forme ET texture). Plus eleve = plus de "
                     "detail et de fidelite, plus lent. 12 = rapide, 20 = qualite.",
            )
            guidance = gr.Slider(
                1.0, 15.0, value=float(cfg["guidance"]), step=0.5, label="Guidance",
                info="A quel point la FORME 3D suit l'image. 7.5 = equilibre. "
                     "Trop haut = artefacts ; trop bas = forme imprecise.",
            )
            max_num_tokens = gr.Slider(
                16384, 131072, value=int(cfg["max_num_tokens"]), step=16384,
                label="Max tokens (precision geometrique)",
                info="Budget de jetons de la structure 3D = finesse du maillage genere. "
                     "Plus eleve = geometrie plus precise, mais beaucoup plus de VRAM "
                     "(risque d'OOM au-dela de ~65000 sur 12 Go).",
            )
            mesh_scale = gr.Slider(
                0.1, 5.0, value=float(cfg["mesh_scale"]), step=0.1, label="Echelle du mesh",
                info="Taille du modele 3D exporte. 1.0 = taille normale.",
            )
            camera_resolution = gr.Dropdown(
                [384, 512, 768, 1024],
                value=int(cfg["camera_resolution"]), label="Resolution d'analyse",
                info="Resolution a laquelle l'image est analysee. Plus eleve = capte plus "
                     "de detail, un peu plus lourd. 512 = standard.",
            )
            remesh = gr.Checkbox(
                value=bool(cfg["remesh"]), label="Remesh (retopologie propre)",
                info="Recalcule une topologie de maillage propre et reguliere. "
                     "Recommande pour des assets exploitables.",
            )
            decimation_target = gr.Slider(
                100_000, 5_000_000, value=int(cfg["decimation_target"]), step=100_000,
                label="Cible de decimation (triangles)",
                info="Nombre de triangles vise pour le mesh final. Plus eleve = mesh plus "
                     "dense et detaille, fichier .glb plus gros.",
            )

            gr.Markdown("#### Texture")
            texture_guidance = gr.Slider(
                0.5, 3.0, value=float(cfg["texture_guidance"]), step=0.1,
                label="Texture guidance",
                info="Fidelite de la texture a l'image source. Plus eleve = texture plus "
                     "proche de la photo d'origine.",
            )
            texture_size = gr.Dropdown(
                [1024, 2048, 4096],
                value=int(cfg["texture_size"]), label="Taille de texture (pixels)",
                info="Resolution de la texture. 2048 = standard. 4096 = tres net, "
                     "fichier plus lourd.",
            )

            gr.Markdown("#### Detourage & cadrage")
            rembg_model = gr.Dropdown(
                ["isnet-general-use", "birefnet-general", "u2net"],
                value=cfg["rembg_model"], label="Modele de detourage",
                info="Retire le fond de l'image. isnet = bon compromis. "
                     "birefnet = decoupe plus precise mais plus lourd. u2net = leger.",
            )
            camera_mode = gr.Dropdown(
                ["moge", "manual"],
                value=cfg["camera_mode"], label="Mode camera",
                info="moge = cadrage/profondeur estimes automatiquement. "
                     "manual = cadrage fixe.",
            )

            save_btn = gr.Button("Enregistrer les reglages", variant="primary")
            save_msg = gr.Markdown("")

        gr.Markdown("### Journal du watcher")
        log_box = gr.Textbox(
            value=tail_log(WATCHER_LOG), lines=18, max_lines=18, autoscroll=True,
            show_label=False, interactive=False,
        )

        with gr.Row():
            open_inbox = gr.Button("Ouvrir le dossier d'entree")
            open_results = gr.Button("Ouvrir le dossier de sortie")
        gr.Markdown(f"Interface ComfyUI (optionnel) : [{COMFY_URL}]({COMFY_URL})")

        # --- Cablage (apres creation de tous les composants) ---
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
    print("Demarrage automatique de ComfyUI et du watcher...", flush=True)
    print(" - " + start_comfyui(), flush=True)
    print(" - " + start_watcher(), flush=True)
    print("Ouverture du panneau sur http://127.0.0.1:7860 ...", flush=True)
    build_ui().launch(
        server_name="127.0.0.1", server_port=7860,
        inbrowser=True, quiet=True, theme=gr.themes.Soft(),
    )
