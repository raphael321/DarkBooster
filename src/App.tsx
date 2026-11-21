import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckSquare,
  Eye,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  Maximize2,
  Minus,
  RefreshCw,
  Settings,
  Shield,
  ShieldCheck,
  Sparkles,
  Square,
  Wrench,
  X,
  Zap,
} from "lucide-react";

import RecursiveErosionBackground from "@/components/ui/recursive-erosion";
import ShinyButton from "@/components/ui/shiny-button";

interface SafeCategory {
  id: string;
  title: string;
  desc: string;
  size_bytes: number;
  size_str: string;
  file_count: number;
  default_checked: boolean;
  open_dir?: string;
  existing_paths: string[];
}

interface PermissionItem {
  id: string;
  name: string;
  category: string;
  path: string;
  size_bytes: number;
  size_str: string;
  file_count: number;
  modified_str: string;
  days_old?: number;
  is_old?: boolean;
  risk_note: string;
  can_drilldown: boolean;
}

interface SubfolderItem {
  name: string;
  path: string;
  kind: string;
  is_recreatable: boolean;
  size_bytes: number;
  size_str: string;
  file_count: number;
  modified_str: string;
  days_old?: number;
  is_old?: boolean;
  is_dir: boolean;
}

interface DuplicateGroup {
  id: string;
  name: string;
  file_size_bytes: number;
  file_size_str: string;
  wasted_bytes: number;
  wasted_str: string;
  copies_count: number;
  original_path: string;
  extra_paths: string[];
  all_paths: string[];
}

interface StartupApp {
  name: string;
  command: string;
  enabled: boolean;
  source: string;
}

interface DebloatTweak {
  id: string;
  title: string;
  desc: string;
  optimized: boolean;
}

interface DnsProvider {
  id: string;
  name: string;
  primary: string;
  secondary: string;
  ping_ms: number;
  is_fastest?: boolean;
}

interface BatteryThermalStatus {
  charge_percent: number;
  power_plugged: boolean;
  health_percent: number;
  design_mwh: number;
  full_mwh: number;
  gpu_temp_c: number;
  active_mode: "cool" | "balanced" | "turbo";
  fan_mode?: "auto" | "max" | "custom";
  fan_speed?: number;
}

interface RamProcess {
  display_name: string;
  raw_name: string;
  pids: number[];
  rss_bytes: number;
  ram_mb: number;
  count: number;
  is_headless: boolean;
  is_candidate: boolean;
}

interface ProcessDetail {
  pid: number;
  name: string;
  exe: string;
  ram_mb: number;
  rss_bytes: number;
}

interface TelemetryData {
  ssd: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    percent_used: number;
    threshold_gb: number;
  };
  ram: {
    total_gb: number;
    used_gb: number;
    avail_gb: number;
    percent_used: number;
    app_rss_mb: number;
  };
  gpu: {
    available: boolean;
    name: string;
    vram_total_mb: number;
    vram_used_mb: number;
    vram_free_mb: number;
    vram_percent: number;
    temp_c: number;
    util_percent: number;
  };
  sys_files: {
    pagefile_gb: number;
    hiberfil_gb: number;
  };
  render: {
    active: boolean;
    apps: string[];
  };
  is_admin?: boolean;
  config: {
    ssd_alert_threshold_gb: number;
    auto_clean_safe_on_low_disk: boolean;
    pause_during_render: boolean;
    startup_enabled: boolean;
  };
}

declare global {
  interface Window {
    pywebview?: {
      api?: {
        minimize_window?: () => Promise<void>;
        toggle_maximize?: () => Promise<void>;
        close_to_tray?: () => Promise<void>;
        pick_folder?: () => Promise<string | null>;
      };
    };
  }
}

