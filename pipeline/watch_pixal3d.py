"""Pixal3D batch watcher.

Surveille un dossier d'entree : pour chaque nouvelle image, retire le fond
(rembg), soumet un job image->3D a l'API ComfyUI, puis range les fichiers :
  - image source -> pipeline/processed/   (succes)  ou pipeline/failed/ (erreur)
  - modele 3D    -> dossier de sortie configure

Dossiers d'entree/sortie et parametres de generation sont lus depuis
pipeline/config.json a chaque cycle (modifiables via le panneau de controle).
Les dossiers peuvent etre locaux ou des chemins reseau (NAS, \\\\serveur\\partage).

Lance ComfyUI separement avant de demarrer ce watcher.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ----------------------------- Chemins locaux -------------------------------
ROOT = Path(__file__).resolve().parent
INBOX_DEFAULT = ROOT / "inbox"
RESULTS_DEFAULT = ROOT / "results"
WORKING = ROOT / "working"
PROCESSED = ROOT / "processed"
FAILED = ROOT / "failed"
CONFIG_PATH = ROOT / "config.json"

PORTABLE = ROOT.parent / "ComfyUI_windows_portable"
COMFY_INPUT = PORTABLE / "ComfyUI" / "input"
COMFY_OUTPUT = PORTABLE / "ComfyUI" / "output"
COMFY_URL = "http://127.0.0.1:8188"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
POLL_SECONDS = 5
CLIENT_ID = "pixal3d-watcher"
CREATE_NO_WINDOW = 0x08000000

# Parametres par defaut (surcharges par config.json)
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

_rembg_sessions: dict[str, object] = {}
_nas_authed: set[str] = set()


def log(msg: str) -> None:
    text = f"{datetime.now():%H:%M:%S}  {msg}"
    print(text, flush=True)
    try:
        with open(ROOT / "watcher.log", "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def safe_stem(name: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
    return keep.strip("_") or "image"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception as exc:
        log(f"[config] config.json illisible ({exc}); valeurs par defaut.")
    return cfg


# ------------------------------ Dossiers / NAS -------------------------------
def resolve_dirs(cfg: dict) -> tuple[Path, Path]:
    inbox = Path(cfg["inbox_dir"]) if str(cfg.get("inbox_dir", "")).strip() else INBOX_DEFAULT
    output = Path(cfg["output_dir"]) if str(cfg.get("output_dir", "")).strip() else RESULTS_DEFAULT
    return inbox, output


def unc_share(path_str: str) -> str | None:
    """Racine de partage d'un chemin UNC : \\\\serveur\\partage\\... -> \\\\serveur\\partage."""
    p = path_str.replace("/", "\\")
    if not p.startswith("\\\\"):
        return None
    parts = [x for x in p.split("\\") if x]
    if len(parts) < 2:
        return None
    return "\\\\" + parts[0] + "\\" + parts[1]


def ensure_nas(cfg: dict, dirs: list[Path]) -> None:
    """Authentifie les partages reseau (net use) si besoin."""
    user = str(cfg.get("nas_user", "")).strip()
    pwd = str(cfg.get("nas_password", ""))
    if not user:
        return
    for d in dirs:
        share = unc_share(str(d))
        if not share or share in _nas_authed:
            continue
        try:
            subprocess.run(
                ["net", "use", share, f"/user:{user}", pwd],
                capture_output=True, text=True, timeout=25, creationflags=CREATE_NO_WINDOW,
            )
            _nas_authed.add(share)
            log(f"[NAS] connexion etablie : {share}")
        except Exception as exc:
            log(f"[NAS] echec connexion {share}: {exc}")


# ------------------------------- Detourage ----------------------------------
def remove_background(src: Path, dst: Path, model: str) -> None:
    from PIL import Image
    from rembg import new_session, remove

    session = _rembg_sessions.get(model)
    if session is None:
        log(f"[rembg] chargement du modele '{model}' (1er appel, peut telecharger)...")
        session = new_session(model)
        _rembg_sessions[model] = session
    with Image.open(src) as im:
        cut = remove(im.convert("RGB"), session=session)
    cut.save(dst)


