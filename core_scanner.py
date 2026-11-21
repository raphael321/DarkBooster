import ctypes
import datetime
import json
import os
import shutil
import time

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", r"C:\Users\rapha\AppData\Local")
APPDATA = os.environ.get("APPDATA", r"C:\Users\rapha\AppData\Roaming")
USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\rapha")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "ssd_alert_threshold_gb": 25.0,
    "auto_clean_safe_on_low_disk": False,
    "pause_during_render": True,
    "check_interval_seconds": 60,
    "custom_channel_paths": [
        os.path.join(USERPROFILE, "shorts"),
        r"C:\tmp",
    ],
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg.update(data)
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def fast_dir_size(path: str, max_seconds: float = 0.8) -> tuple[int, int, bool]:
    """
    Fast non-blocking directory scanner that skips OneDrive Cloud-Only placeholders
    and symlinks. Returns (total_bytes, file_count, was_capped).
    """
    if not os.path.exists(path):
        return 0, 0, False
    try:
        if os.path.isfile(path):
            st = os.stat(path, follow_symlinks=False)
            return st.st_size, 1, False
    except Exception:
        return 0, 0, False

    total = 0
    files = 0
    steps = 0
    t0 = time.perf_counter()
    stack = [path]

    while stack:
        curr = stack.pop()
        try:
            with os.scandir(curr) as it:
                for entry in it:
                    steps += 1
                    if (steps & 255) == 0 and (time.perf_counter() - t0) > max_seconds:
                        return total, files, True
                    try:
                        st = entry.stat(follow_symlinks=False)
                        attrs = getattr(st, "st_file_attributes", 0)
                        # Skip OneDrive cloud-only files (0x400000 or 0x1000)
                        if attrs & (0x400000 | 0x1000):
                            continue
                        if entry.is_file(follow_symlinks=False):
                            total += st.st_size
                            files += 1
                        elif entry.is_dir(follow_symlinks=False) and not (attrs & 0x400):
                            stack.append(entry.path)
                    except Exception:
                        pass
        except Exception:
            pass
    return total, files, False


def format_size(size_bytes: int, capped: bool = False) -> str:
    plus = "+" if capped else ""
    mb = size_bytes / (1024 ** 2)
    if mb >= 1000:
        gb = size_bytes / (1024 ** 3) if size_bytes >= 1024 ** 3 else mb / 1000.0
        return f"{gb:.2f} GB{plus}"
    if size_bytes >= 1024 ** 2:
        return f"{mb:.1f} MB{plus}"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB{plus}"
    return f"{size_bytes} B"


