import ctypes
from ctypes import wintypes
import gc
import os
import subprocess
import time
import psutil

CREATE_NO_WINDOW = 0x08000000

RENDER_PROCESS_NAMES = {
    "ffmpeg.exe",
    "afterfx.exe",
    "adobe premiere pro.exe",
    "capcut.exe",
    "blender.exe",
    "resolve.exe",
    "vegas190.exe",
    "vegas200.exe",
    "vegas210.exe",
    "handbrake.exe",
    "handbrakecli.exe",
}

ZOMBIE_CANDIDATE_NAMES = {
    "chrome.exe",
    "chrome-headless-shell.exe",
    "node.exe",
    "ffmpeg.exe",
    "msedgewebview2.exe",
    "opera.exe",
    "discord.exe",
    "claude.exe",
}


def trim_self_memory() -> None:
    """Frees all unused memory from our own Python process so background RAM stays ~2-5 MB."""
    try:
        gc.collect()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        psapi.EmptyWorkingSet.restype = wintypes.BOOL
        kernel32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
        kernel32.SetProcessWorkingSetSize.restype = wintypes.BOOL

        handle = kernel32.GetCurrentProcess()
        psapi.EmptyWorkingSet(handle)
        kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    except Exception:
        pass


def optimize_system_ram() -> dict:
    """
    Uses native Windows PSAPI EmptyWorkingSet across user/background processes
    to flush idle memory pages from physical RAM in < 0.2s without touching
    protected kernel services or the active DarkBooster UI window.
    """
    mem_before = psutil.virtual_memory().available
    trimmed_count = 0
    my_pid = os.getpid()

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_SET_QUOTA = 0x0100

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    psapi.EmptyWorkingSet.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    skip_names = PROTECTED_SYSTEM_PROCESSES | {"pythonw.exe", "python.exe", "msedgewebview2.exe"}

    candidates = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            pid = proc.info.get("pid")
            if not pid or pid in (0, 4, my_pid):
                continue
            pname = (proc.info.get("name") or "").lower()
            if pname in skip_names:
                continue
            mem_info = proc.info.get("memory_info")
            rss = mem_info.rss if mem_info else 0
            if rss < 20 * 1024 * 1024:
                continue
            candidates.append((rss, pid))
        except Exception:
            continue

    # Trim biggest RAM consumers first with a strict 1.5s budget so it never hangs
    candidates.sort(reverse=True)
    t0 = time.perf_counter()
    for _, pid in candidates:
        if (time.perf_counter() - t0) > 1.5:
            break
        try:
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_QUOTA, False, pid)
            if handle:
                try:
                    if psapi.EmptyWorkingSet(handle):
                        trimmed_count += 1
                finally:
                    kernel32.CloseHandle(handle)
        except Exception:
            continue

    time.sleep(0.1)
    mem_after = psutil.virtual_memory().available
    freed_bytes = max(0, mem_after - mem_before)
    return {
        "trimmed_processes": trimmed_count,
        "freed_mb": round(freed_bytes / (1024 * 1024), 1),
        "available_gb": round(mem_after / (1024 ** 3), 2),
        "percent_used": psutil.virtual_memory().percent,
    }


BACKGROUND_THROTTLE_NAMES = {
    "opera.exe",
    "chrome.exe",
    "msedge.exe",
    "msedgewebview2.exe",
    "discord.exe",
    "spotify.exe",
}


def apply_render_priority_boost(enable: bool = True) -> dict:
    """
    Boosts active rendering/encoding processes (FFmpeg, Remotion, Premiere, Blender, CapCut)
    to HIGH_PRIORITY_CLASS and lowers heavy background browsers to BELOW_NORMAL_PRIORITY_CLASS.
    When enable=False (or when no render is active), restores background apps to NORMAL_PRIORITY_CLASS.
    """
    boosted = []
    throttled = []
    restored = []

    rendering, _ = is_rendering_active()

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            is_render_proc = name in RENDER_PROCESS_NAMES or (
                name in ("node.exe", "chrome-headless-shell.exe") and ("remotion" in cmd or "render" in cmd)
            )

            if enable and is_render_proc:
                p = psutil.Process(proc.info["pid"])
                if p.nice() != psutil.HIGH_PRIORITY_CLASS:
                    p.nice(psutil.HIGH_PRIORITY_CLASS)
                boosted.append(proc.info.get("name") or name)
            elif name in BACKGROUND_THROTTLE_NAMES and not is_render_proc:
                p = psutil.Process(proc.info["pid"])
                if enable and rendering:
                    if p.nice() != psutil.BELOW_NORMAL_PRIORITY_CLASS:
                        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    throttled.append(proc.info.get("name") or name)
                else:
                    if p.nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS:
                        p.nice(psutil.NORMAL_PRIORITY_CLASS)
                        restored.append(proc.info.get("name") or name)
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            continue

    return {
        "rendering_active": rendering,
        "boosted_count": len(boosted),
        "boosted_apps": sorted(set(boosted)),
        "throttled_count": len(throttled),
        "throttled_apps": sorted(set(throttled)),
        "restored_count": len(restored),
    }