# ------------------------------- API ComfyUI --------------------------------
def comfy_request(path: str, payload: dict | None = None, timeout: int = 90):
    url = COMFY_URL + path
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def comfy_alive() -> bool:
    try:
        comfy_request("/system_stats", timeout=20)
        return True
    except Exception:
        return False


def build_prompt(image_filename: str, prefix: str, seed: int, cfg: dict) -> dict:
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": image_filename},
        },
        "2": {
            "class_type": "Pixal3DModelLoader",
            "inputs": {
                "model_repo": "TencentARC/Pixal3D",
                "hf_endpoint": "https://huggingface.co",
                "attention_backend": "auto",
                "vram_mode": "dynamic_vram",
                "download_if_missing": False,
                "load_moge": True,
                "load_rembg": False,
                "naf_mode": "fallback_if_missing",
                "naf_target_size": "upstream",
                "preload_naf": False,
                "force_reload": False,
            },
        },
        "3": {
            "class_type": "Pixal3DImageTo3D",
            "inputs": {
                "model": ["2", 0],
                "image": ["1", 0],
                "seed": seed,
                "pipeline_type": cfg["pipeline_type"],
                "background_mode": "keep_alpha",
                "camera_mode": cfg["camera_mode"],
                "manual_camera_angle_x": 0.857556,
                "manual_distance": 2.0,
                "mesh_scale": float(cfg["mesh_scale"]),
                "extend_pixel": 0,
                "camera_resolution": int(cfg["camera_resolution"]),
                "steps": int(cfg["steps"]),
                "guidance": float(cfg["guidance"]),
                "texture_guidance": float(cfg["texture_guidance"]),
                "max_num_tokens": int(cfg["max_num_tokens"]),
                "force_offload": False,
            },
        },
        "4": {
            "class_type": "Pixal3DExportGLB",
            "inputs": {
                "pixal3d_result": ["3", 0],
                "decimation_target": int(cfg["decimation_target"]),
                "texture_size": int(cfg["texture_size"]),
                "remesh": bool(cfg["remesh"]),
                "filename_prefix": prefix,
            },
        },
    }


def submit_job(image_filename: str, prefix: str, cfg: dict) -> str:
    seed = random.randint(0, 2**31 - 1)
    res = comfy_request(
        "/prompt",
        {"prompt": build_prompt(image_filename, prefix, seed, cfg), "client_id": CLIENT_ID},
        timeout=60,
    )
    if res.get("node_errors"):
        raise RuntimeError(f"node_errors: {res['node_errors']}")
    return res["prompt_id"]


def job_status(prompt_id: str) -> str:
    hist = comfy_request(f"/history/{prompt_id}")
    entry = hist.get(prompt_id)
    if not entry:
        return "running"
    status = entry.get("status", {})
    if status.get("status_str") == "error":
        return "error"
    if status.get("status_str") == "success" or status.get("completed"):
        return "success"
    return "running"