def get_safe_categories() -> list[dict]:
    """
    Returns the definition of Tier-1 SAFE cleanup categories
    ('Arquivos que consigo apagar sem risco para projetos ou senhas').
    """
    temp_root = os.path.join(LOCALAPPDATA, "Temp")

    # Dynamically partition Temp into Claude Temp, Remotion/Render Bundles, and General Temp
    remotion_paths = []
    general_temp_paths = []
    claude_temp_path = os.path.join(temp_root, "claude")

    if os.path.exists(temp_root):
        try:
            for e in os.scandir(temp_root):
                nl = e.name.lower()
                if nl == "claude":
                    continue
                elif (
                    nl.startswith("remotion-")
                    or nl.startswith("puppeteer_")
                    or nl.startswith("playwright")
                    or nl.startswith("etilqs_")
                    or nl.startswith("ffmpeg")
                ):
                    remotion_paths.append(e.path)
                else:
                    general_temp_paths.append(e.path)
        except Exception:
            pass

    # Chrome all profiles cache paths
    chrome_user_data = os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data")
    chrome_caches = []
    if os.path.exists(chrome_user_data):
        try:
            for e in os.scandir(chrome_user_data):
                if e.is_dir() and (e.name == "Default" or e.name.startswith("Profile ")):
                    for sub in (
                        "Cache",
                        "Code Cache",
                        "GPUCache",
                        os.path.join("Service Worker", "CacheStorage"),
                        os.path.join("Service Worker", "ScriptCache"),
                    ):
                        p = os.path.join(e.path, sub)
                        if os.path.exists(p):
                            chrome_caches.append(p)
        except Exception:
            pass

    # Opera caches
    opera_caches = [
        p
        for p in [
            os.path.join(LOCALAPPDATA, "Opera Software", "Opera Stable", "Cache"),
            os.path.join(LOCALAPPDATA, "Opera Software", "Opera Stable", "System Cache"),
            os.path.join(APPDATA, "Opera Software", "Opera Stable", "Cache"),
            os.path.join(APPDATA, "Opera Software", "Opera Stable", "Code Cache"),
            os.path.join(APPDATA, "Opera Software", "Opera Stable", "GPUCache"),
            os.path.join(APPDATA, "Opera Software", "Opera Stable", "Service Worker", "CacheStorage"),
            os.path.join(LOCALAPPDATA, "Opera Software", "Opera GX Stable", "Cache"),
            os.path.join(APPDATA, "Opera Software", "Opera GX Stable", "Cache"),
            os.path.join(APPDATA, "Opera Software", "Opera GX Stable", "Code Cache"),
            os.path.join(APPDATA, "Opera Software", "Opera GX Stable", "GPUCache"),
        ]
        if os.path.exists(p)
    ]

    categories = [
        {
            "id": "onedrive_internal",
            "title": "OneDrive: Cache Interno ListSync & Logs",
            "desc": "Logs e banco temporário ListSync do OneDrive que incham ocultamente em AppData (NÃO apaga seus arquivos).",
            "paths": [
                os.path.join(LOCALAPPDATA, "Microsoft", "OneDrive", "ListSync"),
                os.path.join(LOCALAPPDATA, "Microsoft", "OneDrive", "logs"),
                os.path.join(LOCALAPPDATA, "Microsoft", "OneDrive", "setup", "logs"),
            ],
            "default_checked": True,
            "action_type": "delete_contents",
        },
        {
            "id": "temp_claude",
            "title": "Temp: Arquivos Temporários do Claude",
            "desc": "Arquivos temporários acumulados em AppData\\Local\\Temp\\claude.",
            "paths": [claude_temp_path],
            "default_checked": True,
            "action_type": "delete_contents",
        },
        {
            "id": "temp_remotion",
            "title": "Temp: Bundles de Renderização (Remotion / Puppeteer / SQLite)",
            "desc": "Bundles webpack do Remotion, perfis headless e arquivos etilqs_* deixados por renderizações anteriores.",
            "paths": remotion_paths,
            "open_dir": temp_root,
            "default_checked": True,
            "action_type": "delete_paths",
        },
        {
            "id": "temp_general",
            "title": "Temp: Arquivos Temporários Gerais do Windows",
            "desc": "Restante da pasta AppData\\Local\\Temp e C:\\Windows\\Temp (arquivos em uso são ignorados com segurança).",
            "paths": general_temp_paths + ([r"C:\Windows\Temp"] if os.path.exists(r"C:\Windows\Temp") else []),
            "open_dir": temp_root,
            "default_checked": True,
            "action_type": "delete_paths",
        },
        {
            "id": "gpu_shaders",
            "title": "GPU: Shader Cache (NVIDIA DXCache / GLCache / AMD / DirectX)",
            "desc": "Caches de shaders compilados da RTX 4050 e Radeon. Limpar devolve GBs e corrige engasgos de vídeo.",
            "paths": [
                os.path.join(LOCALAPPDATA, "NVIDIA", "DXCache"),
                os.path.join(LOCALAPPDATA, "NVIDIA", "GLCache"),
                os.path.join(LOCALAPPDATA, "NVIDIA Corporation", "NV_Cache"),
                os.path.join(LOCALAPPDATA, "AMD", "DxCache"),
                os.path.join(LOCALAPPDATA, "AMD", "GLCache"),
                os.path.join(LOCALAPPDATA, "D3DSCache"),
            ],
            "default_checked": True,
            "action_type": "delete_contents",
        },
        {
            "id": "recycle_bin",
            "title": "Sistema: Lixeira do Windows (C:\\$Recycle.Bin)",
            "desc": "Arquivos que você já apagou das pastas mas ainda estão ocupando espaço real no SSD.",
            "paths": [r"C:\$Recycle.Bin"],
            "default_checked": True,
            "action_type": "empty_recycle_bin",
        },
        {
            "id": "browser_chrome",
            "title": "Navegador: Cache de Mídia do Google Chrome (Mantém Logins)",
            "desc": "Limpa apenas vídeos/imagens em cache de disco do Chrome. NÃO desconecta contas nem apaga senhas.",
            "paths": chrome_caches,
            "open_dir": chrome_user_data,
            "default_checked": True,
            "action_type": "delete_contents",
        },
        {
            "id": "browser_opera",
            "title": "Navegador: Cache de Mídia do Opera (Mantém Logins)",
            "desc": "Limpa apenas cache de disco/GPU do Opera. NÃO desconecta suas contas nem apaga favoritos.",
            "paths": opera_caches,
            "open_dir": os.path.join(APPDATA, "Opera Software"),
            "default_checked": True,
            "action_type": "delete_contents",
        },
        {
            "id": "dark_apps_cache",
            "title": "Apps Dark & Editores: Caches, Updaters e CrashDumps",
            "desc": "Instaladores antigos do DarkPlanner, SquirrelTemp, CrashDumps, Adobe Media Cache e Discord Cache.",
            "paths": [
                os.path.join(LOCALAPPDATA, "darkplanner-updater"),
                os.path.join(LOCALAPPDATA, "SquirrelTemp"),
                os.path.join(LOCALAPPDATA, "CrashDumps"),
                os.path.join(APPDATA, "Adobe", "Common", "Media Cache Files"),
                os.path.join(APPDATA, "Adobe", "Common", "Media Cache"),
                os.path.join(APPDATA, "discord", "Cache"),
                os.path.join(APPDATA, "discord", "Code Cache"),
                os.path.join(APPDATA, "discord", "GPUCache"),
                os.path.join(APPDATA, "slobs-client", "Cache"),
                os.path.join(APPDATA, "slobs-client", "Code Cache"),
            ],
            "default_checked": True,
            "action_type": "delete_contents",
        },
        {
            "id": "dev_package_caches",
            "title": "Caches de Pacotes (NPM / PNPM / PIP / UV / WinGet)",
            "desc": "Instaladores baixados em cache (não desinstala bibliotecas dos seus projetos, apenas limpa o cache de download).",
            "paths": [
                os.path.join(LOCALAPPDATA, "npm-cache"),
                os.path.join(LOCALAPPDATA, "pnpm-cache"),
                os.path.join(LOCALAPPDATA, "pip", "Cache"),
                os.path.join(LOCALAPPDATA, "uv", "cache"),
                os.path.join(LOCALAPPDATA, "Microsoft", "WinGet", "Cache"),
            ],
            "default_checked": True,
            "action_type": "delete_contents",
        },
    ]
    return categories