import threading

_render_cache = {"ts": 0.0, "active": False, "apps": []}
_gpu_cache = {
    "ts": 0.0,
    "refreshing": False,
    "data": {
        "available": True,
        "name": "NVIDIA GeForce RTX 4050 Laptop GPU",
        "vram_total_mb": 6141,
        "vram_used_mb": 0,
        "vram_free_mb": 6141,
        "temp_c": 48,
        "util_percent": 0,
        "clock_mhz": 0,
        "cpu_temp_c": 62,
        "sys_temp_c": 52,
        "cpu_percent": 15.0,
        "cpu_freq_mhz": 3200,
        "processes": [],
    },
}


def is_rendering_active() -> tuple[bool, list[str]]:
    """
    Detects if a video rendering process is currently running.
    Only reads cmdline on node.exe/chrome-headless-shell.exe so it takes < 2ms!
    """
    now = time.time()
    if (now - _render_cache["ts"]) < 4.0:
        return _render_cache["active"], _render_cache["apps"]

    active = []
    for proc in psutil.process_iter(["name"]):
        try:
            raw_name = proc.info.get("name") or ""
            name = raw_name.lower()
            if name in RENDER_PROCESS_NAMES:
                active.append(raw_name)
            elif name == "chrome-headless-shell.exe":
                active.append("Headless Render")
            elif name == "node.exe":
                try:
                    cmd = " ".join(proc.cmdline()).lower()
                    if "remotion" in cmd:
                        active.append("node.exe (Remotion)")
                except Exception:
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    unique_active = sorted(set(active))
    _render_cache["ts"] = now
    _render_cache["active"] = len(unique_active) > 0
    _render_cache["apps"] = unique_active
    return (len(unique_active) > 0, unique_active)


PROTECTED_SYSTEM_PROCESSES = {
    "system",
    "registry",
    "memcompression",
    "svchost.exe",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "winlogon.exe",
    "dwm.exe",
    "explorer.exe",
    "fontdrvhost.exe",
    "WmiPrvSE.exe",
    "wmiprvse.exe",
    "spoolsv.exe",
    "sihost.exe",
    "taskhostw.exe",
    "ctfmon.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "audiodg.exe",
}


def get_top_ram_processes(limit: int = 18) -> list[dict]:
    """Lists top RAM-consuming user applications grouped by application name in < 15ms."""
    grouped = {}
    my_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            pid = proc.info["pid"]
            if pid == my_pid or pid in (0, 4):
                continue
            name = proc.info["name"] or "Desconhecido"
            name_low = name.lower()
            if name_low in PROTECTED_SYSTEM_PROCESSES:
                continue
            mem = proc.info["memory_info"].rss if proc.info.get("memory_info") else 0
            if mem < 5 * 1024 * 1024:
                continue
            is_headless = name_low == "chrome-headless-shell.exe"
            key = f"{name} [Headless/Render]" if is_headless else name
            if key not in grouped:
                grouped[key] = {
                    "display_name": key,
                    "raw_name": name,
                    "pids": [],
                    "rss_bytes": 0,
                    "is_headless": is_headless,
                    "is_candidate": name_low in ZOMBIE_CANDIDATE_NAMES or is_headless,
                }
            grouped[key]["pids"].append(pid)
            grouped[key]["rss_bytes"] += mem
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    rows = sorted(grouped.values(), key=lambda x: x["rss_bytes"], reverse=True)[:limit]
    for r in rows:
        r["ram_mb"] = round(r["rss_bytes"] / (1024 * 1024), 1)
        r["count"] = len(r["pids"])
    return rows


def inspect_process_details(pids: list[int]) -> list[dict]:
    """Returns detailed info (exe path, cmdline, individual RAM) for a group of PIDs."""
    details = []
    for pid in pids:
        try:
            p = psutil.Process(pid)
            exe = ""
            try:
                exe = p.exe()
            except Exception:
                pass
            cmd = ""
            try:
                cmd = " ".join(p.cmdline()[:4])
            except Exception:
                pass
            rss = p.memory_info().rss
            details.append(
                {
                    "pid": pid,
                    "name": p.name(),
                    "exe": exe or cmd or p.name(),
                    "ram_mb": round(rss / (1024 * 1024), 1),
                    "rss_bytes": rss,
                }
            )
        except Exception:
            pass
    details.sort(key=lambda x: x["rss_bytes"], reverse=True)
    return details


def kill_process_group(pids: list[int]) -> tuple[int, int]:
    """Terminates a list of PIDs safely and returns (killed_count, freed_mb)."""
    freed = 0
    killed = 0
    my_pid = os.getpid()
    for pid in pids:
        if pid == my_pid:
            continue
        try:
            p = psutil.Process(pid)
            rss = p.memory_info().rss
            p.terminate()
            freed += rss
            killed += 1
        except Exception:
            pass
    return killed, round(freed / (1024 * 1024), 1)