def find_glb(prefix: str) -> Path | None:
    matches = sorted(
        COMFY_OUTPUT.rglob(f"{prefix}*.glb"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return matches[0] if matches else None


# --------------------------------- Boucle -----------------------------------
def process_inbox(pending: dict, sizes: dict, cfg: dict, inbox_dir: Path) -> None:
    if not inbox_dir.exists():
        _nas_authed.clear()
        ensure_nas(cfg, [inbox_dir])
        if not inbox_dir.exists():
            return
    for img in sorted(inbox_dir.iterdir()):
        if not img.is_file() or img.suffix.lower() not in IMAGE_EXTS:
            continue
        size = img.stat().st_size
        if sizes.get(img.name) != size:   # encore en cours de copie
            sizes[img.name] = size
            continue
        sizes.pop(img.name, None)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = safe_stem(img.stem)
        prefix = f"pxlw_{stem}_{stamp}"
        input_temp = COMFY_INPUT / f"{prefix}.png"

        try:
            log(f"[detour] {img.name} ...")
            remove_background(img, input_temp, cfg["rembg_model"])
        except Exception as exc:
            log(f"[ERREUR detour] {img.name}: {exc} -> failed/")
            input_temp.unlink(missing_ok=True)
            shutil.move(str(img), str(FAILED / img.name))
            continue

        try:
            prompt_id = submit_job(input_temp.name, prefix, cfg)
        except urllib.error.URLError:
            log(f"[attente] {img.name}: ComfyUI injoignable, nouvel essai au prochain cycle.")
            input_temp.unlink(missing_ok=True)
            continue
        except Exception as exc:
            log(f"[ERREUR soumission] {img.name}: {exc} -> failed/")
            input_temp.unlink(missing_ok=True)
            shutil.move(str(img), str(FAILED / img.name))
            continue

        working = WORKING / img.name
        shutil.move(str(img), str(working))
        pending[prompt_id] = {
            "name": img.name,
            "working": working,
            "prefix": prefix,
            "input_temp": input_temp,
        }
        log(f"[file] {img.name} -> job {prompt_id[:8]} ({len(pending)} job(s) en file)")


def poll_jobs(pending: dict, output_dir: Path) -> None:
    for prompt_id in list(pending):
        info = pending[prompt_id]
        try:
            state = job_status(prompt_id)
        except Exception:
            continue
        if state == "running":
            continue

        info["input_temp"].unlink(missing_ok=True)
        if state == "success":
            glb = find_glb(info["prefix"])
            if glb is None:
                log(f"[ATTENTION] {info['name']}: job fini mais GLB introuvable -> failed/")
                shutil.move(str(info["working"]), str(FAILED / info["name"]))
            else:
                stem = safe_stem(Path(info["name"]).stem)
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    dest = output_dir / f"{stem}.glb"
                    if dest.exists():
                        dest = output_dir / f"{stem}_{glb.stem}.glb"
                    shutil.copy2(str(glb), str(dest))
                    shutil.move(str(info["working"]), str(PROCESSED / info["name"]))
                    log(f"[OK] {info['name']} -> {dest}")
                except Exception as exc:
                    log(f"[ERREUR copie sortie] {info['name']}: {exc} -> failed/")
                    shutil.move(str(info["working"]), str(FAILED / info["name"]))
        else:
            log(f"[ECHEC] {info['name']} (voir la console ComfyUI) -> failed/")
            shutil.move(str(info["working"]), str(FAILED / info["name"]))
        del pending[prompt_id]


def main(stop_event: threading.Event | None = None) -> None:
    for d in (INBOX_DEFAULT, RESULTS_DEFAULT, WORKING, PROCESSED, FAILED):
        d.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    inbox_dir, output_dir = resolve_dirs(cfg)
    ensure_nas(cfg, [inbox_dir, output_dir])
    log("=== Pixal3D watcher ===")
    log(f"entree : {inbox_dir}")
    log(f"sortie : {output_dir}")
    log(f"reglages : detour={cfg['rembg_model']} | {cfg['pipeline_type']} | "
        f"steps={cfg['steps']} | tokens={cfg['max_num_tokens']} | texture={cfg['texture_size']}")
    log("Depose des images dans le dossier d'entree.  (Ctrl+C pour arreter)")

    pending: dict[str, dict] = {}
    sizes: dict[str, int] = {}
    down_cycles = 0

    while True:
        if stop_event and stop_event.is_set():
            log("Signal d'arret recu. Fermeture du watcher.")
            break
        try:
            cfg = load_config()
            inbox_dir, output_dir = resolve_dirs(cfg)
            ensure_nas(cfg, [inbox_dir, output_dir])
            if comfy_alive():
                if down_cycles:
                    log("ComfyUI de nouveau joignable.")
                down_cycles = 0
                process_inbox(pending, sizes, cfg, inbox_dir)
            else:
                down_cycles += 1
                if down_cycles == 1 or down_cycles % 12 == 0:
                    log("ComfyUI ne repond pas (occupe par un job, ou pas lance). En attente...")
            poll_jobs(pending, output_dir)
        except KeyboardInterrupt:
            log("Arret demande. Bye.")
            return
        except Exception as exc:
            log(f"[boucle] erreur inattendue: {exc}")

        # Responsive sleep check
        for _ in range(POLL_SECONDS):
            if stop_event and stop_event.is_set():
                break
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