def scan_safe_categories() -> list[dict]:
    """Calculates live sizes for each Tier-1 SAFE cleanup category."""
    cats = get_safe_categories()
    results = []
    for cat in cats:
        total_bytes = 0
        total_files = 0
        any_capped = False
        existing_paths = []
        for p in cat["paths"]:
            if os.path.exists(p):
                existing_paths.append(p)
                sz, fc, cap = fast_dir_size(p, max_seconds=0.6)
                total_bytes += sz
                total_files += fc
                any_capped = any_capped or cap

        cat_copy = dict(cat)
        cat_copy["size_bytes"] = total_bytes
        cat_copy["size_str"] = format_size(total_bytes, any_capped)
        cat_copy["file_count"] = total_files
        cat_copy["existing_paths"] = existing_paths
        results.append(cat_copy)
    return results


def scan_permission_items(custom_roots: list[str] | None = None) -> list[dict]:
    """
    Scans Tier-2 PERMISSION items ('Arquivos que pode apagar mas precisa da minha permissão'):
    - Every channel/project inside C:\\Users\\rapha\\shorts (and custom folders)
    - Build caches inside channels (node_modules, .venv, out, build*)
    - Subfolders inside C:\\tmp (e.g. C:\\tmp\\wz)
    - AI Models & Runtimes in .cache (huggingface, codex-runtimes)
    - Sandboxes / VMs (Claude-Data, ms-playwright, VirtualBox VMs)
    - Heavy files in Downloads / Videos
    """
    if custom_roots is None:
        custom_roots = load_config().get("custom_channel_paths", DEFAULT_CONFIG["custom_channel_paths"])

    items = []

    # 1. Scan Custom Channel / Project Roots (e.g. C:\Users\rapha\shorts and C:\tmp)
    for root in custom_roots:
        if not os.path.exists(root):
            continue
        root_name = os.path.basename(root.rstrip("\\/")) or root
        try:
            for entry in os.scandir(root):
                try:
                    sz, fc, cap = fast_dir_size(entry.path, max_seconds=0.8)
                    if sz < 25 * 1024 * 1024:  # Show items >= 25 MB
                        continue
                    mtime = datetime.datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime)
                    is_tmp = root.lower().startswith("c:\\tmp")
                    category = "Pasta Temporária Raiz (C:\\tmp)" if is_tmp else f"Canal / Projeto Dark ({root_name})"
                    risk_note = (
                        "Subpasta de trabalho em C:\\tmp. Verifique se o processamento já terminou antes de apagar."
                        if is_tmp
                        else "Pasta de canal/projeto Dark (contém episódios, b-rolls, áudios ou código). Revise antes de apagar!"
                    )
                    items.append(
                        {
                            "id": f"custom::{entry.path}",
                            "name": f"[{root_name}] {entry.name}",
                            "category": category,
                            "path": entry.path,
                            "size_bytes": sz,
                            "size_str": format_size(sz, cap),
                            "file_count": fc,
                            "modified_str": mtime.strftime("%d/%m/%Y %H:%M"),
                            "risk_note": risk_note,
                            "can_drilldown": entry.is_dir(follow_symlinks=False),
                        }
                    )
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Scan AI Models & Runtimes (.cache, ms-playwright, Claude-Data, VirtualBox VMs)
    special_candidates = [
        (
            os.path.join(USERPROFILE, ".cache", "huggingface"),
            "Modelos de IA (HuggingFace Cache)",
            "Pesos de modelos de IA baixados (Whisper/TTS/Transformers). Se apagar, libera ~7 GB e só baixa de novo se usar o modelo.",
        ),
        (
            os.path.join(USERPROFILE, ".cache", "codex-runtimes"),
            "Runtimes & Ambientes (.cache\\codex-runtimes)",
            "Runtimes em cache. Pode ser recriado quando necessário.",
        ),
        (
            os.path.join(LOCALAPPDATA, "Claude-Data"),
            "Sandbox / VM Local (Claude-Data)",
            "Dados locais/imagem do pacote Claude Desktop (12.6 GB). Apagar redefine o ambiente local do app.",
        ),
        (
            os.path.join(LOCALAPPDATA, "ms-playwright"),
            "Browsers de Automação (ms-playwright)",
            "Navegadores Chromium/Firefox do Playwright. Se apagar, rode 'npx playwright install' quando precisar.",
        ),
        (
            os.path.join(LOCALAPPDATA, "ms-playwright-mcp"),
            "Browsers de Automação (ms-playwright-mcp)",
            "Navegadores headless do Playwright MCP.",
        ),
        (
            os.path.join(USERPROFILE, "VirtualBox VMs"),
            "Máquinas Virtuais (VirtualBox VMs)",
            "Discos virtuais do VirtualBox. Apague apenas se não usar mais essas VMs.",
        ),
    ]

    for sp_path, sp_cat, sp_note in special_candidates:
        if os.path.exists(sp_path):
            try:
                sz, fc, cap = fast_dir_size(sp_path, max_seconds=0.8)
                if sz >= 30 * 1024 * 1024:
                    mtime = datetime.datetime.fromtimestamp(os.stat(sp_path).st_mtime)
                    items.append(
                        {
                            "id": f"special::{sp_path}",
                            "name": os.path.basename(sp_path),
                            "category": sp_cat,
                            "path": sp_path,
                            "size_bytes": sz,
                            "size_str": format_size(sz, cap),
                            "file_count": fc,
                            "modified_str": mtime.strftime("%d/%m/%Y %H:%M"),
                            "risk_note": sp_note,
                            "can_drilldown": os.path.isdir(sp_path),
                        }
                    )
            except Exception:
                pass

    # 3. Scan Large Files (>50 MB) in Downloads and Videos
    for media_dir_name in ("Downloads", "Videos"):
        m_dir = os.path.join(USERPROFILE, media_dir_name)
        if not os.path.exists(m_dir):
            continue
        try:
            for entry in os.scandir(m_dir):
                try:
                    sz, fc, cap = fast_dir_size(entry.path, max_seconds=0.4)
                    if sz >= 50 * 1024 * 1024:
                        mtime = datetime.datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime)
                        items.append(
                            {
                                "id": f"media::{entry.path}",
                                "name": f"[{media_dir_name}] {entry.name}",
                                "category": f"Arquivo/Pasta Grande em {media_dir_name}",
                                "path": entry.path,
                                "size_bytes": sz,
                                "size_str": format_size(sz, cap),
                                "file_count": fc,
                                "modified_str": mtime.strftime("%d/%m/%Y %H:%M"),
                                "risk_note": f"Item grande na pasta {media_dir_name}. Confirme se já foi publicado/usado.",
                                "can_drilldown": entry.is_dir(follow_symlinks=False),
                            }
                        )
                except Exception:
                    pass
        except Exception:
            pass

    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    return items


