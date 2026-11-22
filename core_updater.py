import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(APP_DIR, "version.json")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

REPO_OWNER = "raphael321"
REPO_NAME = "DarkBooster"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
RAW_VERSION_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/version.json"
ZIP_DOWNLOAD_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"
CREATE_NO_WINDOW = 0x08000000


def get_local_version() -> dict:
    default_v = {"version": "2.1.0", "released_at": "2026-11-22", "notes": ""}
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_v.update(data)
        except Exception:
            pass
    return default_v


def _parse_ver(v_str: str) -> tuple[int, ...]:
    parts = []
    for p in str(v_str).strip().lstrip("vV").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_for_updates() -> dict:
    """
    Lightweight 1KB check against raw.githubusercontent.com/raphael321/DarkBooster/main/version.json.
    """
    local = get_local_version()
    local_ver = local.get("version", "2.1.0")
    result = {
        "ok": True,
        "update_available": False,
        "local_version": local_ver,
        "remote_version": local_ver,
        "notes": local.get("notes", ""),
        "repo_url": REPO_URL,
    }
    try:
        req = urllib.request.Request(
            RAW_VERSION_URL,
            headers={"User-Agent": "DarkBooster-Updater/2.1", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            raw = resp.read().decode("utf-8")
            remote = json.loads(raw)
            remote_ver = remote.get("version", local_ver)
            result["remote_version"] = remote_ver
            result["notes"] = remote.get("notes", result["notes"])
            result["update_available"] = _parse_ver(remote_ver) > _parse_ver(local_ver)
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
    return result


def download_and_apply_update() -> tuple[bool, str]:
    """
    Updates DarkBooster from GitHub (main branch) while preserving the user's config.json.
    Works both for Git clones (via git pull) and ZIP installations (via direct ZIP download).
    """
    # 1. Backup user's config.json in memory so personal settings/folders are NEVER lost
    config_backup = None
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "rb") as f:
                config_backup = f.read()
        except Exception:
            pass

    updated_via_git = False
    if os.path.isdir(os.path.join(APP_DIR, ".git")):
        try:
            res = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=APP_DIR,
                capture_output=True,
                text=True,
                timeout=25,
                creationflags=CREATE_NO_WINDOW,
            )
            if res.returncode == 0:
                updated_via_git = True
        except Exception:
            pass

    if not updated_via_git:
        # Fallback: Download main.zip directly from GitHub (works even without Git installed!)
        tmp_dir = tempfile.mkdtemp(prefix="darkbooster_upd_")
        zip_path = os.path.join(tmp_dir, "main.zip")
        try:
            req = urllib.request.Request(
                ZIP_DOWNLOAD_URL,
                headers={"User-Agent": "DarkBooster-Updater/2.1"},
            )
            with urllib.request.urlopen(req, timeout=25) as resp, open(zip_path, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)

            extracted_root = None
            for entry in os.scandir(tmp_dir):
                if entry.is_dir() and entry.name.startswith(REPO_NAME):
                    extracted_root = entry.path
                    break

            if not extracted_root:
                return False, "Falha ao extrair o pacote de atualização."

            # Copy updated runtime files & compiled dist/ folder
            items_to_copy = [
                "app.py",
                "core_scanner.py",
                "core_optimizer.py",
                "core_updater.py",
                "version.json",
                "darkbooster.ico",
                "dist",
            ]
            for rel in items_to_copy:
                src = os.path.join(extracted_root, rel)
                dst = os.path.join(APP_DIR, rel)
                if not os.path.exists(src):
                    continue
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
        except Exception as e:
            return False, f"Erro ao baixar atualização do GitHub: {e}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # Restore user config.json
    if config_backup is not None:
        try:
            with open(CONFIG_FILE, "wb") as f:
                f.write(config_backup)
        except Exception:
            pass

    new_ver = get_local_version().get("version", "2.1.0")
    return True, f"DarkBooster atualizado para a versão v{new_ver}! Reiniciando aplicativo..."