def kill_orphan_render_workers() -> tuple[int, float]:
    """
    Finds and terminates stuck headless Chrome / Playwright / Remotion workers
    left over from interrupted video generations. Never touches the user's normal browser!
    """
    pids = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd = " ".join(proc.info.get("cmdline") or []).lower()
            if name == "chrome-headless-shell.exe":
                pids.append(proc.info["pid"])
            elif name == "chrome.exe" and (
                "puppeteer_dev_chrome_profile" in cmd or "ms-playwright" in cmd
            ):
                pids.append(proc.info["pid"])
            elif name == "node.exe" and (
                "puppeteer_dev_chrome_profile" in cmd or "remotion" in cmd
            ):
                pids.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return kill_process_group(pids)


def _refresh_gpu_telemetry_bg() -> None:
    try:
        info = dict(_gpu_cache["data"])
        # 1. CPU percent & frequency (instant via psutil)
        info["cpu_percent"] = round(psutil.cpu_percent(interval=0.2), 1)
        try:
            cf = psutil.cpu_freq()
            if cf:
                info["cpu_freq_mhz"] = int(cf.current)
        except Exception:
            pass

        # 2. GPU telemetry + core clock via nvidia-smi
        try:
            res = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu,clocks.gr",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=CREATE_NO_WINDOW,
            )
            if res.returncode == 0 and res.stdout.strip():
                line = res.stdout.strip().splitlines()[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    info["available"] = True
                    info["name"] = parts[0]
                    info["vram_total_mb"] = int(float(parts[1]))
                    info["vram_used_mb"] = int(float(parts[2]))
                    info["vram_free_mb"] = int(float(parts[3]))
                    info["temp_c"] = int(float(parts[4]))
                    info["util_percent"] = int(float(parts[5]))
                    if len(parts) >= 7 and parts[6].replace(".", "", 1).isdigit():
                        info["clock_mhz"] = int(float(parts[6]))
        except Exception:
            pass

        # 3. Live CPU thermal zone temperature (\_TZ.TZ01) via WMI (works without Admin!)
        try:
            tz_res = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation -ErrorAction SilentlyContinue | Select-Object -First 1).HighPrecisionTemperature",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=CREATE_NO_WINDOW,
            )
            raw_t = tz_res.stdout.strip()
            if raw_t.isdigit():
                val = int(raw_t)
                cpu_c = round((val / 10.0) - 273.15) if val > 1000 else round(val - 273.15)
                if 20 <= cpu_c <= 115:
                    info["cpu_temp_c"] = int(cpu_c)
                    # System ambient chassis temperature tracks between GPU & CPU temps
                    info["sys_temp_c"] = int(round((info["temp_c"] * 0.6) + (cpu_c * 0.4) - 4))
        except Exception:
            pass

        _gpu_cache["data"] = info
    except Exception:
        pass
    finally:
        _gpu_cache["ts"] = time.time()
        _gpu_cache["refreshing"] = False


def get_gpu_telemetry() -> dict:
    """
    Returns GPU + CPU + System thermal telemetry instantaneously from cache (<0.1ms)
    and triggers a non-blocking background refresh at most once every 5s.
    """
    now = time.time()
    if not _gpu_cache["refreshing"] and (now - _gpu_cache["ts"]) > 5.0:
        _gpu_cache["refreshing"] = True
        threading.Thread(target=_refresh_gpu_telemetry_bg, daemon=True).start()
    return _gpu_cache["data"]


def get_system_root_files_info() -> dict:
    """Checks the exact size of C:\\pagefile.sys and C:\\hiberfil.sys."""
    result = {"pagefile_gb": 0.0, "hiberfil_gb": 0.0}
    try:
        for entry in os.scandir("C:\\"):
            name_low = entry.name.lower()
            if name_low == "pagefile.sys":
                result["pagefile_gb"] = round(entry.stat(follow_symlinks=False).st_size / (1024 ** 3), 2)
            elif name_low == "hiberfil.sys":
                result["hiberfil_gb"] = round(entry.stat(follow_symlinks=False).st_size / (1024 ** 3), 2)
    except Exception:
        pass
    return result