def scan_subfolders_of(parent_path: str, min_bytes: int = 0) -> list[dict]:
    """
    Drills down into any folder (e.g. channel, episode, cache, or shader dir)
    so the user can inspect and delete individual files/subfolders.
    """
    rows = []
    if not os.path.exists(parent_path):
        return rows
    if os.path.isfile(parent_path):
        try:
            st = os.stat(parent_path, follow_symlinks=False)
            mtime = datetime.datetime.fromtimestamp(st.st_mtime)
            rows.append(
                {
                    "name": os.path.basename(parent_path),
                    "path": parent_path,
                    "kind": "Arquivo",
                    "is_recreatable": False,
                    "size_bytes": st.st_size,
                    "size_str": format_size(st.st_size, False),
                    "file_count": 1,
                    "modified_str": mtime.strftime("%d/%m/%Y %H:%M"),
                    "is_dir": False,
                }
            )
        except Exception:
            pass
        return rows

    try:
        for entry in os.scandir(parent_path):
            try:
                sz, fc, cap = fast_dir_size(entry.path, max_seconds=0.35)
                if sz < min_bytes or sz == 0:
                    continue
                mtime = datetime.datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime)
                is_recreatable = entry.name.lower() in (
                    "node_modules",
                    ".venv",
                    ".remotion",
                    ".next",
                    ".cache",
                    "__pycache__",
                )
                kind = (
                    "Dependência Recriável (npm/venv)"
                    if is_recreatable
                    else ("Pasta" if entry.is_dir(follow_symlinks=False) else "Arquivo")
                )
                rows.append(
                    {
                        "name": entry.name,
                        "path": entry.path,
                        "kind": kind,
                        "is_recreatable": is_recreatable,
                        "size_bytes": sz,
                        "size_str": format_size(sz, cap),
                        "file_count": fc,
                        "modified_str": mtime.strftime("%d/%m/%Y %H:%M"),
                        "is_dir": entry.is_dir(follow_symlinks=False),
                    }
                )
            except Exception:
                pass
    except Exception:
        pass
    rows.sort(key=lambda x: x["size_bytes"], reverse=True)
    return rows[:120]


