"""Recherche autonome des reglages de qualite max avant OOM (12 Go VRAM).

Teste pipeline_type, puis pousse max_num_tokens par paliers jusqu'a l'OOM,
sur une image de test. Ecrit les reglages optimaux trouves dans config.json.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORTABLE = ROOT.parent / "ComfyUI_windows_portable"
COMFY_INPUT = PORTABLE / "ComfyUI" / "input"
COMFY_OUTPUT = PORTABLE / "ComfyUI" / "output"
COMFY_LOG = ROOT / "comfyui.log"
CONFIG_PATH = ROOT / "config.json"
COMFY_URL = "http://127.0.0.1:8188"

TEST_SRC = ROOT / "processed" / "router.png"
TEST_IMG = COMFY_INPUT / "oom_test.png"

JOB_TIMEOUT = 1800          # 30 min max par job
TEST_STEPS = 12             # steps n'affecte pas le pic VRAM -> bas = tests rapides
TOKEN_LADDER = [65536, 81920, 98304, 114688, 131072]


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


def detour_test_image() -> None:
    from PIL import Image
    from rembg import new_session, remove
    log(f"Detourage de l'image de test : {TEST_SRC.name}")
    sess = new_session("isnet-general-use")
    with Image.open(TEST_SRC) as im:
        remove(im.convert("RGB"), session=sess).save(TEST_IMG)


def comfy(path: str, payload: dict | None = None, timeout: int = 60):
    url = COMFY_URL + path
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_prompt(pipeline_type: str, max_num_tokens: int, seed: int) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": TEST_IMG.name}},
        "2": {"class_type": "Pixal3DModelLoader", "inputs": {
            "model_repo": "TencentARC/Pixal3D", "hf_endpoint": "https://huggingface.co",
            "attention_backend": "auto", "vram_mode": "dynamic_vram",
            "download_if_missing": False, "load_moge": True, "load_rembg": False,
            "naf_mode": "fallback_if_missing", "naf_target_size": "upstream",
            "preload_naf": False, "force_reload": False}},
        "3": {"class_type": "Pixal3DImageTo3D", "inputs": {
            "model": ["2", 0], "image": ["1", 0], "seed": seed,
            "pipeline_type": pipeline_type, "background_mode": "keep_alpha",
            "camera_mode": "moge", "manual_camera_angle_x": 0.857556,
            "manual_distance": 2.0, "mesh_scale": 1.0, "extend_pixel": 0,
            "camera_resolution": 512, "steps": TEST_STEPS, "guidance": 7.5,
            "texture_guidance": 1.0, "max_num_tokens": max_num_tokens,
            "force_offload": False}},
        "4": {"class_type": "Pixal3DExportGLB", "inputs": {
            "pixal3d_result": ["3", 0], "decimation_target": 2500000,
            "texture_size": 4096, "remesh": True, "filename_prefix": "oom_test"}},
    }


def looks_like_oom(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in (
        "out of memory", "outofmemory", "cuda error", "cuda out of memory",
        "alloc", "cudamalloc", "not enough memory",
    ))


def run(pipeline_type: str, max_num_tokens: int) -> tuple[str, float]:
    """Retourne ('OK'|'OOM'|'ERR', secondes)."""
    seed = random.randint(0, 2**31 - 1)
    log(f"--> TEST  pipeline={pipeline_type}  max_num_tokens={max_num_tokens}")
    try:
        res = comfy("/prompt", {"prompt": build_prompt(pipeline_type, max_num_tokens, seed),
                                "client_id": "find-max"}, timeout=60)
    except Exception as exc:
        log(f"    soumission impossible: {exc}")
        return "ERR", 0.0
    if res.get("node_errors"):
        log(f"    node_errors: {res['node_errors']}")
        return "ERR", 0.0
    pid = res["prompt_id"]

    start = time.time()
    fails = 0
    while time.time() - start < JOB_TIMEOUT:
        time.sleep(8)
        try:
            hist = comfy(f"/history/{pid}", timeout=30)
            fails = 0
        except Exception:
            fails += 1
            if fails >= 12:
                el = time.time() - start
                log(f"    ComfyUI ne repond plus apres {el:.0f}s (crash = OOM probable)")
                return "OOM", el
            continue
        entry = hist.get(pid)
        if not entry:
            continue
        elapsed = time.time() - start
        status = entry.get("status", {})
        sstr = status.get("status_str")
        if sstr == "success" or (status.get("completed") and sstr != "error"):
            log(f"    OK en {elapsed:.0f}s")
            return "OK", elapsed
        # erreur : OOM ou autre ?
        blob = json.dumps(status)
        try:
            blob += COMFY_LOG.read_text(encoding="utf-8", errors="replace")[-6000:]
        except Exception:
            pass
        if looks_like_oom(blob):
            log(f"    OOM apres {elapsed:.0f}s")
            return "OOM", elapsed
        log(f"    ERREUR (non-OOM) apres {elapsed:.0f}s")
        return "ERR", elapsed
    log("    TIMEOUT (job trop long)")
    return "ERR", JOB_TIMEOUT


def apply_config(pipeline_type: str, max_num_tokens: int) -> None:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    cfg["pipeline_type"] = pipeline_type
    cfg["max_num_tokens"] = max_num_tokens
    cfg["steps"] = 30          # qualite max ; n'affecte pas la VRAM
    cfg["texture_size"] = 4096
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    log(f"config.json mis a jour : pipeline={pipeline_type}, max_num_tokens={max_num_tokens}, steps=30")


def main() -> None:
    log("=== Recherche limite OOM : 1024_cascade ===")
    log("Rappel 1536_cascade : OK @ 49152 (1690s), OOM @ 65536 -> plafond 1536 = 49152.")
    if not TEST_SRC.exists():
        log(f"Image de test introuvable: {TEST_SRC}")
        return
    detour_test_image()

    base = "1024_cascade"
    best_tokens = 49152              # combinaison deja prouvee fiable
    results: list[str] = []
    for tok in TOKEN_LADDER:
        v, s = run(base, tok)
        results.append(f"{base} @ {tok} -> {v} ({s:.0f}s)")
        if v == "OK":
            best_tokens = tok
        else:
            log(f"Limite atteinte a {tok} tokens ({v}). Arret de la montee.")
            break

    log("")
    log("=== RESULTATS 1024_cascade ===")
    for r in results:
        log("  " + r)
    log("")
    log(f"=== 1024_cascade : max_num_tokens viable le plus haut = {best_tokens} ===")
    log("Termine.")


if __name__ == "__main__":
    main()