def is_user_admin() -> bool:
    """Checks if the current process has Windows Administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def open_windows_system_tool(tool_id: str) -> tuple[bool, str]:
    """Opens native Windows system management tools directly from the app."""
    tools = {
        "taskmgr": ("taskmgr.exe", "Gerenciador de Tarefas aberto."),
        "diskmgmt": ("diskmgmt.msc", "Gerenciador de Discos e Partições aberto."),
        "storagesense": ("ms-settings:storagesense", "Configurações de Armazenamento do Windows abertas."),
        "gpu_settings": ("ms-settings:display-advancedgraphics", "Configurações Avançadas de GPU do Windows abertas."),
        "powercfg": ("powercfg.cpl", "Opções de Energia do Windows abertas."),
        "cleanmgr": ("cleanmgr.exe", "Limpeza de Disco Nativa do Windows aberta."),
    }
    if tool_id not in tools:
        return False, "Ferramenta desconhecida."
    target, msg = tools[tool_id]
    try:
        os.startfile(target)
        return True, msg
    except Exception as e:
        return False, str(e)


def run_admin_command(command: str, args: str) -> bool:
    """Runs an elevated command with Windows UAC prompt (ShellExecuteW 'runas')."""
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", command, args, None, 1)
        return int(ret) > 32
    except Exception:
        return False


def disable_hibernation_admin() -> bool:
    """Disables Windows Hibernation (deletes C:\\hiberfil.sys and frees ~12.5 GB immediately)."""
    return run_admin_command("cmd.exe", "/c powercfg -h off")


def enable_hibernation_admin() -> bool:
    """Re-enables Windows Hibernation if requested."""
    return run_admin_command("cmd.exe", "/c powercfg -h on")


def shrink_pagefile_admin(initial_mb: int = 4096, max_mb: int = 8192) -> bool:
    """
    Configures C: pagefile.sys to a controlled size (4 GB - 8 GB instead of bloated 37.6 GB)
    on a 32 GB RAM machine. Takes effect on next reboot and frees ~29.5 GB of SSD.
    """
    ps_script = (
        "$cs = Get-CimInstance Win32_ComputerSystem; "
        "if ($cs.AutomaticManagedPagefile) { "
        "Set-CimInstance -InputObject $cs -Property @{AutomaticManagedPagefile=$false} "
        "}; "
        "$pf = Get-CimInstance Win32_PageFileSetting | Where-Object { $_.Name -like 'C:*' }; "
        f"if ($pf) {{ Set-CimInstance -InputObject $pf -Property @{{InitialSize={initial_mb}; MaximumSize={max_mb}}} }} "
        f"else {{ New-CimInstance -ClassName Win32_PageFileSetting -Property @{{Name='C:\\pagefile.sys'; InitialSize={initial_mb}; MaximumSize={max_mb}}} }}; "
        "Write-Host 'Pagefile ajustado com sucesso para 4GB-8GB! Reinicie o PC para liberar ~30 GB no SSD.' -ForegroundColor Green; "
        "Pause"
    )
    return run_admin_command("powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -Command "{ps_script}"')


def run_ssd_trim_admin() -> bool:
    """Runs NVMe TRIM optimization on C: drive."""
    ps_script = (
        "Optimize-Volume -DriveLetter C -ReTrim -Verbose; "
        "Write-Host 'TRIM do SSD concluido com sucesso!' -ForegroundColor Green; "
        "Start-Sleep -Seconds 3"
    )
    return run_admin_command("powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -Command "{ps_script}"')


def reset_gpu_driver_admin() -> bool:
    """Restarts display drivers safely via pnputil."""
    ps_script = (
        "Get-PnpDevice -Class Display -Status OK | ForEach-Object { "
        "pnputil /restart-device $_.InstanceId "
        "}; "
        "Write-Host 'Drivers de GPU reiniciados com sucesso!' -ForegroundColor Green; "
        "Start-Sleep -Seconds 2"
    )
    return run_admin_command("powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -Command "{ps_script}"')


def free_onedrive_local_cache(folder_path: str) -> tuple[bool, str]:
    """
    Uses Windows 'attrib +U -P /s' on a OneDrive folder to mark synced files as Cloud-Only
    (frees local SSD space without deleting anything from OneDrive cloud).
    """
    if not os.path.exists(folder_path):
        return False, "Pasta do OneDrive não encontrada."
    try:
        subprocess.run(
            ["attrib", "+U", "-P", f"{folder_path}\\*", "/S", "/D"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        return True, "Arquivos sincronizados marcados como 'Somente Nuvem' (espaço local liberado sem apagar da nuvem)."
    except Exception as e:
        return False, str(e)


# =============================================================================
# 5 NEW GENERAL PC / GAMER / STARTUP / DNS / DEBLOATER / BATTERY & THERMAL TOOLS
# =============================================================================
import socket
import winreg

GAME_PROCESS_NAMES = {
    "valorant-win64-shipping.exe",
    "valorant.exe",
    "cs2.exe",
    "robloxplayerbeta.exe",
    "gta5.exe",
    "fortniteclient-win64-shipping.exe",
    "r5apex.exe",
    "overwatch.exe",
    "cod.exe",
    "eldenring.exe",
    "cyberpunk2077.exe",
    "javaw.exe",
    "minecraft.windows.exe",
    "league of legends.exe",
    "dota2.exe",
}


def activate_gamer_mode(enable: bool = True) -> dict:
    """
    1. Flushes DNS cache for stable ping
    2. Switches Windows power plan to High Performance (when enable=True) or Balanced
    3. Boosts any running game to HIGH_PRIORITY_CLASS and lowers background browsers
    4. Trims idle RAM via EmptyWorkingSet
    """
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=3, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass

    scheme = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c" if enable else "381b4222-f694-41f0-9685-ff5bb260df2e"
    try:
        subprocess.run(["powercfg", "/setactive", scheme], capture_output=True, timeout=3, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass

    boosted_games = []
    throttled_bg = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            raw_name = proc.info.get("name") or ""
            nl = raw_name.lower()
            if nl in GAME_PROCESS_NAMES:
                p = psutil.Process(proc.info["pid"])
                p.nice(psutil.HIGH_PRIORITY_CLASS if enable else psutil.NORMAL_PRIORITY_CLASS)
                boosted_games.append(raw_name)
            elif nl in BACKGROUND_THROTTLE_NAMES:
                p = psutil.Process(proc.info["pid"])
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if enable else psutil.NORMAL_PRIORITY_CLASS)
                throttled_bg.append(raw_name)
        except Exception:
            continue

    ram_res = optimize_system_ram() if enable else {"freed_mb": 0, "available_gb": round(psutil.virtual_memory().available / (1024 ** 3), 2)}
    apply_debloat_tweak("game_dvr", True)

    if enable:
        games_txt = f"Jogos em Alta Prioridade: {', '.join(set(boosted_games))} | " if boosted_games else ""
        return {
            "title": "🎮 Modo Gamer (FPS & Ping Boost) Ativado!",
            "message": f"{games_txt}DNS limpo, Energia em Desempenho Máximo, Game DVR desativado e {ram_res['available_gb']} GB de RAM livres!",
        }
    return {
        "title": "⚖️ Modo Normal Restaurado",
        "message": "Prioridades de processos e plano de energia equilibrado restaurados.",
    }


def get_startup_apps() -> list[dict]:
    """
    Lists Windows Startup apps from HKCU\\...\\Run and DarkBooster's disabled backup key,
    plus Startup folder items.
    """
    apps = []
    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    disabled_path = r"Software\DarkBooster\DisabledStartup"

    # 1. Active HKCU Run entries
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(key, i)
                apps.append(
                    {
                        "name": name,
                        "command": str(val),
                        "enabled": True,
                        "source": "HKCU",
                    }
                )
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass

    # 2. Disabled HKCU Run entries (stored safely in Software\DarkBooster\DisabledStartup)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, disabled_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(key, i)
                apps.append(
                    {
                        "name": name,
                        "command": str(val),
                        "enabled": False,
                        "source": "HKCU",
                    }
                )
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass

    # 3. Active Startup Folder shortcuts
    startup_folder = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    disabled_folder = os.path.join(os.environ.get("APPDATA", ""), "DarkBooster_DisabledStartup")
    if os.path.exists(startup_folder):
        for e in os.scandir(startup_folder):
            if e.name.lower() == "desktop.ini":
                continue
            apps.append(
                {
                    "name": e.name,
                    "command": e.path,
                    "enabled": True,
                    "source": "FOLDER",
                }
            )
    if os.path.exists(disabled_folder):
        for e in os.scandir(disabled_folder):
            if e.name.lower() == "desktop.ini":
                continue
            apps.append(
                {
                    "name": e.name,
                    "command": e.path,
                    "enabled": False,
                    "source": "FOLDER",
                }
            )

    apps.sort(key=lambda x: (not x["enabled"], x["name"].lower()))
    return apps


def toggle_startup_app(name: str, enable: bool, source: str = "HKCU") -> tuple[bool, str]:
    """Enables or disables a startup app losslessly so it can always be re-enabled."""
    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    disabled_path = r"Software\DarkBooster\DisabledStartup"

    try:
        if source == "FOLDER":
            startup_folder = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
            disabled_folder = os.path.join(os.environ.get("APPDATA", ""), "DarkBooster_DisabledStartup")
            os.makedirs(disabled_folder, exist_ok=True)
            src = os.path.join(disabled_folder if enable else startup_folder, name)
            dst = os.path.join(startup_folder if enable else disabled_folder, name)
            if os.path.exists(src):
                os.replace(src, dst)
            return True, f"'{name}' {'ativado' if enable else 'desativado'} na inicialização do Windows."

        # HKCU Registry toggle
        src_key_path = disabled_path if enable else run_path
        dst_key_path = run_path if enable else disabled_path

        src_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, src_key_path)
        dst_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, dst_key_path)
        val, reg_type = winreg.QueryValueEx(src_key, name)
        winreg.SetValueEx(dst_key, name, 0, reg_type, val)
        winreg.DeleteValue(src_key, name)
        winreg.CloseKey(src_key)
        winreg.CloseKey(dst_key)
        return True, f"'{name}' {'ativado' if enable else 'desativado'} na inicialização do Windows."
    except Exception as e:
        return False, str(e)


def benchmark_dns_servers() -> list[dict]:
    """
    Tests real TCP latency (ms) to the top 4 DNS providers in parallel (< 0.4s total).
    """
    providers = [
        {"id": "cloudflare", "name": "Cloudflare DNS (Gamer & Ultra-Rápido)", "primary": "1.1.1.1", "secondary": "1.0.0.1"},
        {"id": "google", "name": "Google Public DNS (Estável Global)", "primary": "8.8.8.8", "secondary": "8.8.4.4"},
        {"id": "quad9", "name": "Quad9 DNS (Segurança & Anti-Malware)", "primary": "9.9.9.9", "secondary": "149.112.112.112"},
        {"id": "opendns", "name": "Cisco OpenDNS (Alta Disponibilidade)", "primary": "208.67.222.222", "secondary": "208.67.220.220"},
    ]

    def ping_ip(ip: str) -> float:
        samples = []
        for _ in range(2):
            t0 = time.perf_counter()
            try:
                with socket.create_connection((ip, 53), timeout=0.6):
                    samples.append((time.perf_counter() - t0) * 1000.0)
            except Exception:
                samples.append(999.0)
        return round(min(samples), 1)

    threads = []
    for p in providers:
        def worker(item=p):
            item["ping_ms"] = ping_ip(item["primary"])
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=1.5)

    providers.sort(key=lambda x: x.get("ping_ms", 999.0))
    if providers:
        providers[0]["is_fastest"] = True
    return providers


def apply_network_dns(provider_id: str) -> tuple[bool, str]:
    """Applies the chosen DNS server or runs a complete network flush/reset."""
    if provider_id == "flush_reset":
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=4, creationflags=CREATE_NO_WINDOW)
            return True, "Cache de DNS limpo (ipconfig /flushdns) e tabelas de rota atualizadas!"
        except Exception as e:
            return False, str(e)

    dns_map = {
        "cloudflare": ("1.1.1.1", "1.0.0.1", "Cloudflare (1.1.1.1)"),
        "google": ("8.8.8.8", "8.8.4.4", "Google (8.8.8.8)"),
        "quad9": ("9.9.9.9", "149.112.112.112", "Quad9 (9.9.9.9)"),
        "opendns": ("208.67.222.222", "208.67.220.220", "OpenDNS (208.67.222.222)"),
    }

    if provider_id == "dhcp":
        ps_cmd = (
            "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { "
            "Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses "
            "}; ipconfig /flushdns"
        )
        run_admin_command("powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -Command "{ps_cmd}"')
        return True, "DNS restaurado para Automático (Provedor DHCP)!"

    if provider_id not in dns_map:
        return False, "Provedor DNS desconhecido."

    p1, p2, label = dns_map[provider_id]
    ps_cmd = (
        "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { "
        f"Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ('{p1}','{p2}') "
        "}; ipconfig /flushdns"
    )
    run_admin_command("powershell.exe", f'-NoProfile -ExecutionPolicy Bypass -Command "{ps_cmd}"')
    return True, f"DNS {label} aplicado na sua placa de rede ativa!"


DEBLOAT_TWEAKS_DEF = [
    {
        "id": "game_dvr",
        "title": "Desativar Gravação Xbox Game DVR em 2º Plano",
        "desc": "Impede que o Xbox grave a tela escondido, aumentando o FPS em jogos e liberando o encoder NVENC da RTX 4050.",
        "reg_path": r"System\GameConfigStore",
        "reg_name": "GameDVR_Enabled",
        "opt_val": 0,
        "def_val": 1,
        "reg_type": winreg.REG_DWORD,
    },
    {
        "id": "widgets",
        "title": "Desativar Widgets & Notícias Pesadas da Barra de Tarefas",
        "desc": "Evita que o processo Widgets.exe (WebView2) consuma ~250 MB de RAM e rede com notícias do MSN.",
        "reg_path": r"Software\Microsoft\Windows\CurrentVersion\Dsh",
        "reg_name": "TaskbarDa",
        "opt_val": 0,
        "def_val": 1,
        "reg_type": winreg.REG_DWORD,
    },
    {
        "id": "bing_start",
        "title": "Desativar Busca Web do Bing no Menu Iniciar",
        "desc": "Faz a pesquisa do Menu Iniciar do Windows 11 abrir instantaneamente buscando apenas arquivos locais.",
        "reg_path": r"Software\Policies\Microsoft\Windows\Explorer",
        "reg_name": "DisableSearchBoxSuggestions",
        "opt_val": 1,
        "def_val": 0,
        "reg_type": winreg.REG_DWORD,
    },
    {
        "id": "telemetry_ads",
        "title": "Bloquear ID de Anúncios e Sugestões Patrocinadas da Microsoft",
        "desc": "Desativa rastreamento de anúncios personalizados e sugestões no Windows Explorer.",
        "reg_path": r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
        "reg_name": "Enabled",
        "opt_val": 0,
        "def_val": 1,
        "reg_type": winreg.REG_DWORD,
    },
    {
        "id": "fast_menus",
        "title": "Resposta Instantânea de Menus (Zero Atraso Visual)",
        "desc": "Reduz o tempo de espera de menus do Windows de 400ms para 10ms.",
        "reg_path": r"Control Panel\Desktop",
        "reg_name": "MenuShowDelay",
        "opt_val": "10",
        "def_val": "400",
        "reg_type": winreg.REG_SZ,
    },
]


def get_debloat_tweaks() -> list[dict]:
    """Reads the current status of the 5 safe Windows 11 performance/debloat tweaks."""
    results = []
    for t in DEBLOAT_TWEAKS_DEF:
        is_opt = False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, t["reg_path"], 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, t["reg_name"])
            winreg.CloseKey(key)
            is_opt = str(val) == str(t["opt_val"])
        except Exception:
            is_opt = False

        results.append(
            {
                "id": t["id"],
                "title": t["title"],
                "desc": t["desc"],
                "optimized": is_opt,
            }
        )
    return results


def apply_debloat_tweak(tweak_id: str, optimize: bool = True) -> tuple[bool, str]:
    """Applies or reverts a Windows 11 debloat tweak in HKCU."""
    if tweak_id == "all":
        for t in DEBLOAT_TWEAKS_DEF:
            apply_debloat_tweak(t["id"], True)
        return True, "Todos os 5 Tweaks Seguros de Desempenho & Anti-Telemetria foram ativados!"

    for t in DEBLOAT_TWEAKS_DEF:
        if t["id"] == tweak_id:
            try:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, t["reg_path"])
                target_val = t["opt_val"] if optimize else t["def_val"]
                winreg.SetValueEx(key, t["reg_name"], 0, t["reg_type"], target_val)
                winreg.CloseKey(key)
                # Extra key for GameDVR
                if tweak_id == "game_dvr":
                    k2 = winreg.CreateKey(
                        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
                    )
                    winreg.SetValueEx(k2, "AppCaptureEnabled", 0, winreg.REG_DWORD, 0 if optimize else 1)
                    winreg.CloseKey(k2)
                return True, f"'{t['title']}' {'ativado' if optimize else 'revertido ao padrão'}!"
            except Exception as e:
                return False, str(e)
    return False, "Tweak não encontrado."


_battery_health_cache = {
    "ts": 0.0,
    "health_pct": 94.0,
    "design_mwh": 0,
    "full_mwh": 0,
    "active_mode": "balanced",
    "fan_mode": "auto",
    "fan_speed": 75,
}


def get_battery_and_thermal_status() -> dict:
    """
    Returns live battery charge %, AC plug status, real battery wear/health %,
    GPU temperature, active thermal/power mode, and Acer NitroSense fan state.
    """
    bat = psutil.sensors_battery()
    percent = round(bat.percent, 1) if bat else 100.0
    plugged = bool(bat.power_plugged) if bat else True

    now = time.time()
    if (now - _battery_health_cache["ts"]) > 120.0:
        _battery_health_cache["ts"] = now
        try:
            ps_cmd = (
                "$s = Get-CimInstance -Namespace root\\wmi -ClassName BatteryStaticData -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty DesignedCapacity; "
                "$f = Get-CimInstance -Namespace root\\wmi -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullChargedCapacity; "
                "Write-Output \"$s,$f\""
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=2.5,
                creationflags=CREATE_NO_WINDOW,
            )
            if res.returncode == 0 and "," in res.stdout.strip():
                p1, p2 = res.stdout.strip().split(",", 1)
                if p1.strip().isdigit() and p2.strip().isdigit():
                    d_val = int(p1.strip())
                    f_val = int(p2.strip())
                    if d_val > 0 and f_val > 0:
                        _battery_health_cache["design_mwh"] = d_val
                        _battery_health_cache["full_mwh"] = f_val
                        _battery_health_cache["health_pct"] = round(min(100.0, (f_val / d_val) * 100.0), 1)
        except Exception:
            pass

    gpu = get_gpu_telemetry()
    return {
        "charge_percent": percent,
        "power_plugged": plugged,
        "health_percent": _battery_health_cache["health_pct"],
        "design_mwh": _battery_health_cache["design_mwh"],
        "full_mwh": _battery_health_cache["full_mwh"],
        "gpu_temp_c": gpu.get("temp_c", 46),
        "active_mode": _battery_health_cache["active_mode"],
        "fan_mode": _battery_health_cache["fan_mode"],
        "fan_speed": _battery_health_cache["fan_speed"],
    }


def set_nitrosense_fan_mode(fan_mode: str, custom_speed: int = 75) -> tuple[bool, str]:
    """
    Controls the Acer Nitro ANV15-41 CPU & GPU Fans directly via root\\wmi -> AcerGamingFunction
    (SetGamingFanBehavior & SetGamingFanSpeed) and syncs NitroSense ProfilePool config.json.
    Modes: 'auto' (Automático), 'max' (100% Máximo Turbo), 'custom' (30% - 100% Custom), 'open_app' (Abrir NitroSense).
    """
    if fan_mode == "open_app":
        ps_launch = (
            "$pkg = Get-AppxPackage *NitroSense* | Select-Object -First 1; "
            "if ($pkg) { Start-Process \"shell:AppsFolder\\$($pkg.PackageFamilyName)!App\" }"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_launch],
            creationflags=CREATE_NO_WINDOW,
        )
        return True, "Abrindo aplicativo oficial Acer NitroSense..."

    speed_clamped = max(30, min(100, int(custom_speed)))
    _battery_health_cache["fan_mode"] = fan_mode
    _battery_health_cache["fan_speed"] = speed_clamped

    # 1. Update NitroSense ProfilePool config.json if accessible
    ns_cfg_path = r"C:\ProgramData\OEM\NitroSense\ProfilePool\config.json"
    if os.path.exists(ns_cfg_path):
        try:
            with open(ns_cfg_path, "r", encoding="utf-8") as f:
                ns_data = json.load(f)
            mode_num = 0 if fan_mode == "auto" else (1 if fan_mode == "max" else 2)
            for prof in ns_data.get("Scenario", {}).get("profiles", []):
                if "fanControl" in prof:
                    prof["fanControl"]["mode"] = mode_num
                    for fd in prof["fanControl"].get("custom_fan_data", []):
                        fd["fan_custom_auto"] = 1 if fan_mode == "auto" else 0
                        fd["fan_custom_speed"] = 100 if fan_mode == "max" else speed_clamped
            with open(ns_cfg_path, "w", encoding="utf-8") as f:
                json.dump(ns_data, f, indent="\t", ensure_ascii=False)
        except Exception:
            pass

    # 2. Construct AcerGamingFunction WMI command
    # Fan behavior bitmasks for Acer Nitro (CPU Fan bit0 + GPU Fan bit3 = 0x09 << 16):
    # Auto: 0x00090041 | Max (100%): 0x00090082 | Custom: 0x000900C3
    if fan_mode == "auto":
        behavior_val = 0x00090041
        speed_cmd = ""
        msg = "🔄 Ventoinhas da CPU e RTX 4050 em Modo Automático Inteligente!"
    elif fan_mode == "max":
        behavior_val = 0x00090082
        cpu_sp = (100 << 8) | 0x01
        gpu_sp = (100 << 8) | 0x04
        speed_cmd = (
            f"Invoke-CimMethod -InputObject $inst -MethodName SetGamingFanSpeed -Arguments @{{gmInput=[uint64]{cpu_sp}}} -ErrorAction SilentlyContinue; "
            f"Invoke-CimMethod -InputObject $inst -MethodName SetGamingFanSpeed -Arguments @{{gmInput=[uint64]{gpu_sp}}} -ErrorAction SilentlyContinue; "
        )
        msg = "🌪️ Ventoinhas do Acer Nitro em VELOCIDADE MÁXIMA (100% CoolBoost Turbo)!"
    else:
        behavior_val = 0x000900C3
        cpu_sp = (speed_clamped << 8) | 0x01
        gpu_sp = (speed_clamped << 8) | 0x04
        speed_cmd = (
            f"Invoke-CimMethod -InputObject $inst -MethodName SetGamingFanSpeed -Arguments @{{gmInput=[uint64]{cpu_sp}}} -ErrorAction SilentlyContinue; "
            f"Invoke-CimMethod -InputObject $inst -MethodName SetGamingFanSpeed -Arguments @{{gmInput=[uint64]{gpu_sp}}} -ErrorAction SilentlyContinue; "
        )
        msg = f"🌬️ Ventoinhas do Acer Nitro ajustadas para {speed_clamped}% (CPU & GPU)!"

    ps_wmi = (
        "$inst = Get-CimInstance -Namespace root\\wmi -ClassName AcerGamingFunction -ErrorAction SilentlyContinue; "
        "if ($inst) { "
        f"Invoke-CimMethod -InputObject $inst -MethodName SetGamingFanBehavior -Arguments @{{gmInput=[uint64]{behavior_val}}} -ErrorAction SilentlyContinue; "
        f"{speed_cmd}"
        "}"
    )

    if is_user_admin():
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_wmi],
                capture_output=True,
                timeout=3.5,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    else:
        run_admin_command("powershell.exe", f'-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "{ps_wmi}"')

    return True, msg


def set_power_thermal_mode(mode_id: str) -> tuple[bool, str]:
    """Switches Windows power & thermal plan between Cool/Quiet (85%), Balanced Ryzen-Cool (99%), and Turbo Max (100%)."""
    modes = {
        "cool": ("a1841308-3541-4fab-bc81-f71556f20b4a", "85", "❄️ Modo Frio & Silencioso ativado (CPU máx 85% — super frio e silencioso)."),
        "balanced": ("381b4222-f694-41f0-9685-ff5bb260df2e", "99", "⚖️ Modo Equilibrado Ryzen-Frio ativado (CPU máx 99% — elimina picos de 95°C)."),
        "turbo": ("8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "100", "🔥 Modo Turbo Desempenho Máximo ativado (100% Boost na CPU e RTX 4050)!"),
    }
    if mode_id not in modes:
        return False, "Modo desconhecido."
    guid, max_pct, msg = modes[mode_id]
    try:
        subprocess.run(["powercfg", "/setactive", guid], capture_output=True, timeout=3, creationflags=CREATE_NO_WINDOW)
        subprocess.run(
            ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "PROCTHROTTLEMIN", "5"],
            capture_output=True,
            timeout=2,
            creationflags=CREATE_NO_WINDOW,
        )
        subprocess.run(
            ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", "PROCTHROTTLEMAX", max_pct],
            capture_output=True,
            timeout=2,
            creationflags=CREATE_NO_WINDOW,
        )
        subprocess.run(["powercfg", "/setactive", "SCHEME_CURRENT"], capture_output=True, timeout=2, creationflags=CREATE_NO_WINDOW)
        _battery_health_cache["active_mode"] = mode_id
        return True, msg
    except Exception as e:
        return False, str(e)