def inspect_multiple_paths(paths: list[str]) -> list[dict]:
    """
    Lists the files and subfolders inside one or more paths (e.g. for Safe Categories,
    GPU Shader Caches, or System Root files C:\\pagefile.sys / C:\\hiberfil.sys).
    """
    rows = []
    if len(paths) == 1 and os.path.isdir(paths[0]):
        return scan_subfolders_of(paths[0], min_bytes=0)

    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            st = os.stat(p, follow_symlinks=False)
            mtime = datetime.datetime.fromtimestamp(st.st_mtime)
            is_d = os.path.isdir(p)
            if is_d and len(paths) <= 6:
                # Expand children of each directory so user sees the actual files inside
                sub_rows = scan_subfolders_of(p, min_bytes=0)
                if sub_rows:
                    parent_tag = os.path.basename(p.rstrip("\\/"))
                    for sr in sub_rows[:40]:
                        sr["name"] = f"[{parent_tag}] {sr['name']}"
                        rows.append(sr)
                    continue
            sz, fc, cap = fast_dir_size(p, max_seconds=0.35) if is_d else (st.st_size, 1, False)
            if sz == 0:
                continue
            rows.append(
                {
                    "name": os.path.basename(p.rstrip("\\/")) or p,
                    "path": p,
                    "kind": "Pasta" if is_d else "Arquivo de Sistema / Cache",
                    "is_recreatable": False,
                    "size_bytes": sz,
                    "size_str": format_size(sz, cap),
                    "file_count": fc,
                    "modified_str": mtime.strftime("%d/%m/%Y %H:%M"),
                    "is_dir": is_d,
                }
            )
        except Exception:
            pass

    rows.sort(key=lambda x: x["size_bytes"], reverse=True)
    return rows[:120]