function RadialGauge({
  percent,
  color = "#ff5f00",
  size = 132,
  strokeWidth = 10,
  title,
  valueText,
  subText,
}: {
  percent: number;
  color?: string;
  size?: number;
  strokeWidth?: number;
  title: string;
  valueText: string;
  subText: string;
}) {
  const safePct = Math.max(0, Math.min(100, percent || 0));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (safePct / 100) * circumference;

  return (
    <div className="flex flex-col items-center">
      <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90 transform">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke="rgba(255,255,255,0.07)"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{
              transition: "stroke-dashoffset 0.7s cubic-bezier(0.22, 1, 0.36, 1)",
              filter: `drop-shadow(0 0 10px ${color}80)`,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-2xl font-black tracking-tight text-white">{safePct.toFixed(0)}%</span>
          <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">{title}</span>
        </div>
      </div>
      <div className="mt-3 text-center">
        <div className="text-lg font-extrabold text-white">{valueText}</div>
        <div className="text-xs text-zinc-400">{subText}</div>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  const mb = bytes / 1024 ** 2;
  if (mb >= 1000) {
    const gb = bytes >= 1024 ** 3 ? bytes / 1024 ** 3 : mb / 1000;
    return `${gb.toFixed(2)} GB`;
  }
  if (bytes >= 1024 ** 2) return `${mb.toFixed(0)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function formatMb(mb: number): string {
  if (mb >= 1000) {
    const gb = mb >= 1024 ? mb / 1024 : mb / 1000;
    return `${gb.toFixed(2)} GB`;
  }
  return `${mb.toFixed(0)} MB`;
}

function shortTitle(title: string): string {
  return title
    .replace("OneDrive: Cache Interno ListSync & Logs", "OneDrive (ListSync & Logs)")
    .replace("Temp: Arquivos Temporários do Claude", "Temp Claude")
    .replace("Temp: Bundles de Renderização (Remotion / Puppeteer / SQLite)", "Temp Render (Remotion / Puppeteer)")
    .replace("Temp: Arquivos Temporários Gerais do Windows", "Temp do Windows")
    .replace("GPU: Shader Cache (NVIDIA DXCache / GLCache / AMD / DirectX)", "Shader Cache GPU (NVIDIA / DirectX)")
    .replace("Sistema: Lixeira do Windows (C:\\$Recycle.Bin)", "Lixeira do Windows")
    .replace("Navegador: Cache de Mídia do Google Chrome (Mantém Logins)", "Cache do Chrome")
    .replace("Navegador: Cache de Mídia do Opera (Mantém Logins)", "Cache do Opera")
    .replace("Apps Dark & Editores: Caches, Updaters e CrashDumps", "Cache Apps Dark & Adobe")
    .replace("Caches de Pacotes (NPM / PNPM / PIP / UV / WinGet)", "Cache NPM / PIP / UV");
}

function directSourcePath(cat: SafeCategory): string {
  const map: Record<string, string> = {
    onedrive_internal: "AppData\\Local\\Microsoft\\OneDrive\\ListSync",
    temp_claude: "AppData\\Local\\Temp\\claude",
    temp_remotion: "AppData\\Local\\Temp\\remotion-* & puppeteer_*",
    temp_general: "AppData\\Local\\Temp",
    gpu_shaders: "AppData\\Local\\NVIDIA\\DXCache & GLCache",
    recycle_bin: "C:\\$Recycle.Bin (Lixeira)",
    browser_chrome: "AppData\\Local\\Google\\Chrome\\User Data\\...\\Cache",
    browser_opera: "AppData\\Roaming\\Opera Software\\...\\Cache",
    dark_apps_cache: "AppData\\Local\\darkplanner-updater & Adobe Media Cache",
    dev_package_caches: "AppData\\Local\\npm-cache, pnpm-cache, pip & uv",
  };
  return map[cat.id] || cat.open_dir || cat.existing_paths?.[0] || "";
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"overview" | "safe" | "perm" | "hw" | "pc">("overview");
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [safeCategories, setSafeCategories] = useState<SafeCategory[]>([]);
  const [selectedSafeIds, setSelectedSafeIds] = useState<Record<string, boolean>>({});
  const [permissionItems, setPermissionItems] = useState<PermissionItem[]>([]);
  const [ramProcesses, setRamProcesses] = useState<RamProcess[]>([]);
  const [busyMessage, setBusyMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<{ title: string; msg: string } | null>(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [onlyOldFilter, setOnlyOldFilter] = useState(false);

  // PC & Gamer 5 Modules State
  const [startupApps, setStartupApps] = useState<StartupApp[]>([]);
  const [debloatTweaks, setDebloatTweaks] = useState<DebloatTweak[]>([]);
  const [dnsProviders, setDnsProviders] = useState<DnsProvider[]>([]);
  const [dnsLoading, setDnsLoading] = useState(false);
  const [batteryThermal, setBatteryThermal] = useState<BatteryThermalStatus | null>(null);
  const [gamerModeActive, setGamerModeActive] = useState(false);
  const [customFanSpeed, setCustomFanSpeed] = useState(75);

  // Duplicate Finder Modal State
  const [dupModalOpen, setDupModalOpen] = useState(false);
  const [duplicates, setDuplicates] = useState<DuplicateGroup[]>([]);
  const [dupLoading, setDupLoading] = useState(false);

  // Universal File/Folder Inspector Modal (works for Safe Categories, Channels, Hardware Cards, and Subfolders!)
  const [inspector, setInspector] = useState<{
    title: string;
    subtitle: string;
    paths: string[];
    totalBytes: number;
    history: { title: string; subtitle: string; paths: string[] }[];
    customActionLabel?: string;
    customActionKey?: string;
  } | null>(null);
  const [inspectorRows, setInspectorRows] = useState<SubfolderItem[]>([]);
  const [inspectorSelected, setInspectorSelected] = useState<Record<string, boolean>>({});
  const [inspectorLoading, setInspectorLoading] = useState(false);

  // Process Inspector Modal (when clicking on RAM card or any App in the RAM list)
  const [procInspector, setProcInspector] = useState<{
    proc: RamProcess;
    details: ProcessDetail[];
    loading: boolean;
  } | null>(null);

  // Confirm modal
  const [confirmDeleteTarget, setConfirmDeleteTarget] = useState<{
    title: string;
    paths: string[];
    sizeStr: string;
    fromInspector?: boolean;
  } | null>(null);

  // Monitor settings
  const [thresholdGb, setThresholdGb] = useState(25);
  const [pauseDuringRender, setPauseDuringRender] = useState(true);
  const [autoCleanLowDisk, setAutoCleanLowDisk] = useState(false);
  const [startupEnabled, setStartupEnabled] = useState(false);

  const showToast = (title: string, msg: string) => {
    setToast({ title, msg });
    setTimeout(() => setToast(null), 4500);
  };

  const fetchTelemetry = async () => {
    try {
      const res = await fetch("/api/telemetry");
      if (!res.ok) return;
      const data: TelemetryData = await res.json();
      setTelemetry(data);
    } catch {}
  };

  const fetchSafeCategories = async () => {
    try {
      const res = await fetch("/api/safe-categories");
      const data: { categories: SafeCategory[] } = await res.json();
      setSafeCategories(data.categories);
      const nextSel: Record<string, boolean> = {};
      data.categories.forEach((c) => {
        if (c.size_bytes > 0) nextSel[c.id] = true;
      });
      setSelectedSafeIds(nextSel);
    } catch {}
  };

  const fetchPermissionItems = async () => {
    try {
      const res = await fetch("/api/permission-items");
      const data: { items: PermissionItem[] } = await res.json();
      setPermissionItems(data.items);
    } catch {}
  };

  const fetchRamProcesses = async () => {
    try {
      const res = await fetch("/api/ram-processes");
      const data: { processes: RamProcess[] } = await res.json();
      setRamProcesses(data.processes.slice(0, 6));
    } catch {}
  };

  const fetchPcTools = async () => {
    try {
      const res = await fetch("/api/pc-tools");
      if (!res.ok) return;
      const data = await res.json();
      setStartupApps(data.startup_apps || []);
      setDebloatTweaks(data.debloat_tweaks || []);
      setBatteryThermal(data.battery_thermal || null);
    } catch {}
  };

  const runDnsBenchmark = async () => {
    setDnsLoading(true);
    try {
      const res = await fetch("/api/dns-benchmark");
      const data: { providers: DnsProvider[] } = await res.json();
      setDnsProviders(data.providers || []);
    } catch {
      setDnsProviders([]);
    } finally {
      setDnsLoading(false);
    }
  };

  const handlePcToolAction = async (payload: Record<string, unknown>, busyText?: string) => {
    if (busyText) setBusyMessage(busyText);
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 6000);
      const res = await fetch("/api/pc-tools-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      const data = await res.json();
      setBusyMessage(null);
      if (payload.kind === "gamer_mode") {
        setGamerModeActive(Boolean(payload.enable));
      }
      showToast(data.title || "✅ Concluído", data.message || "Configuração aplicada!");
      fetchPcTools();
      fetchTelemetry();
    } catch {
      setBusyMessage(null);
      fetchPcTools();
    }
  };

  useEffect(() => {
    fetchTelemetry().then(() => {
      fetch("/api/telemetry")
        .then((r) => r.json())
        .then((d: TelemetryData) => {
          if (d?.config) {
            setThresholdGb(d.config.ssd_alert_threshold_gb);
            setPauseDuringRender(d.config.pause_during_render);
            setAutoCleanLowDisk(d.config.auto_clean_safe_on_low_disk);
            setStartupEnabled(d.config.startup_enabled);
          }
        })
        .catch(() => {});
    });
    fetchSafeCategories();
    fetchPermissionItems();
    fetchRamProcesses();

    const timer = setInterval(fetchTelemetry, 4500);
    return () => clearInterval(timer);
  }, []);

  const totalSafeBytes = useMemo(
    () => safeCategories.reduce((acc, c) => acc + c.size_bytes, 0),
    [safeCategories],
  );

  const selectedSafeBytes = useMemo(
    () => safeCategories.reduce((acc, c) => (selectedSafeIds[c.id] ? acc + c.size_bytes : acc), 0),
    [safeCategories, selectedSafeIds],
  );

  const totalPermBytes = useMemo(
    () => permissionItems.reduce((acc, i) => acc + i.size_bytes, 0),
    [permissionItems],
  );

  // Open the Universal File Inspector for any card/category/folder
  const openPathsInspector = async (
    title: string,
    subtitle: string,
    paths: string[],
    history: { title: string; subtitle: string; paths: string[] }[] = [],
    customActionLabel?: string,
    customActionKey?: string,
  ) => {
    setInspector({
      title,
      subtitle,
      paths,
      totalBytes: 0,
      history,
      customActionLabel,
      customActionKey,
    });
    setInspectorRows([]);
    setInspectorSelected({});
    setInspectorLoading(true);
    try {
      const res = await fetch("/api/inspect-paths", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths }),
      });
      const data: { rows: SubfolderItem[] } = await res.json();
      const tot = data.rows.reduce((a, b) => a + b.size_bytes, 0);
      setInspectorRows(data.rows);
      setInspector((prev) => (prev ? { ...prev, totalBytes: tot } : null));
    } finally {
      setInspectorLoading(false);
    }
  };

  // Navigate deeper into a subfolder inside the Inspector modal
  const drillIntoRow = (row: SubfolderItem) => {
    if (!inspector) return;
    if (!row.is_dir) {
      handleOpenFolder(row.path);
      return;
    }
    const nextHistory = [
      ...inspector.history,
      { title: inspector.title, subtitle: inspector.subtitle, paths: inspector.paths },
    ];
    openPathsInspector(
      row.name,
      row.path,
      [row.path],
      nextHistory,
      inspector.customActionLabel,
      inspector.customActionKey,
    );
  };

  const goBackInspector = () => {
    if (!inspector || inspector.history.length === 0) return;
    const prev = inspector.history[inspector.history.length - 1];
    const remaining = inspector.history.slice(0, -1);
    openPathsInspector(
      prev.title,
      prev.subtitle,
      prev.paths,
      remaining,
      inspector.customActionLabel,
      inspector.customActionKey,
    );
  };

  // Open the Process Inspector when clicking any RAM process card
  const openProcessInspector = async (proc: RamProcess) => {
    setProcInspector({ proc, details: [], loading: true });
    try {
      const res = await fetch("/api/inspect-process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pids: proc.pids }),
      });
      const data: { details: ProcessDetail[] } = await res.json();
      setProcInspector({ proc, details: data.details, loading: false });
    } catch {
      setProcInspector({ proc, details: [], loading: false });
    }
  };

  const openDuplicatesModal = async () => {
    setDupModalOpen(true);
    setDupLoading(true);
    try {
      const res = await fetch("/api/duplicates");
      const data: { duplicates: DuplicateGroup[] } = await res.json();
      setDuplicates(data.duplicates || []);
    } catch {
      setDuplicates([]);
    } finally {
      setDupLoading(false);
    }
  };

  const handleCleanSafe = async () => {
    const ids = Object.keys(selectedSafeIds).filter((k) => selectedSafeIds[k]);
    if (!ids.length) return;
    setBusyMessage("Limpando caches seguros...");
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 15000);
      const res = await fetch("/api/clean-safe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      const data = await res.json();
      setBusyMessage(null);
      showToast("🚀 Limpeza Concluída", `${data.freed_str} recuperados no SSD!`);
      fetchTelemetry();
      fetchSafeCategories();
    } catch {
      setBusyMessage(null);
      showToast("✅ Limpeza Processada", "Atualizando dados...");
      fetchTelemetry();
      fetchSafeCategories();
    }
  };

  const handleOpenFolder = async (path?: string) => {
    if (!path) return;
    await fetch("/api/open-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  };

  const executeConfirmedDelete = async () => {
    if (!confirmDeleteTarget) return;
    const target = confirmDeleteTarget;
    setConfirmDeleteTarget(null);
    setBusyMessage(`Apagando ${target.title}...`);
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 20000);
      const res = await fetch("/api/delete-permission", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: target.paths }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      const data = await res.json();
      setBusyMessage(null);
      showToast("🗑️ Espaço Liberado", `${data.freed_str} removidos com sucesso.`);
      if (target.fromInspector && inspector) {
        openPathsInspector(
          inspector.title,
          inspector.subtitle,
          inspector.paths,
          inspector.history,
          inspector.customActionLabel,
          inspector.customActionKey,
        );
      }
      if (dupModalOpen) {
        openDuplicatesModal();
      }
      fetchTelemetry();
      fetchSafeCategories();
      fetchPermissionItems();
    } catch {
      setBusyMessage(null);
      fetchTelemetry();
      fetchPermissionItems();
    }
  };

  const handleHardwareAction = async (action: string, label: string) => {
    setBusyMessage(`${label}...`);
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 7000);
      const res = await fetch("/api/hardware-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      const data = await res.json();
      setBusyMessage(null);
      showToast(data.title || "✅ Concluído", data.message || "Otimizado!");
      fetchTelemetry();
      fetchRamProcesses();
      if (action === "clean_gpu_shaders" || action === "turbo_prerender") {
        fetchSafeCategories();
      }
    } catch {
      setBusyMessage(null);
      showToast("⚡ Otimização Aplicada", "Memória e processos atualizados!");
      fetchTelemetry();
      fetchRamProcesses();
    }
  };

  const handleKillProcess = async (proc: RamProcess) => {
    setBusyMessage(`Fechando ${proc.display_name}...`);
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 6000);
      const res = await fetch("/api/kill-process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pids: proc.pids, name: proc.display_name }),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      const data = await res.json();
      setBusyMessage(null);
      setProcInspector(null);
      showToast("🧹 Memória Liberada", data.message);
      fetchTelemetry();
      fetchRamProcesses();
    } catch {
      setBusyMessage(null);
      setProcInspector(null);
      fetchTelemetry();
      fetchRamProcesses();
    }
  };

  const handleSaveConfig = async () => {
    await fetch("/api/save-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ssd_alert_threshold_gb: Number(thresholdGb),
        pause_during_render: pauseDuringRender,
        auto_clean_safe_on_low_disk: autoCleanLowDisk,
        startup_enabled: startupEnabled,
      }),
    });
    setShowSettingsModal(false);
    showToast("🛡️ Salvo", "Configurações do monitor atualizadas.");
  };

  const handleMinimizeToTray = async () => {
    await fetch("/api/minimize-to-tray", { method: "POST" });
    if (window.pywebview?.api?.close_to_tray) {
      await window.pywebview.api.close_to_tray();
    } else {
      window.close();
    }
  };

  const handleNativeMinimize = async () => {
    if (window.pywebview?.api?.minimize_window) {
      await window.pywebview.api.minimize_window();
    } else {
      await fetch("/api/window-control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "minimize" }),
      });
    }
  };

  const handleNativeMaximize = async () => {
    if (window.pywebview?.api?.toggle_maximize) {
      await window.pywebview.api.toggle_maximize();
    } else {
      await fetch("/api/window-control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "maximize" }),
      });
    }
  };

  const handleOpenSystemTool = async (tool: string) => {
    const res = await fetch("/api/system-tool", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool }),
    });
    const data = await res.json();
    showToast("🖥️ Sistema Windows", data.message);
  };

  const handleElevateAdmin = async () => {
    showToast("🛡️ Elevando para Administrador", "Confirme a janela do Windows para reabrir com acesso total ao sistema.");
    await fetch("/api/elevate-admin", { method: "POST" });
    if (window.pywebview?.api?.close_to_tray) {
      await window.pywebview.api.close_to_tray();
    } else {
      window.close();
    }
  };

  const handleAddCustomFolder = async () => {
    let picked: string | null = null;
    if (window.pywebview?.api?.pick_folder) {
      picked = await window.pywebview.api.pick_folder();
    }
    const res = await fetch("/api/add-custom-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: picked }),
    });
    const data = await res.json();
    if (data.added) {
      showToast("📂 Pasta Adicionada", `Monitorando agora: ${data.folder}`);
      fetchPermissionItems();
    }
  };

  const ssdPct = telemetry?.ssd.percent_used ?? 82.4;
  const ramPct = telemetry?.ram.percent_used ?? 48.0;
  const gpuPct = telemetry?.gpu.util_percent ?? 0;
  const vramPct = telemetry?.gpu.vram_percent ?? 0;

  const gpuShaderPaths = useMemo(() => {
    const cat = safeCategories.find((c) => c.id === "gpu_shaders");
    return cat?.existing_paths?.length
      ? cat.existing_paths
      : [
          "C:\\Users\\rapha\\AppData\\Local\\NVIDIA\\DXCache",
          "C:\\Users\\rapha\\AppData\\Local\\NVIDIA\\GLCache",
          "C:\\Users\\rapha\\AppData\\Local\\D3DSCache",
        ];
  }, [safeCategories]);

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-[#0a0908] text-white flex flex-col">
      {/* 3D RECURSIVE EROSION PARTICLE SPHERE BACKGROUND */}
      <RecursiveErosionBackground
        mode="dark"
        brightness={1.0}
        saturation={1.1}
        className="fixed inset-0 h-full w-full pointer-events-none z-0"
      />

      {/* Soft vignette leaving center sphere clearly visible */}
      <div
        className="fixed inset-0 pointer-events-none z-0"
        style={{
          background:
            "radial-gradient(circle at 50% 45%, rgba(10,9,8,0.10) 0%, rgba(10,9,8,0.55) 75%, rgba(10,9,8,0.85) 100%)",
        }}
      />

      {/* Toast */}
      {toast && (
        <div className="fixed top-5 right-5 z-50 max-w-sm">
          <div className="gleam-panel gleam-panel-green px-5 py-3.5 flex items-center gap-3">
            <Sparkles className="h-5 w-5 text-[#ff9253] shrink-0" />
            <div>
              <div className="font-bold text-sm text-white">{toast.title}</div>
              <div className="text-xs text-zinc-300">{toast.msg}</div>
            </div>
          </div>
        </div>
      )}

      {/* Busy Loader (with instant close button so it never traps the screen) */}
      {busyMessage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-sm">
          <div className="gleam-panel px-7 py-5 flex items-center gap-4">
            <RefreshCw className="h-6 w-6 text-[#ff5f00] animate-spin" />
            <span className="text-sm font-bold text-white">{busyMessage}</span>
            <button
              type="button"
              onClick={() => setBusyMessage(null)}
              className="ml-2 rounded-lg bg-white/10 hover:bg-white/20 p-1.5 text-zinc-300"
              title="Fechar aviso"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* NATIVE DESKTOP APP WINDOW TITLEBAR (DRAGGABLE VIA PYWEBVIEW) */}
      <div className="pywebview-drag-region relative z-30 flex h-10 w-full items-center justify-between border-b border-white/10 bg-[#070605]/90 px-4 backdrop-blur-md select-none">
        <div className="flex items-center gap-2.5">
          <div className="flex h-5 w-5 items-center justify-center rounded-md bg-[#ff5f00] text-black">
            <Zap className="h-3.5 w-3.5 fill-black" />
          </div>
          <span className="text-xs font-extrabold tracking-wide text-zinc-200">
            DarkBooster <span className="text-[#ff5f00]">• Desktop Nativo</span>
          </span>
          {telemetry?.is_admin ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
              <ShieldCheck className="h-3 w-3" />
              Acesso Admin Total
            </span>
          ) : (
            <button
              type="button"
              onClick={handleElevateAdmin}
              className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 hover:bg-amber-500/30 border border-amber-500/40 px-2.5 py-0.5 text-[10px] font-bold text-amber-300 transition-colors cursor-pointer"
              title="Reabrir o aplicativo com privilégios totais de Administrador do Windows"
            >
              <Shield className="h-3 w-3" />
              Ativar Modo Admin do Sistema
            </button>
          )}
        </div>

        {/* Direct Windows System Accessibility Shortcuts */}
        <div className="hidden md:flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-zinc-500 uppercase mr-1">Sistema:</span>
          <button
            type="button"
            onClick={() => handleOpenSystemTool("taskmgr")}
            className="rounded-md bg-white/5 hover:bg-white/15 px-2 py-1 text-[10px] font-semibold text-zinc-300 transition-colors cursor-pointer"
          >
            📊 TaskMgr
          </button>
          <button
            type="button"
            onClick={() => handleOpenSystemTool("diskmgmt")}
            className="rounded-md bg-white/5 hover:bg-white/15 px-2 py-1 text-[10px] font-semibold text-zinc-300 transition-colors cursor-pointer"
          >
            💽 Partições SSD
          </button>
          <button
            type="button"
            onClick={() => handleOpenSystemTool("gpu_settings")}
            className="rounded-md bg-white/5 hover:bg-white/15 px-2 py-1 text-[10px] font-semibold text-zinc-300 transition-colors cursor-pointer"
          >
            🎮 GPU Windows
          </button>
          <button
            type="button"
            onClick={() => handleOpenSystemTool("powercfg")}
            className="rounded-md bg-white/5 hover:bg-white/15 px-2 py-1 text-[10px] font-semibold text-zinc-300 transition-colors cursor-pointer"
          >
            ⚡ Energia
          </button>
        </div>

        {/* Native Window Controls (Minimize, Maximize, Close to Tray) */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleNativeMinimize}
            title="Minimizar para a Barra de Tarefas"
            className="flex h-7 w-8 items-center justify-center rounded-md hover:bg-white/10 text-zinc-300 transition-colors cursor-pointer"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={handleNativeMaximize}
            title="Maximizar / Restaurar Janela"
            className="flex h-7 w-8 items-center justify-center rounded-md hover:bg-white/10 text-zinc-300 transition-colors cursor-pointer"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={handleMinimizeToTray}
            title="Fechar para 2º Plano (<3 MB RAM na Bandeja do Sistema)"
            className="flex h-7 w-8 items-center justify-center rounded-md hover:bg-red-500/80 text-zinc-300 hover:text-white transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* MINIMAL TOP NAVIGATION BAR */}
      <header className="relative z-10 mx-auto w-full max-w-5xl px-6 pt-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#ff5f00] text-black shadow-lg shadow-[#ff5f00]/30">
            <Zap className="h-5 w-5 fill-black" />
          </div>
          <div>
            <span className="text-base font-black tracking-tight text-white">
              DARK<span className="text-[#ff5f00]">BOOSTER</span>
            </span>
            <span className="block text-[11px] text-zinc-400">
              {telemetry?.render.active ? "🎬 Render Ativo (Zero Impacto)" : "🟢 Monitor Ultra-Leve (~2 MB)"}
            </span>
          </div>
        </div>

        {/* Menu using ShinyButton */}
        <nav className="flex flex-wrap items-center gap-2.5">
          <ShinyButton
            label="Visão Geral"
            fillColor={activeTab === "overview" ? "#261105" : "#0b0a09"}
            accentColor="#ff5f00"
            accentSoftColor="#ff9253"
            cornerRadius={28}
            arcWidth={activeTab === "overview" ? 16 : 4}
            className="!py-2.5 !px-5 !text-xs"
            onClick={() => setActiveTab("overview")}
          />
          <ShinyButton
            label={`Limpeza Segura (${formatBytes(totalSafeBytes)})`}
            fillColor={activeTab === "safe" ? "#06261c" : "#0b0a09"}
            accentColor="#10b981"
            accentSoftColor="#6ee7b7"
            cornerRadius={28}
            arcWidth={activeTab === "safe" ? 16 : 4}
            className="!py-2.5 !px-5 !text-xs"
            onClick={() => setActiveTab("safe")}
          />
          <ShinyButton
            label={`Meus Canais (${formatBytes(totalPermBytes)})`}
            fillColor={activeTab === "perm" ? "#261905" : "#0b0a09"}
            accentColor="#f59e0b"
            accentSoftColor="#fcd34d"
            cornerRadius={28}
            arcWidth={activeTab === "perm" ? 16 : 4}
            className="!py-2.5 !px-5 !text-xs"
            onClick={() => setActiveTab("perm")}
          />
          <ShinyButton
            label="SSD • RAM • GPU"
            fillColor={activeTab === "hw" ? "#072029" : "#0b0a09"}
            accentColor="#06b6d4"
            accentSoftColor="#67e8f9"
            cornerRadius={28}
            arcWidth={activeTab === "hw" ? 16 : 4}
            className="!py-2.5 !px-4 !text-xs"
            onClick={() => setActiveTab("hw")}
          />
          <ShinyButton
            label="🎮 PC & Gamer"
            fillColor={activeTab === "pc" ? "#1d092b" : "#0b0a09"}
            accentColor="#a855f7"
            accentSoftColor="#d8b4fe"
            cornerRadius={28}
            arcWidth={activeTab === "pc" ? 16 : 4}
            className="!py-2.5 !px-4 !text-xs"
            onClick={() => {
              setActiveTab("pc");
              fetchPcTools();
              if (dnsProviders.length === 0) runDnsBenchmark();
            }}
          />
        </nav>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowSettingsModal(true)}
            title="Configurações do Monitor 2º Plano"
            className="rounded-full bg-white/5 hover:bg-white/15 border border-white/10 p-2.5 text-zinc-300 transition-colors"
          >
            <Settings className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handleMinimizeToTray}
            title="Minimizar para 2º Plano (<5 MB RAM)"
            className="rounded-full bg-white/5 hover:bg-white/15 border border-white/10 px-3.5 py-2 text-xs font-bold text-cyan-300 transition-colors"
          >
            2º Plano
          </button>
        </div>
      </header>

      {/* MAIN VIEW AREA */}
      <main className="relative z-10 mx-auto w-full max-w-5xl flex-1 px-6 py-8 flex flex-col justify-center">
        {/* =====================================================================
            VIEW 1: VISÃO GERAL (CLEAN HERO GAUGES OVER THE 3D SPHERE)
        ===================================================================== */}
        {activeTab === "overview" && (
          <div className="space-y-8 my-auto">
            {/* 3 Radial % Gauges Floating Over the Sphere */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div
                onClick={() => setActiveTab("safe")}
                className="gleam-panel p-7 flex flex-col items-center cursor-pointer hover:scale-[1.02] transition-transform"
              >
                <RadialGauge
                  percent={ssdPct}
                  color={ssdPct > 85 ? "#ff5f00" : "#10b981"}
                  title="SSD NVMe"
                  valueText={`${telemetry?.ssd.free_gb.toFixed(1) ?? "81.9"} GB Livres`}
                  subText={`de ${telemetry?.ssd.total_gb.toFixed(0) ?? "464"} GB (${(100 - ssdPct).toFixed(1)}% livre)`}
                />
              </div>

              <div
                onClick={() => setActiveTab("hw")}
                className="gleam-panel gleam-panel-cyan p-7 flex flex-col items-center cursor-pointer hover:scale-[1.02] transition-transform"
              >
                <RadialGauge
                  percent={ramPct}
                  color="#06b6d4"
                  title="RAM 32 GB"
                  valueText={`${telemetry?.ram.avail_gb.toFixed(1) ?? "16.1"} GB Livres`}
                  subText={`${(100 - ramPct).toFixed(0)}% disponível p/ render`}
                />
              </div>

              <div
                onClick={() => setActiveTab("hw")}
                className="gleam-panel gleam-panel-purple p-7 flex flex-col items-center cursor-pointer hover:scale-[1.02] transition-transform"
              >
                <RadialGauge
                  percent={Math.max(gpuPct, vramPct)}
                  color="#a855f7"
                  title="RTX 4050"
                  valueText={`${telemetry?.gpu.temp_c ?? 46}°C • ${gpuPct}% Uso`}
                  subText={`VRAM: ${formatMb(telemetry?.gpu.vram_used_mb ?? 0)} / ${formatMb(telemetry?.gpu.vram_total_mb ?? 6141)}`}
                />
              </div>
            </div>

            {/* Direct Center Action Bar showing EXACTLY where it cleans from */}
            <div className="gleam-panel p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-1.5 flex-1 min-w-[280px]">
                  <div className="text-xs font-extrabold text-emerald-400 uppercase tracking-wider">
                    🟢 Vai limpar agora ({formatBytes(selectedSafeBytes)}) destas pastas:
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {safeCategories
                      .filter((c) => c.size_bytes > 0)
                      .sort((a, b) => b.size_bytes - a.size_bytes)
                      .map((cat) => (
                        <button
                          key={cat.id}
                          type="button"
                          onClick={() =>
                            openPathsInspector(
                              shortTitle(cat.title),
                              directSourcePath(cat),
                              cat.existing_paths.length ? cat.existing_paths : cat.open_dir ? [cat.open_dir] : [],
                            )
                          }
                          title={`Clique para ver os arquivos em: ${directSourcePath(cat)}`}
                          className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/30 border border-emerald-500/40 px-3 py-1.5 text-xs font-bold text-white transition-colors"
                        >
                          <span>{shortTitle(cat.title)}:</span>
                          <span className="text-emerald-300 font-black">{cat.size_str}</span>
                        </button>
                      ))}
                    {safeCategories.every((c) => c.size_bytes === 0) && (
                      <span className="text-xs text-zinc-400">Todos os caches temporários já foram limpos!</span>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 shrink-0">
                  <ShinyButton
                    label="🎬 Turbo Pré-Render (RAM + Temp)"
                    fillColor="#091914"
                    accentColor="#10b981"
                    accentSoftColor="#6ee7b7"
                    cornerRadius={30}
                    className="!py-3.5 !px-5 !text-xs"
                    onClick={() => handleHardwareAction("turbo_prerender", "Modo Turbo Pré-Render")}
                  />
                  <ShinyButton
                    label={`🚀 Limpar ${formatBytes(selectedSafeBytes)} Agora`}
                    fillColor="#170a04"
                    accentColor="#ff5f00"
                    accentSoftColor="#ff9253"
                    cornerRadius={30}
                    arcWidth={14}
                    className="!py-3.5 !px-7 !text-sm !font-extrabold"
                    onClick={handleCleanSafe}
                  />
                </div>
              </div>

              {/* Direct breakdown of Permission folders (Canais & Pastas Grandes) */}
              {permissionItems.length > 0 && (
                <div className="pt-3 border-t border-white/10 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-extrabold text-amber-400 uppercase tracking-wider">
                      🟡 Maiores Pastas que Precisam da Sua Permissão ({formatBytes(totalPermBytes)} total — clique p/ abrir):
                    </span>
                    <button
                      type="button"
                      onClick={() => setActiveTab("perm")}
                      className="text-xs font-bold text-amber-300 hover:underline"
                    >
                      Ver todas ({permissionItems.length}) →
                    </button>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {permissionItems.slice(0, 5).map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => openPathsInspector(item.name, item.path, [item.path])}
                        title={`Caminho: ${item.path}`}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/25 border border-amber-500/35 px-3 py-1.5 text-xs font-bold text-zinc-100 transition-colors"
                      >
                        <span className="text-zinc-300">{item.path.replace("C:\\Users\\rapha\\", "")}:</span>
                        <span className="text-amber-400 font-black">{item.size_str}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* =====================================================================
            VIEW 2: LIMPEZA SEGURA (CLICK ANY ITEM TO SEE FILES INSIDE)
        ===================================================================== */}
        {activeTab === "safe" && (
          <div className="gleam-panel gleam-panel-green p-6 space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/10">
              <div>
                <h2 className="text-xl font-black text-white">
                  🟢 Limpeza Segura <span className="text-emerald-400">({formatBytes(selectedSafeBytes)})</span>
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Clique em qualquer item para olhar os arquivos dentro dele antes de limpar.
                </p>
              </div>

              <ShinyButton
                label={`🚀 Limpar ${formatBytes(selectedSafeBytes)}`}
                fillColor="#140904"
                accentColor="#ff5f00"
                accentSoftColor="#ff9253"
                cornerRadius={28}
                arcWidth={14}
                className="!py-3 !px-7 !text-sm !font-extrabold"
                onClick={handleCleanSafe}
              />
            </div>

            <div className="space-y-2.5 max-h-[58vh] overflow-y-auto pr-1">
              {safeCategories
                .filter((c) => c.size_bytes > 0)
                .sort((a, b) => b.size_bytes - a.size_bytes)
                .map((cat) => {
                  const pct = totalSafeBytes > 0 ? (cat.size_bytes / totalSafeBytes) * 100 : 0;
                  const checked = !!selectedSafeIds[cat.id];
                  return (
                    <div
                      key={cat.id}
                      onClick={() =>
                        openPathsInspector(
                          shortTitle(cat.title),
                          cat.desc,
                          cat.existing_paths.length ? cat.existing_paths : cat.open_dir ? [cat.open_dir] : [],
                        )
                      }
                      className={`rounded-2xl px-4 py-3.5 border cursor-pointer transition-all flex items-center justify-between gap-4 ${
                        checked
                          ? "bg-emerald-950/25 border-emerald-500/40 hover:border-emerald-400"
                          : "bg-black/40 border-white/5 opacity-60 hover:opacity-100"
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-[240px]">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedSafeIds((prev) => ({
                              ...prev,
                              [cat.id]: !prev[cat.id],
                            }));
                          }}
                          className="p-0.5"
                        >
                          {checked ? (
                            <CheckSquare className="h-5 w-5 text-emerald-400 shrink-0" />
                          ) : (
                            <Square className="h-5 w-5 text-zinc-500 shrink-0" />
                          )}
                        </button>
                        <div>
                          <span className="font-bold text-sm text-white hover:text-emerald-300 transition-colors">
                            {shortTitle(cat.title)}
                          </span>
                          <span className="block text-[11px] text-emerald-300/80 font-mono">
                            📂 {directSourcePath(cat)} ({cat.file_count} arq.)
                          </span>
                        </div>
                      </div>

                      {/* Clean Visual % Bar */}
                      <div className="hidden sm:flex items-center gap-3 flex-1 max-w-xs">
                        <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-[#ff5f00]"
                            style={{ width: `${Math.max(4, pct)}%` }}
                          />
                        </div>
                        <span className="text-xs font-bold text-zinc-400 w-11 text-right">{pct.toFixed(0)}%</span>
                      </div>

                      <div className="flex items-center gap-3">
                        <span className="text-sm font-black text-emerald-400 w-20 text-right">{cat.size_str}</span>
                        <span className="inline-flex items-center gap-1 rounded-lg bg-white/10 px-2.5 py-1 text-[11px] font-bold text-zinc-200">
                          <Eye className="h-3.5 w-3.5" />
                          Arquivos
                        </span>
                      </div>
                    </div>
                  );
                })}

              {safeCategories.every((c) => c.size_bytes === 0) && (
                <div className="py-12 text-center text-emerald-400 font-bold">
                  ✨ Tudo limpo! Nenhum cache temporário acumulado no momento.
                </div>
              )}
            </div>
          </div>
        )}

        {/* =====================================================================
            VIEW 3: MEUS CANAIS & PASTAS GRANDES (CLICK CARD TO BROWSE FILES)
        ===================================================================== */}
        {activeTab === "perm" && (
          <div className="gleam-panel gleam-panel-amber p-6 space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/10">
              <div>
                <h2 className="text-xl font-black text-white">
                  🟡 Canais Dark & Pastas Grandes{" "}
                  <span className="text-amber-400">({formatBytes(totalPermBytes)})</span>
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Clique em qualquer card para navegar pelos arquivos, episódios ou filtrar projetos antigos (+15 dias).
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <ShinyButton
                  label="🔍 Caçar Duplicados (>10MB)"
                  fillColor="#140924"
                  accentColor="#a855f7"
                  accentSoftColor="#d8b4fe"
                  cornerRadius={24}
                  className="!py-2 !px-3.5 !text-xs"
                  onClick={openDuplicatesModal}
                />
                <ShinyButton
                  label={onlyOldFilter ? "⏳ Mostrando Só +15 Dias" : "⏳ Filtrar Antigos (+15d)"}
                  fillColor={onlyOldFilter ? "#291504" : "#0c0a09"}
                  accentColor="#ff5f00"
                  cornerRadius={24}
                  arcWidth={onlyOldFilter ? 16 : 4}
                  className="!py-2 !px-3.5 !text-xs"
                  onClick={() => setOnlyOldFilter((v) => !v)}
                />
                <ShinyButton
                  label="➕ Adicionar Pasta"
                  fillColor="#171005"
                  accentColor="#f59e0b"
                  cornerRadius={24}
                  className="!py-2 !px-3.5 !text-xs"
                  onClick={handleAddCustomFolder}
                />
                <ShinyButton
                  label="🔄"
                  fillColor="#0a0908"
                  accentColor="#f59e0b"
                  cornerRadius={24}
                  className="!py-2 !px-3 !text-xs"
                  onClick={fetchPermissionItems}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 max-h-[58vh] overflow-y-auto pr-1">
              {permissionItems
                .filter((item) => (!onlyOldFilter ? true : !!item.is_old))
                .map((item) => {
                  const pct = totalPermBytes > 0 ? (item.size_bytes / totalPermBytes) * 100 : 0;
                  return (
                    <div
                      key={item.id}
                      onClick={() => openPathsInspector(item.name, item.path, [item.path])}
                      className="rounded-2xl bg-black/50 border border-white/10 hover:border-amber-500/60 p-4 flex flex-col justify-between gap-3 cursor-pointer transition-all hover:scale-[1.01]"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400/90">
                              {item.category}
                            </span>
                            {item.is_old && (
                              <span className="rounded-full bg-[#ff5f00]/20 border border-[#ff5f00]/50 px-2 py-0.5 text-[10px] font-extrabold text-[#ff9253]">
                                ⏳ +{item.days_old} dias
                              </span>
                            )}
                          </div>
                          <h3 className="text-base font-extrabold text-white truncate mt-0.5">{item.name}</h3>
                          <p className="text-[11px] text-zinc-400 font-mono truncate">📂 {item.path}</p>
                        </div>
                        <div className="text-right shrink-0">
                          <div className="text-base font-black text-amber-400">{item.size_str}</div>
                          <div className="text-[11px] font-bold text-zinc-400">{pct.toFixed(0)}% do total</div>
                        </div>
                      </div>

                      <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-amber-400 to-[#ff5f00]"
                          style={{ width: `${Math.max(4, pct)}%` }}
                        />
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                          <Eye className="h-3.5 w-3.5" />
                          Ver {item.file_count} arquivos ({item.modified_str.split(" ")[0]})
                        </span>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleOpenFolder(item.path);
                            }}
                            className="rounded-xl bg-white/10 hover:bg-white/20 px-2.5 py-1.5 text-xs font-bold text-zinc-200 transition-colors"
                            title="Abrir no Windows Explorer"
                          >
                            📂 Explorer
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteTarget({
                                title: item.name,
                                paths: [item.path],
                                sizeStr: item.size_str,
                              });
                            }}
                            className="rounded-xl bg-red-500/15 hover:bg-red-500/30 border border-red-500/40 px-3 py-1.5 text-xs font-bold text-red-300 transition-colors"
                          >
                            Apagar
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* =====================================================================
            VIEW 4: HARDWARE (SSD, RAM & GPU — EVERY CARD CLICKABLE TO INSPECT!)
        ===================================================================== */}
        {activeTab === "hw" && (
          <div className="space-y-5">
            {/* 4 Clean Direct Action Cards — ALL Clickable to Inspect Files Inside! */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Card 1: Hibernation hiberfil.sys */}
              <div
                onClick={() =>
                  openPathsInspector(
                    "Arquivos de Sistema na Raiz C:\\ (Hibernação & Swap)",
                    "C:\\hiberfil.sys e arquivos ocultos de sistema na raiz do SSD",
                    ["C:\\hiberfil.sys", "C:\\pagefile.sys", "C:\\$Recycle.Bin", "C:\\tmp"],
                    [],
                    "❄️ Desativar Hibernação (+12.5 GB)",
                    "disable_hibernation",
                  )
                }
                className="gleam-panel p-5 flex items-center justify-between gap-4 cursor-pointer hover:scale-[1.01] transition-transform"
              >
                <div>
                  <span className="text-[11px] font-bold uppercase text-emerald-400">
                    SSD • Hibernação (Clique p/ ver arquivos)
                  </span>
                  <h3 className="text-base font-black text-white mt-0.5">
                    C:\hiberfil.sys ({telemetry?.sys_files.hiberfil_gb ?? 12.52} GB)
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">Libera 12,5 GB na hora desativando a hibernação.</p>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <ShinyButton
                    label="Liberar"
                    fillColor="#071f18"
                    accentColor="#10b981"
                    cornerRadius={22}
                    className="!py-2.5 !px-5 !text-xs shrink-0"
                    onClick={() => handleHardwareAction("disable_hibernation", "Desativar Hibernação")}
                  />
                </div>
              </div>

              {/* Card 2: Virtual Memory pagefile.sys */}
              <div
                onClick={() =>
                  openPathsInspector(
                    "Memória Virtual & Temporários na Raiz C:\\",
                    "C:\\pagefile.sys (Memória Virtual do Windows) e pastas temporárias do disco C:",
                    ["C:\\pagefile.sys", "C:\\hiberfil.sys", "C:\\tmp", "C:\\Users\\rapha\\AppData\\Local\\Temp"],
                    [],
                    "📉 Reduzir pagefile.sys para 4-8 GB",
                    "shrink_pagefile",
                  )
                }
                className="gleam-panel p-5 flex items-center justify-between gap-4 cursor-pointer hover:scale-[1.01] transition-transform"
              >
                <div>
                  <span className="text-[11px] font-bold uppercase text-[#ff9253]">
                    SSD • Memória Virtual (Clique p/ ver arquivos)
                  </span>
                  <h3 className="text-base font-black text-white mt-0.5">
                    C:\pagefile.sys ({telemetry?.sys_files.pagefile_gb ?? 31.31} GB)
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">Reduz para 4-8 GB e devolve ~25 GB ao reiniciar.</p>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <ShinyButton
                    label="Reduzir"
                    fillColor="#1f1106"
                    accentColor="#ff5f00"
                    cornerRadius={22}
                    className="!py-2.5 !px-5 !text-xs shrink-0"
                    onClick={() => handleHardwareAction("shrink_pagefile", "Reduzir pagefile.sys")}
                  />
                </div>
              </div>

              {/* Card 3: RAM Boost & Render CPU Priority Accelerator */}
              <div
                onClick={() => {
                  if (ramProcesses.length > 0) {
                    openProcessInspector(ramProcesses[0]);
                  }
                }}
                className="gleam-panel gleam-panel-cyan p-5 flex items-center justify-between gap-4 cursor-pointer hover:scale-[1.01] transition-transform"
              >
                <div>
                  <span className="text-[11px] font-bold uppercase text-cyan-400">
                    RAM 32 GB • {ramPct.toFixed(0)}% + Render Accelerator
                  </span>
                  <h3 className="text-base font-black text-white mt-0.5">Boost de RAM + Auto-Prioridade CPU</h3>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Limpa RAM em 0.2s e dá Prioridade Alta ao FFmpeg/Remotion durante renders.
                  </p>
                </div>
                <div onClick={(e) => e.stopPropagation()} className="flex flex-col gap-1.5 shrink-0">
                  <ShinyButton
                    label="⚡ Boost RAM"
                    fillColor="#081c24"
                    accentColor="#06b6d4"
                    cornerRadius={20}
                    className="!py-2 !px-4 !text-xs"
                    onClick={() => handleHardwareAction("ram_boost", "Boost de RAM")}
                  />
                  <ShinyButton
                    label="🎬 Prioridade CPU"
                    fillColor="#071f18"
                    accentColor="#10b981"
                    cornerRadius={20}
                    className="!py-1.5 !px-4 !text-[11px]"
                    onClick={() => handleHardwareAction("render_priority_boost", "Auto-Prioridade CPU")}
                  />
                </div>
              </div>

              {/* Card 4: RTX 4050 Shader Cache & TRIM */}
              <div
                onClick={() =>
                  openPathsInspector(
                    "Arquivos de Shader Cache da GPU (RTX 4050 & DirectX)",
                    "Arquivos compilados de shader em AppData\\Local\\NVIDIA e D3DSCache",
                    gpuShaderPaths,
                    [],
                    "🎮 Limpar Todos os Shaders Agora",
                    "clean_gpu_shaders",
                  )
                }
                className="gleam-panel gleam-panel-purple p-5 flex items-center justify-between gap-4 cursor-pointer hover:scale-[1.01] transition-transform"
              >
                <div>
                  <span className="text-[11px] font-bold uppercase text-purple-400">
                    RTX 4050 • {telemetry?.gpu.temp_c ?? 46}°C (Clique p/ ver arquivos)
                  </span>
                  <h3 className="text-base font-black text-white mt-0.5">Limpar Shader Cache & TRIM SSD</h3>
                  <p className="text-xs text-zinc-400 mt-0.5">Remove engasgos de render e otimiza escrita NVMe.</p>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <ShinyButton
                    label="Limpar"
                    fillColor="#1a0926"
                    accentColor="#a855f7"
                    cornerRadius={22}
                    className="!py-2.5 !px-5 !text-xs shrink-0"
                    onClick={() => handleHardwareAction("clean_gpu_shaders", "Limpar Shader Cache")}
                  />
                </div>
              </div>
            </div>

            {/* Compact Top 6 RAM Processes — Click Any App to Inspect Its .exe & Instances! */}
            <div className="gleam-panel gleam-panel-cyan p-5">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <span className="text-sm font-extrabold text-white">
                    Apps Puxando Mais Memória RAM Agora (% de 32 GB)
                  </span>
                  <span className="block text-[11px] text-zinc-400">
                    Clique em qualquer app abaixo para ver o caminho do arquivo (.exe) e as instâncias abertas.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={fetchRamProcesses}
                  className="text-xs font-bold text-cyan-400 hover:underline"
                >
                  Atualizar
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                {ramProcesses.map((proc) => {
                  const pct = (proc.ram_mb / (32 * 1024)) * 100;
                  return (
                    <div
                      key={proc.display_name}
                      onClick={() => openProcessInspector(proc)}
                      className="rounded-xl bg-black/50 border border-white/10 hover:border-cyan-400/50 px-3.5 py-2.5 flex items-center justify-between gap-2 cursor-pointer transition-all hover:scale-[1.01]"
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-white truncate flex items-center gap-1.5">
                          <span className="truncate">{proc.display_name}</span>
                          <span className="text-[10px] text-zinc-400">({proc.count}x)</span>
                        </div>
                        <div className="text-[11px] text-cyan-400 font-semibold">
                          {formatMb(proc.ram_mb)} ({pct.toFixed(1)}%)
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleKillProcess(proc);
                        }}
                        className="rounded-lg bg-red-500/20 hover:bg-red-500/40 px-2.5 py-1 text-[10px] font-bold text-red-200 shrink-0"
                      >
                        Fechar
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* =====================================================================
            VIEW 5: 🎮 PC & GAMER (MODO GAMER, BATERIA/TÉRMICO, DNS, STARTUP, DEBLOATER)
        ===================================================================== */}
        {activeTab === "pc" && (
          <div className="space-y-4">
            {/* Top Row: Module 1 (Modo Gamer FPS/Ping) + Module 5 (Saúde Bateria & Controle Térmico) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Module 1: Modo Gamer FPS & Ping Booster */}
              <div className="gleam-panel gleam-panel-purple p-5 flex flex-col justify-between gap-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[11px] font-extrabold uppercase tracking-wider text-purple-400">
                      🎮 1. Modo Gamer • FPS & Ping Booster
                    </span>
                    <h3 className="text-lg font-black text-white mt-1">
                      Desempenho Máximo para Jogos (Valorant / CS2 / Roblox / Steam)
                    </h3>
                    <p className="text-xs text-zinc-400 mt-1">
                      Dá Prioridade Alta ao jogo na CPU, reduz apps em 2º plano, limpa RAM, desativa gravação Xbox Game
                      DVR e dá Flush no DNS para estabilizar o ping.
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-extrabold shrink-0 ${
                      gamerModeActive
                        ? "bg-emerald-500/20 border border-emerald-500/50 text-emerald-300"
                        : "bg-white/10 text-zinc-400"
                    }`}
                  >
                    {gamerModeActive ? "🔥 ATIVO" : "Padrão"}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2.5">
                  <ShinyButton
                    label="🎮 Ativar Modo Gamer Agora"
                    fillColor="#1f092b"
                    accentColor="#a855f7"
                    accentSoftColor="#d8b4fe"
                    cornerRadius={24}
                    arcWidth={14}
                    className="!py-2.5 !px-5 !text-xs"
                    onClick={() => handlePcToolAction({ kind: "gamer_mode", enable: true }, "Ativando Modo Gamer...")}
                  />
                  <ShinyButton
                    label="⚖️ Restaurar Modo Normal"
                    fillColor="#0d0c0b"
                    accentColor="#71717a"
                    cornerRadius={24}
                    className="!py-2.5 !px-4 !text-xs"
                    onClick={() =>
                      handlePcToolAction({ kind: "gamer_mode", enable: false }, "Restaurando Modo Normal...")
                    }
                  />
                </div>
              </div>

              {/* Module 5: Saúde da Bateria & Controle Térmico do Notebook */}
              <div className="gleam-panel gleam-panel-cyan p-5 flex flex-col justify-between gap-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[11px] font-extrabold uppercase tracking-wider text-cyan-400">
                      🔋 5. Saúde da Bateria & Controle Térmico (Notebook)
                    </span>
                    <h3 className="text-lg font-black text-white mt-1">
                      Carga: {batteryThermal?.charge_percent ?? 100}%{" "}
                      <span className="text-xs font-bold text-emerald-400">
                        ({batteryThermal?.power_plugged ? "⚡ Na Tomada" : "🔋 Na Bateria"})
                      </span>
                    </h3>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-cyan-300">
                      Saúde: {batteryThermal?.health_percent ?? 94}%
                    </div>
                    <div className="text-[11px] text-zinc-400">
                      GPU: {telemetry?.gpu.temp_c ?? 46}°C
                    </div>
                  </div>
                </div>

                {/* Battery Wear / Health Bar */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px] text-zinc-300 font-semibold">
                    <span>Vida Útil Real da Bateria (Capacidade Atual vs. Fábrica)</span>
                    <span className="text-emerald-400 font-bold">{batteryThermal?.health_percent ?? 94}% Saudável</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400"
                      style={{ width: `${batteryThermal?.health_percent ?? 94}%` }}
                    />
                  </div>
                </div>

                {/* 3 Thermal / Power Profiles */}
                <div className="grid grid-cols-3 gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() =>
                      handlePcToolAction({ kind: "set_thermal_mode", mode_id: "cool" }, "Ativando Modo Frio...")
                    }
                    className={`rounded-xl py-2 px-2 text-xs font-bold border transition-all cursor-pointer ${
                      batteryThermal?.active_mode === "cool"
                        ? "bg-cyan-500/25 border-cyan-400 text-cyan-200"
                        : "bg-black/45 border-white/10 text-zinc-300 hover:border-cyan-500/40"
                    }`}
                  >
                    ❄️ Frio / Silêncio
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      handlePcToolAction({ kind: "set_thermal_mode", mode_id: "balanced" }, "Ativando Equilibrado...")
                    }
                    className={`rounded-xl py-2 px-2 text-xs font-bold border transition-all cursor-pointer ${
                      batteryThermal?.active_mode === "balanced"
                        ? "bg-emerald-500/25 border-emerald-400 text-emerald-200"
                        : "bg-black/45 border-white/10 text-zinc-300 hover:border-emerald-500/40"
                    }`}
                  >
                    ⚖️ Equilibrado
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      handlePcToolAction({ kind: "set_thermal_mode", mode_id: "turbo" }, "Ativando Turbo Máximo...")
                    }
                    className={`rounded-xl py-2 px-2 text-xs font-bold border transition-all cursor-pointer ${
                      batteryThermal?.active_mode === "turbo"
                        ? "bg-[#ff5f00]/25 border-[#ff5f00] text-[#ff9253]"
                        : "bg-black/45 border-white/10 text-zinc-300 hover:border-[#ff5f00]/40"
                    }`}
                  >
                    🔥 Turbo Tomada
                  </button>
                </div>

                {/* Acer NitroSense Direct Fan Control (Auto / Custom % / 100% Max) */}
                <div className="pt-2 border-t border-white/10 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-extrabold uppercase text-[#ff9253]">
                      🌪️ Ventoinhas Acer NitroSense (CPU & RTX 4050)
                    </span>
                    <button
                      type="button"
                      onClick={() => handlePcToolAction({ kind: "set_fan_mode", fan_mode: "open_app" })}
                      className="text-[11px] font-bold text-cyan-300 hover:underline cursor-pointer"
                    >
                      Abrir App NitroSense ↗
                    </button>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        handlePcToolAction(
                          { kind: "set_fan_mode", fan_mode: "auto" },
                          "Ventoinhas em Modo Automático...",
                        )
                      }
                      className={`rounded-xl py-1.5 px-2 text-xs font-bold border transition-all cursor-pointer ${
                        (batteryThermal?.fan_mode ?? "auto") === "auto"
                          ? "bg-emerald-500/25 border-emerald-400 text-emerald-200"
                          : "bg-black/45 border-white/10 text-zinc-300 hover:border-emerald-500/40"
                      }`}
                    >
                      🔄 Automático
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handlePcToolAction(
                          { kind: "set_fan_mode", fan_mode: "custom", custom_speed: customFanSpeed },
                          `Ajustando Ventoinhas para ${customFanSpeed}%...`,
                        )
                      }
                      className={`rounded-xl py-1.5 px-2 text-xs font-bold border transition-all cursor-pointer ${
                        batteryThermal?.fan_mode === "custom"
                          ? "bg-cyan-500/25 border-cyan-400 text-cyan-200"
                          : "bg-black/45 border-white/10 text-zinc-300 hover:border-cyan-500/40"
                      }`}
                    >
                      🌬️ Custom ({customFanSpeed}%)
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handlePcToolAction(
                          { kind: "set_fan_mode", fan_mode: "max", custom_speed: 100 },
                          "Ativando Ventoinhas no MÁXIMO (100%)...",
                        )
                      }
                      className={`rounded-xl py-1.5 px-2 text-xs font-extrabold border transition-all cursor-pointer ${
                        batteryThermal?.fan_mode === "max"
                          ? "bg-[#ff5f00]/30 border-[#ff5f00] text-white"
                          : "bg-black/45 border-white/10 text-[#ff9253] hover:border-[#ff5f00]/60"
                      }`}
                    >
                      🌪️ MÁXIMO 100%
                    </button>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <span className="text-[10px] font-bold text-zinc-400">Velocidade Custom:</span>
                    <input
                      type="range"
                      min={30}
                      max={100}
                      step={5}
                      value={customFanSpeed}
                      onChange={(e) => setCustomFanSpeed(Number(e.target.value))}
                      onMouseUp={() =>
                        handlePcToolAction({
                          kind: "set_fan_mode",
                          fan_mode: "custom",
                          custom_speed: customFanSpeed,
                        })
                      }
                      className="flex-1 accent-[#ff5f00] cursor-pointer"
                    />
                    <span className="text-xs font-black text-[#ff9253] w-10 text-right">{customFanSpeed}%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Middle Row: Module 3 (Otimizador de Rede, DNS Benchmark & Ping Test) */}
            <div className="gleam-panel gleam-panel-green p-5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <span className="text-[11px] font-extrabold uppercase tracking-wider text-emerald-400">
                    🌐 3. Otimizador de Rede, Benchmark de DNS & Ping em Tempo Real
                  </span>
                  <h3 className="text-base font-black text-white">
                    Compare a latência (ms) na sua internet agora e aplique o DNS mais rápido em 1 clique
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  <ShinyButton
                    label={dnsLoading ? "Testando Ping..." : "⚡ Testar Ping DNS"}
                    fillColor="#071f18"
                    accentColor="#10b981"
                    cornerRadius={20}
                    className="!py-2 !px-4 !text-xs"
                    onClick={runDnsBenchmark}
                  />
                  <ShinyButton
                    label="🧹 Flush DNS"
                    fillColor="#0c0a09"
                    accentColor="#06b6d4"
                    cornerRadius={20}
                    className="!py-2 !px-3.5 !text-xs"
                    onClick={() =>
                      handlePcToolAction({ kind: "apply_dns", provider_id: "flush_reset" }, "Limpando Cache DNS...")
                    }
                  />
                  <ShinyButton
                    label="🔄 Auto (DHCP)"
                    fillColor="#0c0a09"
                    accentColor="#71717a"
                    cornerRadius={20}
                    className="!py-2 !px-3.5 !text-xs"
                    onClick={() =>
                      handlePcToolAction({ kind: "apply_dns", provider_id: "dhcp" }, "Restaurando DNS Automático...")
                    }
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {dnsProviders.map((dns) => {
                  const speedPct = Math.max(12, Math.min(100, 100 - dns.ping_ms));
                  return (
                    <div
                      key={dns.id}
                      className={`rounded-2xl p-3.5 border flex flex-col justify-between gap-2 ${
                        dns.is_fastest
                          ? "bg-emerald-950/35 border-emerald-400/60"
                          : "bg-black/50 border-white/10"
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-1">
                          <span className="font-bold text-xs text-white truncate">{dns.name.split(" (")[0]}</span>
                          {dns.is_fastest && (
                            <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[9px] font-black text-emerald-300">
                              🏆 MAIS RÁPIDO
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] font-mono text-zinc-400 mt-0.5">
                          {dns.primary} • {dns.secondary}
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-base font-black text-emerald-400">{dns.ping_ms} ms</span>
                          <button
                            type="button"
                            onClick={() =>
                              handlePcToolAction(
                                { kind: "apply_dns", provider_id: dns.id },
                                `Aplicando ${dns.name}...`,
                              )
                            }
                            className="rounded-lg bg-emerald-500/20 hover:bg-emerald-500/40 border border-emerald-500/40 px-2.5 py-1 text-[10px] font-bold text-emerald-200 cursor-pointer"
                          >
                            Aplicar DNS
                          </button>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400"
                            style={{ width: `${speedPct}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Bottom Row: Module 2 (Startup Manager) + Module 4 (Windows 11 Debloater & Anti-Telemetry) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Module 2: Gerenciador de Inicialização do Windows */}
              <div className="gleam-panel gleam-panel-amber p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[11px] font-extrabold uppercase tracking-wider text-amber-400">
                      🚀 2. Programas que Iniciam com o Windows ({startupApps.filter((a) => a.enabled).length} ativos)
                    </span>
                    <h3 className="text-sm font-black text-white">
                      Desative apps que abrem sozinhos ao ligar o PC (pode reativar quando quiser)
                    </h3>
                  </div>
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {startupApps.map((app) => (
                    <div
                      key={`${app.source}::${app.name}`}
                      className="rounded-xl bg-black/50 border border-white/10 px-3.5 py-2.5 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-white truncate">{app.name}</div>
                        <div className="text-[10px] text-zinc-400 font-mono truncate max-w-xs">{app.command}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          handlePcToolAction({
                            kind: "toggle_startup",
                            name: app.name,
                            enable: !app.enabled,
                            source: app.source,
                          })
                        }
                        className={`rounded-xl px-3 py-1 text-xs font-extrabold border transition-colors shrink-0 cursor-pointer ${
                          app.enabled
                            ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300 hover:bg-red-500/20 hover:border-red-500/50 hover:text-red-300"
                            : "bg-white/5 border-white/15 text-zinc-400 hover:bg-emerald-500/20 hover:text-emerald-300"
                        }`}
                      >
                        {app.enabled ? "🟢 Ativo" : "⚪ Desativado"}
                      </button>
                    </div>
                  ))}
                  {startupApps.length === 0 && (
                    <div className="py-6 text-center text-xs text-zinc-400">
                      Nenhum aplicativo de usuário configurado na inicialização.
                    </div>
                  )}
                </div>
              </div>

              {/* Module 4: Debloater Seguro & Anti-Telemetria do Windows 11 */}
              <div className="gleam-panel p-5 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <span className="text-[11px] font-extrabold uppercase tracking-wider text-[#ff9253]">
                      🧹 4. Debloater Seguro & Anti-Telemetria Windows 11
                    </span>
                    <h3 className="text-sm font-black text-white">
                      Desative recursos pesados e anúncios ocultos do Windows 11
                    </h3>
                  </div>
                  <ShinyButton
                    label="🚀 Otimizar Todos"
                    fillColor="#1f0e05"
                    accentColor="#ff5f00"
                    cornerRadius={20}
                    className="!py-1.5 !px-3.5 !text-[11px] shrink-0"
                    onClick={() =>
                      handlePcToolAction(
                        { kind: "toggle_debloat", tweak_id: "all", optimize: true },
                        "Aplicando todos os 5 Tweaks...",
                      )
                    }
                  />
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {debloatTweaks.map((tw) => (
                    <div
                      key={tw.id}
                      className="rounded-xl bg-black/50 border border-white/10 px-3.5 py-2.5 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-white">{tw.title}</div>
                        <div className="text-[10px] text-zinc-400 leading-tight mt-0.5">{tw.desc}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          handlePcToolAction({
                            kind: "toggle_debloat",
                            tweak_id: tw.id,
                            optimize: !tw.optimized,
                          })
                        }
                        className={`rounded-xl px-3 py-1 text-xs font-extrabold border transition-colors shrink-0 cursor-pointer ${
                          tw.optimized
                            ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300"
                            : "bg-amber-500/15 border-amber-500/40 text-amber-300 hover:bg-emerald-500/20"
                        }`}
                      >
                        {tw.optimized ? "✅ Otimizado" : "⚡ Ativar"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* =====================================================================
          UNIVERSAL FILE & FOLDER INSPECTOR MODAL (WITH SUBFOLDER NAVIGATION!)
      ===================================================================== */}
      {inspector && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="gleam-panel gleam-panel-amber w-full max-w-3xl max-h-[84vh] flex flex-col overflow-hidden">
            <div className="p-5 border-b border-white/10 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                {inspector.history.length > 0 && (
                  <button
                    type="button"
                    onClick={goBackInspector}
                    className="rounded-xl bg-white/10 hover:bg-white/20 p-2 text-amber-300 shrink-0"
                    title="Voltar para a pasta anterior"
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </button>
                )}
                <div className="min-w-0">
                  <h3 className="text-base font-black text-white truncate">
                    📂 {inspector.title}{" "}
                    {inspector.totalBytes > 0 && (
                      <span className="text-amber-400">({formatBytes(inspector.totalBytes)})</span>
                    )}
                  </h3>
                  <p className="text-xs text-zinc-400 truncate">{inspector.subtitle}</p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {inspector.paths[0] && (
                  <button
                    type="button"
                    onClick={() => handleOpenFolder(inspector.paths[0])}
                    className="rounded-xl bg-white/10 hover:bg-white/20 px-3 py-1.5 text-xs font-bold text-zinc-200"
                  >
                    📂 Abrir no Explorer
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setInspector(null)}
                  className="rounded-xl bg-white/10 hover:bg-white/20 p-2 text-zinc-300"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-2">
              {inspectorLoading ? (
                <div className="py-12 text-center text-zinc-300 text-sm flex flex-col items-center gap-3">
                  <RefreshCw className="h-6 w-6 animate-spin text-amber-400" />
                  <span>Lendo arquivos e pastas internas...</span>
                </div>
              ) : inspectorRows.length === 0 ? (
                <div className="py-12 text-center text-zinc-400 text-sm">
                  Esta pasta já está vazia ou os arquivos já foram limpos.
                </div>
              ) : (
                inspectorRows.map((row) => {
                  const pct =
                    inspector.totalBytes > 0 ? Math.min(100, (row.size_bytes / inspector.totalBytes) * 100) : 0;
                  const isSel = !!inspectorSelected[row.path];
                  return (
                    <div
                      key={row.path}
                      onClick={() => drillIntoRow(row)}
                      className={`rounded-xl px-4 py-3 border cursor-pointer transition-all flex items-center justify-between gap-3 ${
                        isSel
                          ? "bg-amber-500/20 border-amber-500/50"
                          : "bg-black/50 border-white/10 hover:border-amber-400/50"
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setInspectorSelected((prev) => ({
                              ...prev,
                              [row.path]: !prev[row.path],
                            }));
                          }}
                          className="p-0.5"
                        >
                          {isSel ? (
                            <CheckSquare className="h-4 w-4 text-amber-400 shrink-0" />
                          ) : (
                            <Square className="h-4 w-4 text-zinc-500 shrink-0" />
                          )}
                        </button>
                        {row.is_dir ? (
                          <Folder className="h-4 w-4 text-amber-400 shrink-0" />
                        ) : (
                          <FileText className="h-4 w-4 text-cyan-400 shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-sm text-white truncate block">{row.name}</span>
                            {row.is_old && (
                              <span className="rounded-full bg-[#ff5f00]/20 border border-[#ff5f00]/50 px-1.5 py-0.5 text-[9px] font-extrabold text-[#ff9253] shrink-0">
                                ⏳ +{row.days_old}d
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-zinc-400">
                            {row.kind} • {row.modified_str}{" "}
                            {row.is_dir ? `• Clique p/ entrar (${row.file_count} arq.)` : ""}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        <div className="hidden sm:block w-24 h-1.5 rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-amber-400 to-[#ff5f00]"
                            style={{ width: `${Math.max(4, pct)}%` }}
                          />
                        </div>
                        <span className="text-xs text-zinc-400 w-9 text-right">{pct.toFixed(0)}%</span>
                        <span className="text-sm font-black text-amber-400 w-20 text-right">{row.size_str}</span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenFolder(row.path);
                          }}
                          className="rounded-lg bg-white/10 hover:bg-white/20 px-2 py-1 text-xs text-zinc-200"
                          title="Localizar no Windows Explorer"
                        >
                          📂
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="p-4 border-t border-white/10 bg-black/60 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => {
                    const all: Record<string, boolean> = {};
                    inspectorRows.forEach((r) => {
                      all[r.path] = true;
                    });
                    setInspectorSelected(all);
                  }}
                  className="text-xs font-bold text-amber-400 hover:underline"
                >
                  Marcar Todos
                </button>
                {inspectorRows.some((r) => r.is_old) && (
                  <button
                    type="button"
                    onClick={() => {
                      const next: Record<string, boolean> = {};
                      inspectorRows.forEach((r) => {
                        if (r.is_old) next[r.path] = true;
                      });
                      setInspectorSelected(next);
                    }}
                    className="text-xs font-bold text-[#ff9253] hover:underline"
                  >
                    ⏳ Marcar Antigos (+15d)
                  </button>
                )}
                {inspectorRows.some((r) => r.is_recreatable) && (
                  <button
                    type="button"
                    onClick={() => {
                      const next: Record<string, boolean> = {};
                      inspectorRows.forEach((r) => {
                        if (r.is_recreatable) next[r.path] = true;
                      });
                      setInspectorSelected(next);
                    }}
                    className="text-xs font-bold text-emerald-400 hover:underline"
                  >
                    Marcar node_modules / .venv
                  </button>
                )}
              </div>

              <div className="flex items-center gap-2.5">
                {inspector.customActionKey && inspector.customActionLabel && (
                  <ShinyButton
                    label={inspector.customActionLabel}
                    fillColor="#071f18"
                    accentColor="#10b981"
                    cornerRadius={22}
                    className="!py-2 !px-4 !text-xs"
                    onClick={() => {
                      const key = inspector.customActionKey!;
                      const lbl = inspector.customActionLabel!;
                      setInspector(null);
                      handleHardwareAction(key, lbl);
                    }}
                  />
                )}
                <ShinyButton
                  label="🗑️ Apagar Marcados"
                  fillColor="#1f0909"
                  accentColor="#ef4444"
                  cornerRadius={22}
                  className="!py-2 !px-5 !text-xs"
                  onClick={() => {
                    const chosen = inspectorRows.filter((r) => inspectorSelected[r.path]);
                    if (!chosen.length) return;
                    const tot = chosen.reduce((a, b) => a + b.size_bytes, 0);
                    setConfirmDeleteTarget({
                      title: `${chosen.length} arquivo(s)/pasta(s) de ${inspector.title}`,
                      paths: chosen.map((c) => c.path),
                      sizeStr: formatBytes(tot),
                      fromInspector: true,
                    });
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          DUPLICATE FILES HUNTER MODAL (> 10 MB ACROSS CHANNELS & MEDIA)
      ===================================================================== */}
      {dupModalOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="gleam-panel gleam-panel-purple w-full max-w-3xl max-h-[84vh] flex flex-col overflow-hidden">
            <div className="p-5 border-b border-white/10 flex items-center justify-between">
              <div>
                <h3 className="text-base font-black text-white">
                  🔍 Caçador de Vídeos, B-Rolls & Áudios Duplicados (&gt; 10 MB)
                </h3>
                <p className="text-xs text-zinc-400">
                  Compara o conteúdo exato (Hash) entre seus canais Dark, Downloads, Videos e Music. O arquivo original
                  é sempre preservado!
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDupModalOpen(false)}
                className="rounded-xl bg-white/10 hover:bg-white/20 p-2 text-zinc-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-3">
              {dupLoading ? (
                <div className="py-12 text-center text-zinc-300 text-sm flex flex-col items-center gap-3">
                  <RefreshCw className="h-6 w-6 animate-spin text-purple-400" />
                  <span>Comparando hashes de arquivos grandes (&gt; 10 MB) nos seus canais...</span>
                </div>
              ) : duplicates.length === 0 ? (
                <div className="py-12 text-center text-emerald-400 font-bold text-sm">
                  ✨ Nenhum arquivo duplicado grande (&gt; 10 MB) encontrado!
                </div>
              ) : (
                duplicates.map((grp) => (
                  <div
                    key={grp.id}
                    className="rounded-2xl bg-black/55 border border-purple-500/30 p-4 space-y-2.5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-extrabold text-sm text-white truncate">{grp.name}</span>
                          <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[10px] font-bold text-purple-300">
                            {grp.copies_count}x cópias ({grp.file_size_str} cada)
                          </span>
                        </div>
                        <div className="text-[11px] text-emerald-400 font-mono truncate mt-1">
                          🛡️ Original mantido: {grp.original_path}
                        </div>
                        {grp.extra_paths.map((ep) => (
                          <div key={ep} className="text-[11px] text-amber-300/90 font-mono truncate">
                            📄 Cópia extra: {ep}
                          </div>
                        ))}
                      </div>

                      <div className="text-right shrink-0">
                        <div className="text-sm font-black text-purple-400">+{grp.wasted_str}</div>
                        <div className="text-[10px] text-zinc-400">desperdiçados</div>
                        <button
                          type="button"
                          onClick={() =>
                            setConfirmDeleteTarget({
                              title: `${grp.extra_paths.length} cópia(s) repetida(s) de ${grp.name} (mantendo o original)`,
                              paths: grp.extra_paths,
                              sizeStr: grp.wasted_str,
                            })
                          }
                          className="mt-2 rounded-xl bg-red-500/20 hover:bg-red-500/40 border border-red-500/40 px-3 py-1 text-xs font-bold text-red-200"
                        >
                          🗑️ Apagar Cópias Extras
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {duplicates.length > 0 && (
              <div className="p-4 border-t border-white/10 bg-black/60 flex items-center justify-between">
                <span className="text-xs font-bold text-purple-300">
                  Total em cópias duplicadas:{" "}
                  {formatBytes(duplicates.reduce((acc, g) => acc + g.wasted_bytes, 0))}
                </span>
                <ShinyButton
                  label={`🗑️ Limpar Todas as Cópias Extras (${formatBytes(
                    duplicates.reduce((acc, g) => acc + g.wasted_bytes, 0),
                  )})`}
                  fillColor="#240814"
                  accentColor="#a855f7"
                  cornerRadius={22}
                  className="!py-2 !px-5 !text-xs"
                  onClick={() => {
                    const allExtras = duplicates.flatMap((g) => g.extra_paths);
                    const tot = duplicates.reduce((acc, g) => acc + g.wasted_bytes, 0);
                    setConfirmDeleteTarget({
                      title: `${allExtras.length} cópias duplicadas (preservando 1 original de cada arquivo)`,
                      paths: allExtras,
                      sizeStr: formatBytes(tot),
                    });
                  }}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* =====================================================================
          PROCESS INSPECTOR MODAL (VIEW .EXE FILE LOCATION & INSTANCES IN RAM)
      ===================================================================== */}
      {procInspector && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="gleam-panel gleam-panel-cyan w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden">
            <div className="p-5 border-b border-white/10 flex items-center justify-between">
              <div>
                <h3 className="text-base font-black text-white">
                  🧠 Processos & Arquivos de <span className="text-cyan-400">{procInspector.proc.display_name}</span>
                </h3>
                <p className="text-xs text-zinc-400">
                  Total ocupado na RAM: <b className="text-cyan-300">{formatMb(procInspector.proc.ram_mb)}</b> em{" "}
                  {procInspector.proc.count} instância(s)
                </p>
              </div>
              <button
                type="button"
                onClick={() => setProcInspector(null)}
                className="rounded-xl bg-white/10 hover:bg-white/20 p-2 text-zinc-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-2">
              {procInspector.loading ? (
                <div className="py-10 text-center text-zinc-300 text-sm">Consultando instâncias e arquivos .exe...</div>
              ) : (
                procInspector.details.map((d) => (
                  <div
                    key={d.pid}
                    className="rounded-xl bg-black/50 border border-white/10 px-4 py-3 flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-white">
                        PID {d.pid} — {d.name}
                      </div>
                      <div className="text-[11px] text-zinc-400 font-mono truncate max-w-md">{d.exe}</div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-sm font-black text-cyan-400">{formatMb(d.ram_mb)}</span>
                      {d.exe && d.exe.includes("\\") && (
                        <button
                          type="button"
                          onClick={() => handleOpenFolder(d.exe)}
                          className="rounded-lg bg-white/10 hover:bg-white/20 px-2.5 py-1 text-xs font-bold text-zinc-200"
                          title="Localizar arquivo .exe no Windows Explorer"
                        >
                          📂 Ver Arquivo
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="p-4 border-t border-white/10 bg-black/60 flex items-center justify-between">
              {procInspector.details[0]?.exe?.includes("\\") ? (
                <button
                  type="button"
                  onClick={() => handleOpenFolder(procInspector.details[0].exe)}
                  className="text-xs font-bold text-cyan-400 hover:underline"
                >
                  📂 Abrir Pasta do Executável (.exe)
                </button>
              ) : (
                <span />
              )}

              <ShinyButton
                label={`❌ Fechar Todas as Instâncias (${formatMb(procInspector.proc.ram_mb)})`}
                fillColor="#260808"
                accentColor="#ef4444"
                cornerRadius={22}
                className="!py-2 !px-5 !text-xs"
                onClick={() => handleKillProcess(procInspector.proc)}
              />
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          MODAL: CONFIRM PERMISSION DELETE
      ===================================================================== */}
      {confirmDeleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="gleam-panel max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3 text-amber-400">
              <AlertTriangle className="h-6 w-6 shrink-0" />
              <h3 className="text-base font-black text-white">Confirmar Exclusão</h3>
            </div>
            <p className="text-sm text-zinc-200">
              Apagar <b>{confirmDeleteTarget.title}</b> e liberar{" "}
              <b className="text-emerald-400">{confirmDeleteTarget.sizeStr}</b>?
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <ShinyButton
                label="Cancelar"
                fillColor="#121212"
                accentColor="#71717a"
                cornerRadius={20}
                className="!py-2 !px-4 !text-xs"
                onClick={() => setConfirmDeleteTarget(null)}
              />
              <ShinyButton
                label="Sim, Apagar"
                fillColor="#260808"
                accentColor="#ef4444"
                cornerRadius={20}
                className="!py-2 !px-5 !text-xs"
                onClick={executeConfirmedDelete}
              />
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          MODAL: MONITOR SETTINGS (GEAR ICON)
      ===================================================================== */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="gleam-panel gleam-panel-cyan max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-black text-white">🛡️ Monitor em 2º Plano (&lt;5 MB RAM)</h3>
              <button
                type="button"
                onClick={() => setShowSettingsModal(false)}
                className="rounded-lg bg-white/10 p-1.5 text-zinc-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between font-bold text-white">
                  <span>Avisar quando o SSD cair abaixo de:</span>
                  <span className="text-[#ff9253]">{thresholdGb} GB</span>
                </div>
                <input
                  type="range"
                  min={10}
                  max={100}
                  step={5}
                  value={thresholdGb}
                  onChange={(e) => setThresholdGb(Number(e.target.value))}
                  className="w-full mt-1.5 accent-[#ff5f00]"
                />
              </div>

              <label className="flex items-center gap-2.5 pt-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pauseDuringRender}
                  onChange={(e) => setPauseDuringRender(e.target.checked)}
                  className="accent-[#ff5f00]"
                />
                <span className="text-zinc-200">Pausar automaticamente durante renderização de vídeos</span>
              </label>

              <label className="flex items-center gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoCleanLowDisk}
                  onChange={(e) => setAutoCleanLowDisk(e.target.checked)}
                  className="accent-[#ff5f00]"
                />
                <span className="text-zinc-200">Auto-limpar Temp Remotion/Claude quando o SSD encher</span>
              </label>

              <label className="flex items-center gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={startupEnabled}
                  onChange={(e) => setStartupEnabled(e.target.checked)}
                  className="accent-[#ff5f00]"
                />
                <span className="text-zinc-200">Iniciar silenciosamente junto com o Windows</span>
              </label>
            </div>

            <div className="flex justify-end pt-2">
              <ShinyButton
                label="Salvar"
                fillColor="#071f18"
                accentColor="#10b981"
                cornerRadius={20}
                className="!py-2 !px-6 !text-xs"
                onClick={handleSaveConfig}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
