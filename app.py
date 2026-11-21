import ctypes
from ctypes import wintypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import winreg

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PIL import Image, ImageDraw
import psutil
import pystray

import core_optimizer as opt
import core_scanner as scanner

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(APP_DIR, "dist")
ICO_PATH = os.path.join(APP_DIR, "darkbooster.ico")
if not os.path.exists(ICO_PATH):
    ICO_PATH = os.path.join(APP_DIR, "darkstudio.ico")
PORT = 8765
HOST = "127.0.0.1"
URL = f"http://{HOST}:{PORT}"
NATIVE_WIN_TITLE = "DarkBooster — Native Desktop"
APP_USER_MODEL_ID = "Raphael.DarkBooster.DesktopApp.2.0"

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
except Exception:
    pass

PYTHONW_EXE = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.exists(PYTHONW_EXE):
    PYTHONW_EXE = sys.executable

_open_window_lock = threading.Lock()
_last_window_launch_time = 0.0


def create_tray_icon_image(alert: bool = False) -> Image.Image:
    """Generates a crisp 64x64 ember/dark icon in memory for the System Tray."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bg = (218, 54, 51, 255) if alert else (255, 95, 0, 255)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(10, 9, 8, 255), outline=bg, width=4)
    draw.polygon([(35, 11), (19, 34), (31, 34), (25, 53), (45, 28), (33, 28)], fill=bg)
    return img


def get_startup_registry_status() -> bool:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        val, _ = winreg.QueryValueEx(key, "DarkStudioOptimizer")
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False


def set_startup_registry(enable: bool) -> bool:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        if enable:
            app_script = os.path.join(APP_DIR, "app.py")
            cmd = f'"{PYTHONW_EXE}" "{app_script}" --tray'
            winreg.SetValueEx(key, "DarkStudioOptimizer", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "DarkStudioOptimizer")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def is_port_in_use(port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, port)) == 0


def focus_existing_app_window() -> bool:
    """
    Searches ONLY for our own Python native DarkBooster desktop window via Win32 EnumWindows.
    Never touches or closes any browser or external window.
    """
    user32 = ctypes.windll.user32
    found_hwnds = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if title == NATIVE_WIN_TITLE:
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    try:
                        pname = psutil.Process(pid.value).name().lower()
                        if pname in ("python.exe", "pythonw.exe"):
                            found_hwnds.append(hwnd)
                    except Exception:
                        pass
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if found_hwnds:
            hwnd = found_hwnds[0]
            SW_RESTORE = 9
            SW_SHOW = 5
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def open_native_app_window():
    """
    Brings the existing native window to the front if already open;
    otherwise spawns our native pywebview Desktop Window child process.
    """
    global _last_window_launch_time
    with _open_window_lock:
        if focus_existing_app_window():
            return

        now = time.time()
        if (now - _last_window_launch_time) < 2.5:
            return
        _last_window_launch_time = now

        app_script = os.path.join(APP_DIR, "app.py")
        subprocess.Popen(
            [PYTHONW_EXE, app_script, "--native-window"],
            cwd=APP_DIR,
        )


def apply_taskbar_icon_to_hwnd(hwnd: int = 0) -> None:
    """Applies darkbooster.ico to all top-level Win32 HWNDs of this process so it appears in the Windows Taskbar and Alt+Tab."""
    if not os.path.exists(ICO_PATH):
        return
    try:
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = wintypes.LPARAM

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        GCLP_HICON = -14
        GCLP_HICONSM = -34

        hicon_big = user32.LoadImageW(None, ICO_PATH, IMAGE_ICON, 256, 256, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = user32.LoadImageW(None, ICO_PATH, IMAGE_ICON, 64, 64, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = user32.LoadImageW(None, ICO_PATH, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)

        hicon_small = user32.LoadImageW(None, ICO_PATH, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if not hicon_small:
            hicon_small = hicon_big

        target_hwnds = []
        if hwnd:
            target_hwnds.append(hwnd)

        my_pid = os.getpid()
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def enum_cb(h, lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == my_pid:
                target_hwnds.append(h)
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        GWL_STYLE = -16
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000

        dwmapi = getattr(ctypes.windll, "dwmapi", None)

        for h in set(target_hwnds):
            if user32.IsWindowVisible(h):
                cur_style = user32.GetWindowLongW(h, GWL_STYLE)
                user32.SetWindowLongW(h, GWL_STYLE, cur_style | WS_SYSMENU | WS_MINIMIZEBOX)
                if dwmapi:
                    try:
                        dark_mode = ctypes.c_int(1)
                        dwmapi.DwmSetWindowAttribute(h, 20, ctypes.byref(dark_mode), 4)
                        caption_col = ctypes.c_int(0x0008090A)
                        dwmapi.DwmSetWindowAttribute(h, 35, ctypes.byref(caption_col), 4)
                    except Exception:
                        pass
            if hicon_big:
                user32.SendMessageW(h, WM_SETICON, ICON_BIG, hicon_big)
                if hasattr(user32, "SetClassLongPtrW"):
                    user32.SetClassLongPtrW(h, GCLP_HICON, hicon_big)
            if hicon_small:
                user32.SendMessageW(h, WM_SETICON, ICON_SMALL, hicon_small)
                if hasattr(user32, "SetClassLongPtrW"):
                    user32.SetClassLongPtrW(h, GCLP_HICONSM, hicon_small)
    except Exception:
        pass


def run_native_webview_window():
    """
    Runs the 100% native Windows Desktop Application Window via pywebview (WinForms + WebView2).
    """
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

    import webview

    class NativeDesktopApi:
        def __init__(self):
            self._win = None
            self._maximized = False

        def set_window(self, win):
            self._win = win

        def minimize_window(self):
            if self._win:
                self._win.minimize()

        def toggle_maximize(self):
            if not self._win:
                return
            if self._maximized:
                self._win.restore()
                self._maximized = False
            else:
                self._win.maximize()
                self._maximized = True

        def close_to_tray(self):
            if self._win:
                self._win.destroy()

        def pick_folder(self):
            if not self._win:
                return None
            res = self._win.create_file_dialog(webview.FOLDER_DIALOG)
            if res and len(res) > 0:
                return res[0]
            return None

        def start_drag(self):
            if not self._win:
                return
            try:
                hwnd = int(self._win.native.Handle.ToInt64())
                user32 = ctypes.windll.user32
                user32.ReleaseCapture()
                user32.PostMessageW(hwnd, 0x00A1, 2, 0)
            except Exception:
                pass

        def start_resize(self, hit_test: int):
            if not self._win:
                return
            try:
                hwnd = int(self._win.native.Handle.ToInt64())
                user32 = ctypes.windll.user32
                user32.ReleaseCapture()
                user32.PostMessageW(hwnd, 0x00A1, int(hit_test), 0)
            except Exception:
                pass

    api = NativeDesktopApi()
    win = webview.create_window(
        NATIVE_WIN_TITLE,
        url=URL,
        js_api=api,
        width=1360,
        height=850,
        min_size=(1020, 680),
        background_color="#0a0908",
        frameless=True,
        easy_drag=False,
        resizable=True,
    )
    api.set_window(win)

    def on_shown():
        try:
            if os.path.exists(ICO_PATH) and hasattr(win, "native") and win.native is not None:
                import System.Drawing  # type: ignore
                win.native.Icon = System.Drawing.Icon(ICO_PATH)
                win.native.ShowIcon = True
                hwnd = int(win.native.Handle.ToInt64())
                apply_taskbar_icon_to_hwnd(hwnd)
        except Exception:
            pass
        time.sleep(0.15)
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, NATIVE_WIN_TITLE)
        if hwnd:
            apply_taskbar_icon_to_hwnd(hwnd)
        focus_existing_app_window()

    webview.start(on_shown, gui="edgechromium", icon=ICO_PATH if os.path.exists(ICO_PATH) else None)
    os._exit(0)


class DarkStudioAPIHandler(SimpleHTTPRequestHandler):
    """Serves the compiled UI from dist/ and handles /api/* calls."""

    def __init__(self, *args, controller=None, **kwargs):
        self.controller = controller
        super().__init__(*args, directory=DIST_DIR, **kwargs)

    def log_message(self, format, *args):
        pass

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/telemetry":
            du = psutil.disk_usage("C:\\")
            vm = psutil.virtual_memory()
            gpu = opt.get_gpu_telemetry()
            sys_files = opt.get_system_root_files_info()
            rendering, render_apps = opt.is_rendering_active()
            cfg = scanner.load_config()
            my_rss = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            vram_pct = (gpu["vram_used_mb"] / gpu["vram_total_mb"] * 100.0) if gpu.get("vram_total_mb") else 0.0

            self._send_json(
                {
                    "ssd": {
                        "total_gb": round(du.total / (1024 ** 3), 2),
                        "used_gb": round(du.used / (1024 ** 3), 2),
                        "free_gb": round(du.free / (1024 ** 3), 2),
                        "percent_used": round(du.percent, 1),
                        "threshold_gb": float(cfg.get("ssd_alert_threshold_gb", 25.0)),
                    },
                    "ram": {
                        "total_gb": round(vm.total / (1024 ** 3), 1),
                        "used_gb": round((vm.total - vm.available) / (1024 ** 3), 2),
                        "avail_gb": round(vm.available / (1024 ** 3), 2),
                        "percent_used": round(vm.percent, 1),
                        "app_rss_mb": round(my_rss, 2),
                    },
                    "gpu": {
                        **gpu,
                        "vram_percent": round(vram_pct, 1),
                    },
                    "sys_files": sys_files,
                    "render": {
                        "active": rendering,
                        "apps": render_apps,
                    },
                    "is_admin": opt.is_user_admin(),
                    "config": {
                        "ssd_alert_threshold_gb": float(cfg.get("ssd_alert_threshold_gb", 25.0)),
                        "auto_clean_safe_on_low_disk": bool(cfg.get("auto_clean_safe_on_low_disk", False)),
                        "pause_during_render": bool(cfg.get("pause_during_render", True)),
                        "startup_enabled": get_startup_registry_status(),
                    },
                }
            )
            return

        if path == "/api/safe-categories":
            cats = scanner.scan_safe_categories()
            self._send_json({"categories": cats})
            return

        if path == "/api/permission-items":
            cfg = scanner.load_config()
            items = scanner.scan_permission_items(cfg.get("custom_channel_paths"))
            self._send_json({"items": items})
            return

        if path == "/api/ram-processes":
            procs = opt.get_top_ram_processes(limit=18)
            self._send_json({"processes": procs})
            return

        if path == "/api/duplicates":
            cfg = scanner.load_config()
            dups = scanner.scan_duplicate_files(cfg.get("custom_channel_paths"), min_size_mb=10)
            self._send_json({"duplicates": dups})
            return

        if path == "/api/pc-tools":
            self._send_json(
                {
                    "startup_apps": opt.get_startup_apps(),
                    "debloat_tweaks": opt.get_debloat_tweaks(),
                    "battery_thermal": opt.get_battery_and_thermal_status(),
                }
            )
            return

        if path == "/api/dns-benchmark":
            self._send_json({"providers": opt.benchmark_dns_servers()})
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/clean-safe":
            ids = set(body.get("ids", []))
            cats = scanner.scan_safe_categories()
            freed_total = 0
            deleted_total = 0
            for c in cats:
                if c["id"] in ids:
                    fr, dl = scanner.clean_safe_category(c)
                    freed_total += fr
                    deleted_total += dl
            self._send_json(
                {
                    "ok": True,
                    "freed_bytes": freed_total,
                    "freed_str": scanner.format_size(freed_total),
                    "deleted_files": deleted_total,
                }
            )
            return

        if path == "/api/open-path":
            target = body.get("path", "")
            if target and os.path.exists(target):
                try:
                    if os.path.isdir(target):
                        os.startfile(target)
                    else:
                        subprocess.Popen(["explorer", "/select,", target])
                except Exception:
                    pass
            self._send_json({"ok": True})
            return

        if path == "/api/drilldown":
            folder = body.get("path", "")
            rows = scanner.scan_subfolders_of(folder) if os.path.exists(folder) else []
            self._send_json({"rows": rows})
            return

        if path == "/api/inspect-paths":
            paths = body.get("paths", [])
            rows = scanner.inspect_multiple_paths(paths)
            self._send_json({"rows": rows})
            return

        if path == "/api/inspect-process":
            pids = body.get("pids", [])
            details = opt.inspect_process_details(pids)
            self._send_json({"details": details})
            return

        if path == "/api/system-tool":
            tool_id = body.get("tool", "")
            ok, msg = opt.open_windows_system_tool(tool_id)
            self._send_json({"ok": ok, "message": msg})
            return

        if path == "/api/pc-tools-action":
            kind = body.get("kind", "")
            if kind == "gamer_mode":
                enable = bool(body.get("enable", True))
                res = opt.activate_gamer_mode(enable)
                self._send_json({"ok": True, "title": res["title"], "message": res["message"]})
                return
            if kind == "toggle_startup":
                ok, msg = opt.toggle_startup_app(
                    body.get("name", ""),
                    bool(body.get("enable", True)),
                    body.get("source", "HKCU"),
                )
                self._send_json({"ok": ok, "title": "🚀 Inicialização do Windows", "message": msg})
                return
            if kind == "apply_dns":
                ok, msg = opt.apply_network_dns(body.get("provider_id", "cloudflare"))
                self._send_json({"ok": ok, "title": "🌐 Otimizador de Rede & DNS", "message": msg})
                return
            if kind == "toggle_debloat":
                ok, msg = opt.apply_debloat_tweak(
                    body.get("tweak_id", ""),
                    bool(body.get("optimize", True)),
                )
                self._send_json({"ok": ok, "title": "🧹 Debloater & Desempenho Windows 11", "message": msg})
                return
            if kind == "set_thermal_mode":
                ok, msg = opt.set_power_thermal_mode(body.get("mode_id", "balanced"))
                self._send_json({"ok": ok, "title": "🔋 Controle Térmico & Energia", "message": msg})
                return
            if kind == "set_fan_mode":
                ok, msg = opt.set_nitrosense_fan_mode(
                    body.get("fan_mode", "auto"),
                    int(body.get("custom_speed", 75)),
                )
                self._send_json({"ok": ok, "title": "🌪️ Ventoinhas Acer NitroSense", "message": msg})
                return
            self._send_json({"ok": False, "title": "Aviso", "message": "Ação desconhecida."})
            return

        if path == "/api/elevate-admin":
            exe_path = os.path.join(APP_DIR, "DarkBooster.exe")
            if not os.path.exists(exe_path):
                exe_path = os.path.join(APP_DIR, "DarkStudio_Optimizer.exe")
            app_script = os.path.join(APP_DIR, "app.py")
            if os.path.exists(exe_path):
                opt.run_admin_command(exe_path, "")
            else:
                opt.run_admin_command(PYTHONW_EXE, f'"{app_script}"')
            self._send_json({"ok": True})
            if self.controller:
                threading.Timer(0.5, lambda: self.controller._tray_quit()).start()
            return

        if path == "/api/add-custom-folder":
            folder = body.get("folder")
            if not folder:
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    r = tk.Tk()
                    r.withdraw()
                    r.attributes("-topmost", True)
                    folder = filedialog.askdirectory(title="Selecione uma Pasta de Canais Dark / Projetos")
                    r.destroy()
                except Exception:
                    folder = None
            if folder and os.path.exists(folder):
                norm = os.path.normpath(folder)
                cfg = scanner.load_config()
                custom = cfg.get("custom_channel_paths", [])
                if norm not in custom:
                    custom.append(norm)
                    cfg["custom_channel_paths"] = custom
                    scanner.save_config(cfg)
                self._send_json({"added": True, "folder": norm})
            else:
                self._send_json({"added": False})
            return

        if path == "/api/delete-permission":
            paths = body.get("paths", [])
            freed_total = 0
            deleted_total = 0
            for p in paths:
                if p and os.path.exists(p):
                    fr, dl = scanner.delete_permission_item(p)
                    freed_total += fr
                    deleted_total += dl
            opt.trim_self_memory()
            self._send_json(
                {
                    "ok": True,
                    "freed_bytes": freed_total,
                    "freed_str": scanner.format_size(freed_total),
                    "deleted_files": deleted_total,
                }
            )
            return

        if path == "/api/hardware-action":
            action = body.get("action", "")
            if action == "ram_boost":
                res = opt.optimize_system_ram()
                self._send_json(
                    {
                        "title": "🧠 Boost de RAM Concluído",
                        "message": f"Otimizados {res['trimmed_processes']} processos (~{res['freed_mb']} MB liberados | {res['available_gb']} GB disponíveis agora).",
                    }
                )
                return

            if action == "render_priority_boost":
                res = opt.apply_render_priority_boost(enable=True)
                if res["boosted_count"] > 0:
                    msg = f"Prioridade ALTA ativada em {res['boosted_count']} processo(s) ({', '.join(res['boosted_apps'])}) e {res['throttled_count']} apps de fundo reduzidos."
                else:
                    msg = "Modo Auto-Prioridade ativo! Assim que o FFmpeg/Remotion iniciar um render, ele receberá Prioridade Alta automaticamente."
                self._send_json(
                    {
                        "title": "⚡ Render Accelerator (Prioridade de CPU)",
                        "message": msg,
                    }
                )
                return

            if action == "kill_zombies":
                killed, freed_mb = opt.kill_orphan_render_workers()
                self._send_json(
                    {
                        "title": "🧹 Caça-Zumbis Concluído",
                        "message": f"Encerrados {killed} workers headless/render órfãos (~{freed_mb} MB liberados).",
                    }
                )
                return

            if action == "turbo_prerender":
                killed, k_mb = opt.kill_orphan_render_workers()
                cats = scanner.scan_safe_categories()
                freed_disk = 0
                for c in cats:
                    if c["id"] in ("temp_remotion", "temp_claude"):
                        fr, _ = scanner.clean_safe_category(c)
                        freed_disk += fr
                ram_res = opt.optimize_system_ram()
                self._send_json(
                    {
                        "title": "🎬 Modo Turbo Pré-Render Ativado!",
                        "message": f"RAM Livre: {ram_res['available_gb']} GB (+{ram_res['freed_mb'] + k_mb:.0f} MB) | {killed} zumbis fechados | {scanner.format_size(freed_disk)} de Temp Remotion limpos.",
                    }
                )
                return

            if action == "clean_gpu_shaders":
                cats = scanner.scan_safe_categories()
                freed = 0
                files = 0
                for c in cats:
                    if c["id"] == "gpu_shaders":
                        freed, files = scanner.clean_safe_category(c)
                        break
                self._send_json(
                    {
                        "title": "🎮 Shader Cache da GPU Limpo",
                        "message": f"Recuperados {scanner.format_size(freed)} ({files} arquivos de shader removidos da RTX 4050 / Radeon).",
                    }
                )
                return

            if action == "disable_hibernation":
                opt.disable_hibernation_admin()
                self._send_json(
                    {
                        "title": "❄️ Desativando Hibernação (hiberfil.sys)",
                        "message": "Confirme a janela de Administrador do Windows para liberar ~12,52 GB na hora!",
                    }
                )
                return

            if action == "shrink_pagefile":
                opt.shrink_pagefile_admin(4096, 8192)
                self._send_json(
                    {
                        "title": "📉 Reduzindo pagefile.sys (31.3 GB -> 4-8 GB)",
                        "message": "Confirme a janela de Administrador do Windows. Ao reiniciar o PC, ~25 GB serão devolvidos ao SSD!",
                    }
                )
                return

            if action == "free_onedrive":
                od_path = os.path.join(scanner.USERPROFILE, "OneDrive")
                ok, msg = opt.free_onedrive_local_cache(od_path)
                self._send_json({"title": "☁️ OneDrive Local Cache", "message": msg})
                return

            if action == "ssd_trim":
                opt.run_ssd_trim_admin()
                self._send_json(
                    {
                        "title": "⚡ TRIM do SSD NVMe Iniciado",
                        "message": "Otimizando blocos de gravação do SSD NVMe C:.",
                    }
                )
                return

            self._send_json({"title": "Aviso", "message": "Ação desconhecida."})
            return

        if path == "/api/kill-process":
            pids = body.get("pids", [])
            name = body.get("name", "Processo")
            killed, freed_mb = opt.kill_process_group(pids)
            self._send_json(
                {
                    "ok": True,
                    "message": f"{name}: {killed} processo(s) encerrado(s) (~{freed_mb} MB de RAM liberados).",
                }
            )
            return

        if path == "/api/save-config":
            cfg = scanner.load_config()
            cfg["ssd_alert_threshold_gb"] = float(body.get("ssd_alert_threshold_gb", 25.0))
            cfg["pause_during_render"] = bool(body.get("pause_during_render", True))
            cfg["auto_clean_safe_on_low_disk"] = bool(body.get("auto_clean_safe_on_low_disk", False))
            scanner.save_config(cfg)
            if self.controller:
                self.controller.config = cfg
            set_startup_registry(bool(body.get("startup_enabled", False)))
            self._send_json(
                {
                    "ok": True,
                    "message": "Preferências do Monitor em 2º Plano salvas com sucesso!",
                }
            )
            return

        if path == "/api/minimize-to-tray":
            opt.trim_self_memory()
            if self.controller:
                self.controller.notify_tray(
                    "🛡️ DarkStudio em 2º Plano (<3 MB RAM)",
                    "Janela nativa fechada para liberar 100% de RAM/GPU durante seus renders. Clique no ícone perto do relógio quando precisar!",
                )
            self._send_json({"ok": True})
            return

        self._send_json({"error": "Not found"}, status=404)


class DarkStudioController:
    def __init__(self, start_in_tray: bool = False):
        self.config = scanner.load_config()
        self.running = True
        self.last_alert_time = 0.0
        self.tray_icon: pystray.Icon | None = None

        self._start_http_server()
        threading.Thread(target=self._background_monitor_loop, daemon=True).start()
        self._start_tray_icon()

        if not start_in_tray:
            open_native_app_window()

        opt.trim_self_memory()
        while self.running:
            time.sleep(2.0)

    def _start_http_server(self):
        def handler_factory(*args, **kwargs):
            return DarkStudioAPIHandler(*args, controller=self, **kwargs)

        self.httpd = ThreadingHTTPServer((HOST, PORT), handler_factory)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def _start_tray_icon(self):
        menu = pystray.Menu(
            pystray.MenuItem("🚀 Abrir App Nativo DarkBooster", lambda icon, item: open_native_app_window(), default=True),
            pystray.MenuItem("⚡ Boost Rápido de RAM (Pré-Render)", self._tray_quick_ram_boost),
            pystray.MenuItem("🧹 Limpar Temp Remotion & Shaders", self._tray_quick_safe_clean),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Sair Completamente", self._tray_quit),
        )
        self.tray_icon = pystray.Icon(
            "DarkBooster",
            create_tray_icon_image(alert=False),
            "DarkBooster (App Desktop Nativo)",
            menu,
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def notify_tray(self, title: str, message: str):
        if self.tray_icon:
            try:
                self.tray_icon.notify(message, title)
            except Exception:
                pass

    def _tray_quick_ram_boost(self, icon=None, item=None):
        killed, k_mb = opt.kill_orphan_render_workers()
        res = opt.optimize_system_ram()
        msg = f"RAM Liberada: ~{res['freed_mb'] + k_mb:.0f} MB | Disponível: {res['available_gb']} GB"
        if killed:
            msg += f" ({killed} processos headless zumbis encerrados)"
        self.notify_tray("⚡ Boost de RAM Concluído", msg)
        opt.trim_self_memory()

    def _tray_quick_safe_clean(self, icon=None, item=None):
        cats = scanner.scan_safe_categories()
        freed = 0
        for c in cats:
            if c["id"] in ("temp_remotion", "temp_claude", "gpu_shaders", "onedrive_internal"):
                fr, _ = scanner.clean_safe_category(c)
                freed += fr
        self.notify_tray("🧹 Limpeza Rápida Concluída", f"Espaço recuperado: {scanner.format_size(freed)}")
        opt.trim_self_memory()

    def _tray_quit(self, icon=None, item=None):
        self.running = False
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        os._exit(0)

    def _background_monitor_loop(self):
        while self.running:
            try:
                interval = max(25, int(self.config.get("check_interval_seconds", 60)))
                time.sleep(interval)
                opt.trim_self_memory()

                rendering, render_apps = opt.is_rendering_active()
                if self.config.get("auto_render_priority", True):
                    opt.apply_render_priority_boost(enable=True)
                if rendering and self.config.get("pause_during_render", True):
                    if self.tray_icon:
                        self.tray_icon.title = f"DarkBooster — Modo Render + Prioridade Alta ({', '.join(render_apps[:2])})"
                    continue

                usage = psutil.disk_usage("C:\\")
                free_gb = usage.free / (1024 ** 3)
                threshold_gb = float(self.config.get("ssd_alert_threshold_gb", 25.0))

                if self.tray_icon:
                    self.tray_icon.title = f"DarkStudio — SSD Livre: {free_gb:.1f} GB ({100 - usage.percent:.0f}%)"
                    self.tray_icon.icon = create_tray_icon_image(alert=(free_gb < threshold_gb))

                if free_gb < threshold_gb and (time.time() - self.last_alert_time) > 600:
                    self.last_alert_time = time.time()
                    if self.config.get("auto_clean_safe_on_low_disk", False) and not rendering:
                        cats = scanner.scan_safe_categories()
                        freed = 0
                        for c in cats:
                            if c["id"] in ("temp_remotion", "temp_claude", "onedrive_internal", "gpu_shaders"):
                                fr, _ = scanner.clean_safe_category(c)
                                freed += fr
                        new_free_gb = psutil.disk_usage("C:\\").free / (1024 ** 3)
                        self.notify_tray(
                            "🛡️ Auto-Limpeza de SSD Executada",
                            f"Recuperados {scanner.format_size(freed)} (Livre agora: {new_free_gb:.1f} GB).",
                        )
                    else:
                        self.notify_tray(
                            "⚠️ Alerta de Espaço no SSD (C:)",
                            f"Espaço livre caiu para {free_gb:.1f} GB. Clique para abrir o painel DarkStudio!",
                        )
            except Exception:
                pass


if __name__ == "__main__":
    if "--native-window" in sys.argv:
        run_native_webview_window()
        sys.exit(0)

    start_tray = "--tray" in sys.argv
    if is_port_in_use(PORT):
        if not start_tray:
            open_native_app_window()
        sys.exit(0)
    DarkStudioController(start_in_tray=start_tray)