def empty_windows_recycle_bin() -> tuple[bool, str]:
    """Empties the Windows Recycle Bin silently using shell32.SHEmptyRecycleBinW."""
    SHERB_NOCONFIRMATION = 0x00000001
    SHERB_NOPROGRESSUI = 0x00000002
    SHERB_NOSOUND = 0x00000004
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        )
        return True, "Lixeira esvaziada com sucesso."
    except Exception as e:
        return False, str(e)


def _delete_tree_best_effort(target_path: str, delete_root: bool = False) -> tuple[int, int]:
    """
    Deletes files inside target_path while safely skipping any file currently locked by Windows.
    Returns (freed_bytes, deleted_files_count).
    """
    if not os.path.exists(target_path):
        return 0, 0

    freed = 0
    deleted = 0

    if os.path.isfile(target_path) or os.path.islink(target_path):
        try:
            sz = os.path.getsize(target_path)
            os.remove(target_path)
            return sz, 1
        except Exception:
            return 0, 0

    for root, dirs, files in os.walk(target_path, topdown=False):
        for f in files:
            fp = os.path.join(root, f)
            try:
                sz = os.path.getsize(fp)
                os.chmod(fp, 0o777)
                os.remove(fp)
                freed += sz
                deleted += 1
            except Exception:
                pass
        for d in dirs:
            dp = os.path.join(root, d)
            try:
                os.rmdir(dp)
            except Exception:
                pass

    if delete_root:
        try:
            os.rmdir(target_path)
        except Exception:
            pass

    return freed, deleted


def clean_safe_category(cat: dict) -> tuple[int, int]:
    """Executes cleanup for a single Tier-1 SAFE category. Returns (freed_bytes, deleted_files)."""
    action = cat.get("action_type", "delete_contents")
    if action == "empty_recycle_bin":
        sz_before = cat.get("size_bytes", 0)
        empty_windows_recycle_bin()
        return sz_before, cat.get("file_count", 1)

    total_freed = 0
    total_deleted = 0
    delete_root = action == "delete_paths"

    for p in cat.get("paths", []):
        if os.path.exists(p):
            fr, dl = _delete_tree_best_effort(p, delete_root=delete_root)
            total_freed += fr
            total_deleted += dl

    return total_freed, total_deleted


def delete_permission_item(target_path: str) -> tuple[int, int]:
    """Deletes a user-authorized Tier-2 item and returns (freed_bytes, deleted_files)."""
    return _delete_tree_best_effort(target_path, delete_root=True)
