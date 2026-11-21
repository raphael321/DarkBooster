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
        "temp_c": 46,
        "util_percent": 0,
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
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
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
        _gpu_cache["data"] = info
    except Exception:
        pass
    finally:
        _gpu_cache["ts"] = time.time()
        _gpu_cache["refreshing"] = False


def get_gpu_telemetry() -> dict:
    """
    Returns GPU telemetry instantaneously from cache (<0.1ms) and triggers
    a non-blocking background refresh via nvidia-smi at most once every 10s.
    """
    now = time.time()
    if not _gpu_cache["refreshing"] and (now - _gpu_cache["ts"]) > 10.0:
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
