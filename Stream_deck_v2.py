"""
Stream Deck v8 — Constructor visual de macros
─────────────────────────────────────────────
Bloque B — Nuevos tipos de acción:
  • macro   : secuencia de acciones con delay configurable
  • toggle  : alterna entre dos acciones (ON/OFF)
  • confirm : pide confirmación antes de ejecutar
  • script  : ejecuta un script Python con salida visible
  • api     : hace petición HTTP GET/POST a una URL (webhook)

Bloque C — Sistema y UX:
  • Atajos de teclado globales (Ctrl+1…Ctrl+9, configurables)
  • Minimizar a bandeja del sistema (system tray)
  • Notificación toast al ejecutar
  • Reordenar botones con clic derecho → Mover

Bloque D — Avanzado:
  • Contador de usos por botón con historial del día
  • Acción programada (scheduler) por hora
  • Exportar / importar perfil como JSON

Arquitectura mantenida: widget pool, cero recreación en acciones normales.

v12.1 — Optimizaciones de rendimiento:
  • save_all() con debounce — escribe a disco máx cada 800ms
  • Stats cacheados en RAM — flush cada 30s o al cerrar
  • Widget pool en MacroBuilder (elimina destroy/recreate)
  • _paint_grid solo repinta slots que cambiaron
  • Editor no actualiza tabs ocultos
  • trace_add con debounce en MacroBuilder
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, colorchooser
import subprocess, webbrowser, os, time, json, threading, copy, datetime, sched
import pyperclip, requests as _requests_mod
from PIL import Image, ImageTk

try:
    import pystray
    from pystray import MenuItem as TrayItem
    pystray.Icon
    PIL_ICON = True
except Exception:
    PIL_ICON = False

try:
    import plyer
    PLYER_OK = True
except ImportError:
    PLYER_OK = False

try:
    from pynput import mouse as _pynput_mouse, keyboard as _pynput_kb
    PYNPUT_OK = True
except ImportError:
    PYNPUT_OK = False

try:
    import serial, serial.tools.list_ports
    SERIAL_OK = True
except ImportError:
    SERIAL_OK = False

try:
    import keyboard
    KEYBOARD_OK = True
except ImportError:
    KEYBOARD_OK = False

# ── Constantes ────────────────────────────────────────────────────────────────

CONFIG_FILE  = "streamdeck_profiles.json"
STATS_FILE   = "streamdeck_stats.json"
ACTION_TYPES = ["program", "url", "urls", "file", "text",
                "macro", "toggle", "confirm", "script", "api", "key", "system"]
EMOJIS       = ["🎮","💼","🎬","🎵","🏠","⚡","🔧","📷","✏️","🚀","🌐","📁"]
MAX_BUTTONS  = 16
MAX_PROFILES = 20
VERSION      = "12.1"

TYPE_SYMBOL  = {
    "program":"▶","url":"⊕","urls":"⊕","file":"▤","text":"✎",
    "macro":"⛓","toggle":"⇄","confirm":"⚠","script":"🐍","api":"🌐","key":"⌨","system":"⚙",
}

TYPE_HELP = {
    "program": "Ruta o comando a ejecutar. Ej: notepad.exe  /  calc",
    "url":     "URL completa. Ej: https://google.com",
    "urls":    "URLs separadas por coma. Ej: https://a.com,https://b.com",
    "file":    "Ruta al archivo. Usá 'Archivo' para buscarlo.",
    "text":    "Texto que se copiará y pegará automáticamente.",
    "macro":   "Secuencia de acciones. Configurá los pasos abajo.",
    "toggle":  'JSON: {"state":0,"on":{"action_type":"url","action_value":"..."},"off":{...}}',
    "confirm": 'JSON: {"message":"¿Seguro?","action":{"action_type":"url","action_value":"..."}}',
    "script":  "Ruta al archivo .py a ejecutar. Usá 'Script .py' para buscarlo.",
    "api":     'JSON: {"method":"POST","url":"https://...","body":"","headers":{}}',
    "system":  "Seleccioná un comando del sistema de la lista.",
}


QUICK_COLORS = [
    "#5865f2","#4caf50","#f59e0b","#f87171","#a78bfa",
    "#34d399","#60a5fa","#fb923c","#e879f9","#94a3b8",
]

THEMES = {
    "dark": {
        "bg":"#111214","surface":"#16171b","surface2":"#1a1b20","surface3":"#1e1f24",
        "border":"#2a2b30","accent":"#5865f2","accent_bg":"#1a1c2e","accent_bd":"#2a3470",
        "text":"#e2e3e8","text_muted":"#9899a8","text_dim":"#555660",
        "green":"#4caf50","green_bg":"#1e2a1e","green_bd":"#2d4a2d",
        "red":"#f87171","btn_empty":"#252530",
    },
    "light": {
        "bg":"#f0f1f5","surface":"#ffffff","surface2":"#f5f6fa","surface3":"#ecedf2",
        "border":"#d0d1da","accent":"#5865f2","accent_bg":"#eef0fd","accent_bd":"#b0b8f8",
        "text":"#1a1b2e","text_muted":"#4a4b60","text_dim":"#9a9baa",
        "green":"#2e7d32","green_bg":"#e8f5e9","green_bd":"#a5d6a7",
        "red":"#c62828","btn_empty":"#dcdde8",
    },
}

TYPE_COLORS = {
    "dark": {
        "program":("#1e2440","#8890e0"),"url":("#1a2520","#4caf50"),
        "urls":("#1a2520","#4caf50"),"file":("#251e10","#f59e0b"),"text":("#1e2a20","#4ade80"),
        "macro":("#2a1a30","#c084fc"),"toggle":("#1a2530","#38bdf8"),
        "confirm":("#2a1e10","#fb923c"),"script":("#1a2510","#86efac"),"api":("#101a2a","#67e8f9"),"key":("#1a1020","#c084fc"),"system":("#0a1a2a","#38bdf8"),
    },
    "light": {
        "program":("#eef0fd","#5865f2"),"url":("#e8f5e9","#2e7d32"),
        "urls":("#e8f5e9","#2e7d32"),"file":("#fff8e1","#e65100"),"text":("#e8f5e9","#1b5e20"),
        "macro":("#f5e8ff","#7c3aed"),"toggle":("#e0f2fe","#0369a1"),
        "confirm":("#fff3e0","#c2410c"),"script":("#f0fdf4","#15803d"),"api":("#ecfeff","#0e7490"),"key":("#faf5ff","#7c3aed"),"system":("#e0f2fe","#0369a1"),
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# OPTIMIZACIÓN 1: Persistencia con debounce
# ══════════════════════════════════════════════════════════════════════════════

class DebouncedSaver:
    """
    Acumula llamadas a save y escribe a disco una sola vez
    después de `delay_ms` milisegundos de inactividad.
    Evita escrituras repetidas cuando se hacen cambios rápidos
    (drag, colores, toggles, ediciones).
    """
    def __init__(self, filepath, delay_ms=800):
        self._filepath = filepath
        self._delay_ms = delay_ms
        self._timer    = None
        self._data     = None
        self._lock     = threading.Lock()
        self._app      = None  # se asigna después

    def set_app(self, app):
        self._app = app

    def save(self, data):
        with self._lock:
            self._data = data
        # Cancelar timer anterior y programar nuevo
        if self._app:
            if self._timer is not None:
                self._app.after_cancel(self._timer)
            self._timer = self._app.after(self._delay_ms, self._flush)

    def _flush(self):
        with self._lock:
            data = self._data
            self._timer = None
        if data is None:
            return
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[save] {e}")

    def flush_now(self):
        """Fuerza escritura inmediata — llamar al cerrar la app."""
        if self._timer is not None and self._app:
            self._app.after_cancel(self._timer)
            self._timer = None
        with self._lock:
            data = self._data
        if data is None:
            return
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[save] {e}")


_config_saver = DebouncedSaver(CONFIG_FILE, delay_ms=800)


# ══════════════════════════════════════════════════════════════════════════════
# OPTIMIZACIÓN 2: Stats cacheados en RAM
# ══════════════════════════════════════════════════════════════════════════════

class StatsCache:
    """
    Mantiene stats en memoria. Flush a disco cada `flush_interval` segundos
    o al cerrar. Elimina lectura de disco en cada record_use().
    """
    def __init__(self, filepath, flush_interval=30):
        self._filepath = filepath
        self._flush_interval = flush_interval
        self._data = self._load()
        self._dirty = False
        self._lock  = threading.Lock()
        self._timer = None
        self._app   = None

    def set_app(self, app):
        self._app = app
        self._schedule_flush()

    def _load(self):
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def get(self, key=None):
        with self._lock:
            if key is None:
                return self._data
            return self._data.get(key, {})

    def record(self, profile_name, btn_idx, btn_name):
        key   = f"{profile_name}/{btn_idx}"
        today = datetime.date.today().isoformat()
        with self._lock:
            if key not in self._data:
                self._data[key] = {"name": btn_name, "total": 0, "history": {}}
            entry = self._data[key]
            entry["name"]  = btn_name
            entry["total"] = entry.get("total", 0) + 1
            h = entry.setdefault("history", {})
            h[today] = h.get(today, 0) + 1
            self._dirty = True

    def _schedule_flush(self):
        if self._app:
            self._timer = self._app.after(
                self._flush_interval * 1000, self._periodic_flush)

    def _periodic_flush(self):
        self.flush()
        self._schedule_flush()

    def flush(self):
        with self._lock:
            if not self._dirty:
                return
            data = copy.deepcopy(self._data)
            self._dirty = False
        try:
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[stats] {e}")


_stats_cache = StatsCache(STATS_FILE, flush_interval=30)


# ── Persistencia ──────────────────────────────────────────────────────────────

def load_all():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "profiles" in data:
                return data
        except Exception as e:
            print(f"[config] {e}")
    return {
        "active": 0, "theme": "dark",
        "profiles": [
            {"name":"Gaming",    "emoji":"🎮","cols":3,"rows":3,"buttons":[{} for _ in range(9)]},
            {"name":"Trabajo",   "emoji":"💼","cols":3,"rows":3,"buttons":[{} for _ in range(9)]},
            {"name":"Streaming", "emoji":"🎬","cols":3,"rows":3,"buttons":[{} for _ in range(9)]},
        ],
    }

def save_all(data):
    """Usa el saver con debounce — no escribe a disco de inmediato."""
    _config_saver.save(data)
    return True

def save_all_immediate(data):
    """Para casos críticos (cerrar app, exportar)."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[config] {e}")
        return False

def execute_action(cfg, app=None):
    tipo  = cfg.get("action_type","")
    valor = cfg.get("action_value","").strip()
    if not tipo:
        return False

    try:
        if tipo == "program":
            if not valor: return False
            subprocess.Popen(valor, shell=True)

        elif tipo == "url":
            if not valor: return False
            webbrowser.open(valor)

        elif tipo == "urls":
            if not valor: return False
            [webbrowser.open(u.strip()) for u in valor.split(",") if u.strip()]

        elif tipo == "file":
            if not valor: return False
            os.startfile(valor)

        elif tipo == "text":
            if not valor: return False
            pyperclip.copy(valor)
            if KEYBOARD_OK:
                time.sleep(0.1)
                keyboard.press_and_release("ctrl+v")

        elif tipo == "macro":
            try:
                steps = json.loads(valor)
            except Exception:
                print(f"[macro] JSON inválido: {valor[:80]}")
                return False
            if not steps:
                return False
            def _run_macro(_steps=steps, _app=app):
                for step in _steps:
                    tipo_paso = step.get("type","")
                    val_paso  = step.get("value","")
                    if not tipo_paso:
                        continue
                    sub_cfg = {"action_type": tipo_paso, "action_value": val_paso}
                    execute_action(sub_cfg, app=_app)
                    d = float(step.get("delay", 0.3))
                    if d > 0:
                        time.sleep(d)
            threading.Thread(target=_run_macro, daemon=True).start()

        elif tipo == "key":
            if not valor: return False
            if KEYBOARD_OK:
                keyboard.press_and_release(valor)

        elif tipo == "click":
            if not PYNPUT_OK or not valor: return False
            try:
                x, y = map(int, valor.split(","))
                ctrl = _pynput_mouse.Controller()
                ctrl.position = (x, y)
                ctrl.press(_pynput_mouse.Button.left)
                ctrl.release(_pynput_mouse.Button.left)
            except Exception as e:
                print(f"[click] {e}")
                return False

        elif tipo == "toggle":
            try:
                data = json.loads(valor)
            except Exception:
                return False
            state    = data.get("state", 0)
            sub_cfg  = data.get("on" if state == 0 else "off", {})
            data["state"] = 1 - state
            cfg["action_value"] = json.dumps(data)
            if app:
                app.after(0, app._persist_toggle, cfg)
            execute_action(sub_cfg)

        elif tipo == "confirm":
            try:
                data = json.loads(valor)
            except Exception:
                return False
            msg     = data.get("message","¿Ejecutar esta acción?")
            sub_cfg = data.get("action", {})
            if app:
                app.after(0, lambda: _confirm_and_run(msg, sub_cfg))
            else:
                _confirm_and_run(msg, sub_cfg)

        elif tipo == "script":
            if not valor: return False
            def _run_script():
                try:
                    result = subprocess.run(
                        ["python", valor], capture_output=True, text=True, timeout=30)
                    output = result.stdout + result.stderr
                    if app:
                        app.after(0, lambda o=output: app._show_script_output(o))
                except subprocess.TimeoutExpired:
                    if app:
                        app.after(0, lambda: app._show_script_output("⚠ Timeout (30s)"))
                except Exception as e:
                    if app:
                        app.after(0, lambda err=str(e): app._show_script_output(f"Error: {err}"))
            threading.Thread(target=_run_script, daemon=True).start()

        elif tipo == "api":
            try:
                data = json.loads(valor)
            except Exception:
                return False
            def _call_api():
                try:
                    method  = data.get("method","GET").upper()
                    url     = data.get("url","")
                    headers = data.get("headers",{})
                    body    = data.get("body","")
                    if method == "GET":
                        r = _requests_mod.get(url, headers=headers, timeout=10)
                    else:
                        r = _requests_mod.post(url, data=body, headers=headers, timeout=10)
                    msg = f"API {method} → {r.status_code}"
                    if app:
                        app.after(0, lambda m=msg: app._show_status(m, r.status_code < 400))
                except Exception as e:
                    if app:
                        app.after(0, lambda err=str(e): app._show_status(f"API Error: {err}", False))
            threading.Thread(target=_call_api, daemon=True).start()

        elif tipo == "system":
            if valor not in SYSTEM_COMMANDS:
                return False
            name_cmd, _, cmd = SYSTEM_COMMANDS[valor]
            if valor in SYSTEM_CONFIRM:
                from tkinter import messagebox as _mb
                parent = app if app else None
                if not _mb.askyesno("Confirmar",
                        f"¿Ejecutar: {name_cmd}?", parent=parent):
                    return False
            subprocess.Popen(cmd, shell=True)

        else:
            return False

        return True

    except Exception as e:
        print(f"[action] {e}")
        return False


def _confirm_and_run(msg, sub_cfg):
    if messagebox.askyesno("Confirmar", msg):
        execute_action(sub_cfg)


# ── Toast ─────────────────────────────────────────────────────────────────────

def show_toast(title, msg, app=None):
    if PLYER_OK:
        try:
            plyer.notification.notify(title=title, message=msg,
                                      app_name="Stream Deck", timeout=3)
            return
        except Exception:
            pass
    if app:
        app.after(0, lambda: _tk_toast(app, title, msg))

def _tk_toast(app, title, msg):
    C   = THEMES[app._theme]
    win = tk.Toplevel(app)
    win.wm_overrideredirect(True)
    win.wm_attributes("-topmost", True)
    win.configure(bg=C["surface"])

    frame = tk.Frame(win, bg=C["surface2"],
                     highlightbackground=C["border"], highlightthickness=1)
    frame.pack(ipadx=2, ipady=2)
    tk.Label(frame, text=f"  {title}  ", bg=C["surface2"],
             fg=C["accent"], font=("Arial",11,"bold"), padx=8, pady=4).pack(anchor="w")
    tk.Label(frame, text=f"  {msg}  ", bg=C["surface2"],
             fg=C["text_muted"], font=("Arial",10), padx=8, pady=2).pack(anchor="w")

    app.update_idletasks()
    sw = app.winfo_screenwidth()
    sh = app.winfo_screenheight()
    win.update_idletasks()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    win.wm_geometry(f"+{sw-w-20}+{sh-h-60}")
    win.after(3000, win.destroy)


def detectar_arduino():
    if not SERIAL_OK:
        return None
    for p in serial.tools.list_ports.comports():
        if any(k in (p.description or "") for k in ("Arduino","CH340","USB-SERIAL","CP210")):
            return p.device
    return None


# ══════════════════════════════════════════════════════════════════════════════
# COMANDOS DE SISTEMA
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_COMMANDS = {
    "shutdown": ("Apagar equipo",           "⏻", "shutdown /s /t 5"),
    "restart":  ("Reiniciar equipo",         "↺", "shutdown /r /t 5"),
    "suspend":  ("Suspender / dormir",       "💤", "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"),
    "lock":     ("Bloquear pantalla",        "🔒", "rundll32.exe user32.dll,LockWorkStation"),
    "vol_up":   ("Volumen: subir",           "🔊", "powershell -c (New-Object -com WScript.Shell).SendKeys([char]175)"),
    "vol_down": ("Volumen: bajar",           "🔉", "powershell -c (New-Object -com WScript.Shell).SendKeys([char]174)"),
    "vol_mute": ("Volumen: silenciar",       "🔇", "powershell -c (New-Object -com WScript.Shell).SendKeys([char]173)"),
    "snip":     ("Captura de pantalla",      "📸", "explorer ms-screenclip:"),
    "taskmgr":  ("Administrador de tareas",  "📊", "taskmgr"),
    "recycle":  ("Vaciar papelera",          "🗑",  "powershell -Command Clear-RecycleBin -Force -ErrorAction SilentlyContinue"),
}

SYSTEM_CONFIRM = {"shutdown", "restart"}

SYSTEM_GROUPS = {
    "Energía":    ["shutdown","restart","suspend"],
    "Sesión":     ["lock"],
    "Volumen":    ["vol_up","vol_down","vol_mute"],
    "Capturas":   ["snip"],
    "Sistema":    ["taskmgr","recycle"],
}


# ══════════════════════════════════════════════════════════════════════════════
# OPTIMIZACIÓN 3: Snapshot para detectar cambios
# ══════════════════════════════════════════════════════════════════════════════

def _btn_snapshot(cfg):
    """Genera una tupla hashable con el estado visible de un botón.
    Usado para comparar si un slot necesita repintarse."""
    if not cfg:
        return ("empty",)
    return (
        cfg.get("action_type",""),
        cfg.get("name",""),
        cfg.get("custom_color",""),
        cfg.get("icon_path",""),
    )


# ── App ────────────────────────────────────────────────────────────────────────

class StreamDeckApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Stream Deck")
        self.geometry("980x640")
        self.minsize(700, 500)

        self._data       = load_all()
        self._theme      = self._data.get("theme", "dark")
        self._active_idx = self._data.get("active", 0)
        self._sel_btn    = 0
        self._editor_type = ACTION_TYPES[0]

        self._btn_clipboard = None
        self._img_cache     = {}
        self._tooltip_win   = None

        self._hotkeys_active  = False
        self._tray_icon       = None
        self._scheduler       = sched.scheduler(time.time, time.sleep)
        self._sched_thread    = None
        self._drag_source     = None

        # ── OPT: snapshots para repintado selectivo de grilla ─────────────
        self._grid_snapshots = [None] * MAX_BUTTONS
        self._grid_sel_cache = -1   # último sel_btn pintado en la grilla

        # ── OPT: conectar saver y stats cache ─────────────────────────────
        _config_saver.set_app(self)
        _stats_cache.set_app(self)

        self.arduino_var = tk.StringVar(value="Sin conexión")
        self.last_action = tk.StringVar(value="—")
        self.status_var  = tk.StringVar(value="")

        ctk.set_appearance_mode("dark" if self._theme == "dark" else "light")
        self.configure(fg_color=self.C["bg"])

        self._build_ui()
        self._start_serial()
        self._start_hotkeys()
        self._start_scheduler()
        self._load_scheduled_actions()

        # ── OPT: flush al cerrar ──────────────────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def _on_app_close(self):
        """Flush pendientes a disco antes de cerrar."""
        _config_saver.flush_now()
        _stats_cache.flush()
        self.destroy()

    # ── Acceso ────────────────────────────────────────────────────────────────

    @property
    def C(self):
        return THEMES[self._theme]

    @property
    def _profile(self):
        p = self._data["profiles"]
        if self._active_idx >= len(p):
            self._active_idx = 0
        return p[self._active_idx]

    @property
    def _buttons(self):
        return self._profile["buttons"]

    def _tcolors(self, tipo, custom_color=None):
        if custom_color:
            try:
                r = int(custom_color[1:3], 16)
                g = int(custom_color[3:5], 16)
                b = int(custom_color[5:7], 16)
                lum = (0.299*r + 0.587*g + 0.114*b) / 255
                fg = "#ffffff" if lum < 0.55 else "#1a1b2e"
            except Exception:
                fg = "#ffffff"
            return (custom_color, fg)
        return TYPE_COLORS[self._theme].get(tipo, (self.C["surface3"], self.C["text_dim"]))

    def _load_img(self, path, size=28):
        key = (path, size)
        if key in self._img_cache:
            return self._img_cache[key]
        try:
            img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
            cimg = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
            self._img_cache[key] = cimg
            return cimg
        except Exception as e:
            print(f"[img] {e}")
            return None

    def _total(self):
        return self._profile["cols"] * self._profile["rows"]

    # ═══════════════════════════════════════════════════════════════════════════
    # BUILD
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._build_topbar()

        self._main = ctk.CTkFrame(self, fg_color="transparent")
        self._main.pack(fill="both", expand=True)
        self._main.grid_columnconfigure(0, weight=0, minsize=160)
        self._main.grid_columnconfigure(1, weight=1, minsize=260)
        self._main.grid_columnconfigure(2, weight=0, minsize=250)
        self._main.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_center()
        self._build_editor_static()
        self._build_statusbar()

        self._paint_profile_list()
        self._paint_grid()
        self._paint_editor()
        self._paint_sidebar_info()
        self._paint_statusbar()

    # ── Top bar ───────────────────────────────────────────────────────────────

    def _build_topbar(self):
        C = self.C
        bar = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0,
                           height=46, border_width=0)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", padx=16, pady=8)
        logo = ctk.CTkFrame(left, fg_color=C["accent"], width=28, height=28, corner_radius=6)
        logo.pack(side="left", padx=(0,10))
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="▦", font=("Arial",13,"bold"),
                     text_color="white").place(relx=.5, rely=.5, anchor="center")
        ctk.CTkLabel(left, text="Stream Deck", font=("Arial",14,"bold"),
                     text_color=C["text"]).pack(side="left")

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=16)

        self._theme_btn = ctk.CTkButton(
            right, text="☀" if self._theme == "dark" else "☾",
            width=34, height=28, font=("Arial",14),
            fg_color=C["surface3"], hover_color=C["surface2"],
            text_color=C["text_muted"],
            border_width=1, border_color=C["border"], corner_radius=7,
            command=self._toggle_theme)
        self._theme_btn.pack(side="right", padx=(4,0))

        ctk.CTkButton(right, text="⊟", width=34, height=28, font=("Arial",14),
                      fg_color=C["surface3"], hover_color=C["surface2"],
                      text_color=C["text_muted"],
                      border_width=1, border_color=C["border"], corner_radius=7,
                      command=self._minimize_to_tray).pack(side="right", padx=(4,0))

        ctk.CTkButton(right, text="⇅", width=34, height=28, font=("Arial",14),
                      fg_color=C["surface3"], hover_color=C["surface2"],
                      text_color=C["text_muted"],
                      border_width=1, border_color=C["border"], corner_radius=7,
                      command=self._export_import_menu).pack(side="right", padx=(4,0))

        badge = ctk.CTkFrame(right, fg_color=C["green_bg"],
                             border_color=C["green_bd"], border_width=1, corner_radius=20)
        badge.pack(side="right", pady=8)
        dot = ctk.CTkFrame(badge, fg_color=C["green"], width=7, height=7, corner_radius=4)
        dot.pack(side="left", padx=(8,4))
        dot.pack_propagate(False)
        ctk.CTkLabel(badge, textvariable=self.arduino_var, font=("Arial",11),
                     text_color=C["green"]).pack(side="left", padx=(0,10), pady=4)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        C = self.C
        sb = ctk.CTkFrame(self._main, fg_color=C["surface"],
                          border_width=0, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_rowconfigure(0, weight=1)
        sb.grid_columnconfigure(0, weight=1)

        pad = ctk.CTkFrame(sb, fg_color="transparent")
        pad.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        pad.grid_rowconfigure(1, weight=1)
        pad.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(pad, text="PERFILES", font=("Arial",9,"bold"),
                     text_color=C["text_dim"]).grid(row=0, column=0,
                     sticky="w", pady=(0,4))

        scroll = ctk.CTkScrollableFrame(pad, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        self._profile_rows = []
        for i in range(MAX_PROFILES):
            row = ctk.CTkFrame(scroll, fg_color="transparent",
                               corner_radius=7, border_width=0)
            row.grid_columnconfigure(0, weight=1)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=6, pady=4)

            emoji_lbl = ctk.CTkLabel(inner, text="", font=("Arial",13), width=22)
            emoji_lbl.pack(side="left", padx=(0,5))

            name_lbl = ctk.CTkLabel(inner, text="", font=("Arial",11),
                                    text_color=C["text_muted"], anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)

            grid_lbl = ctk.CTkLabel(inner, text="", font=("Arial",9),
                                    text_color=C["text_dim"],
                                    fg_color=C["surface3"],
                                    corner_radius=6, width=30)
            grid_lbl.pack(side="right", padx=(0,2))

            menu_btn = ctk.CTkButton(inner, text="⋯", width=22, height=20,
                                     font=("Arial",12),
                                     fg_color="transparent",
                                     hover_color=C["surface3"],
                                     text_color=C["text_dim"], border_width=0,
                                     command=lambda idx=i: self._profile_menu(idx))
            menu_btn.pack(side="right")

            for w in [row, inner, emoji_lbl, name_lbl]:
                w.bind("<Button-1>", lambda e, idx=i: self._switch_profile(idx))

            self._profile_rows.append({
                "row": row, "inner": inner,
                "emoji": emoji_lbl, "name": name_lbl,
                "grid": grid_lbl, "menu": menu_btn,
            })

        bottom = ctk.CTkFrame(pad, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", pady=(6,0))
        bottom.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(bottom, text="+ Nuevo perfil", height=28,
                      font=("Arial",10),
                      fg_color=C["surface3"], hover_color=C["surface2"],
                      text_color=C["text_muted"],
                      border_width=1, border_color=C["border"], corner_radius=7,
                      command=self._new_profile).grid(row=0, column=0,
                      sticky="ew", pady=(0,6))

        ctk.CTkFrame(bottom, fg_color=C["border"], height=1).grid(
            row=1, column=0, sticky="ew", pady=(0,6))

        ctk.CTkLabel(bottom, text="PERFIL ACTIVO", font=("Arial",9,"bold"),
                     text_color=C["text_dim"]).grid(row=2, column=0,
                     sticky="w", pady=(0,4))

        info = ctk.CTkFrame(bottom, fg_color=C["surface3"], corner_radius=8)
        info.grid(row=3, column=0, sticky="ew")
        info.grid_columnconfigure(0, weight=1)
        ipad = ctk.CTkFrame(info, fg_color="transparent")
        ipad.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(ipad, text="Grilla", font=("Arial",10),
                     text_color=C["text_dim"]).pack(anchor="w")
        self._layout_lbl = ctk.CTkLabel(ipad, text="", font=("Arial",11),
                                        text_color=C["text_muted"])
        self._layout_lbl.pack(anchor="w", pady=(1,6))

        ctk.CTkLabel(ipad, text="Configurados", font=("Arial",10),
                     text_color=C["text_dim"]).pack(anchor="w")
        self._configured_lbl = ctk.CTkLabel(ipad, text="", font=("Arial",11),
                                            text_color=C["green"])
        self._configured_lbl.pack(anchor="w", pady=(1,0))

    def _paint_profile_list(self):
        C        = self.C
        profiles = self._data["profiles"]
        n        = len(profiles)

        for i, pr in enumerate(self._profile_rows):
            if i < n:
                p      = profiles[i]
                active = (i == self._active_idx)

                pr["row"].configure(
                    fg_color=C["accent_bg"] if active else "transparent",
                    border_width=1 if active else 0,
                    border_color=C["accent_bd"])
                pr["emoji"].configure(text=p.get("emoji","🎮"))
                pr["name"].configure(
                    text=p["name"],
                    text_color=C["text"] if active else C["text_muted"])
                pr["grid"].configure(text=f"{p['cols']}×{p['rows']}")
                pr["row"].pack(fill="x", pady=1)
            else:
                pr["row"].pack_forget()

    def _paint_sidebar_info(self):
        p = self._profile
        self._layout_lbl.configure(
            text=f"{p['cols']} × {p['rows']}  —  {self._total()} botones")
        n = sum(1 for b in self._buttons if b.get("action_type"))
        self._configured_lbl.configure(text=f"{n} / {self._total()}")

    # ── Grilla ────────────────────────────────────────────────────────────────

    def _build_center(self):
        C = self.C
        self._center = ctk.CTkFrame(self._main, fg_color="transparent")
        self._center.grid(row=0, column=1, sticky="nsew", padx=2)
        self._center.grid_rowconfigure(1, weight=1)
        self._center.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self._center, fg_color="transparent", height=44)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14,0))
        hdr.grid_propagate(False)

        self._grid_title = ctk.CTkLabel(hdr, text="", font=("Arial",13,"bold"),
                                        text_color=C["text_muted"])
        self._grid_title.pack(side="left")

        self._preset_row = ctk.CTkFrame(hdr, fg_color="transparent")
        self._preset_row.pack(side="right")

        self._preset_btns = {}
        for label, c, r in [("2×2",2,2),("3×3",3,3),("3×4",3,4),("4×4",4,4)]:
            btn = ctk.CTkButton(
                self._preset_row, text=label, width=50, height=26, font=("Arial",11),
                fg_color=C["surface3"], text_color=C["text_dim"],
                border_width=0, border_color=C["surface3"],
                hover_color=C["surface3"], corner_radius=6,
                command=lambda cc=c, rr=r: self._change_grid(cc, rr))
            btn.pack(side="left", padx=3)
            self._preset_btns[(c,r)] = btn

        self._grid_scroll = ctk.CTkScrollableFrame(self._center, fg_color="transparent")
        self._grid_scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=10)

        self._btn_pool = []
        for i in range(MAX_BUTTONS):
            outer = ctk.CTkFrame(self._grid_scroll, fg_color=C["surface2"],
                                 border_color=C["border"], border_width=1,
                                 corner_radius=10)

            plus_lbl = ctk.CTkLabel(outer, text="+", font=("Arial",22),
                                    text_color=C["btn_empty"])
            plus_lbl.place(relx=.5, rely=.5, anchor="center")

            content = ctk.CTkFrame(outer, fg_color="transparent")
            icon_box = ctk.CTkFrame(content, fg_color=C["surface3"],
                                    width=32, height=32, corner_radius=7)
            icon_box.pack(pady=(0,5))
            icon_box.pack_propagate(False)
            icon_lbl = ctk.CTkLabel(icon_box, text="", font=("Arial",13),
                                    text_color=C["text_dim"])
            icon_lbl.place(relx=.5, rely=.5, anchor="center")
            name_lbl = ctk.CTkLabel(content, text="", font=("Arial",10),
                                    text_color=C["text_muted"],
                                    wraplength=110, justify="center")
            name_lbl.pack()

            badge = ctk.CTkLabel(outer, text="", font=("Arial",8),
                                 text_color=C["text_dim"],
                                 fg_color=C["surface3"], corner_radius=4)
            badge.place(relx=1.0, rely=0, anchor="ne", x=-5, y=5)

            for w in [outer, plus_lbl, content, icon_box, icon_lbl, name_lbl, badge]:
                w.bind("<Button-1>",        lambda e, idx=i: self._select_btn(idx))
                w.bind("<Button-3>",        lambda e, idx=i: self._btn_context_menu(e, idx))
                w.bind("<Enter>",           lambda e, idx=i: self._tooltip_show(e, idx))
                w.bind("<Leave>",           lambda e: self._tooltip_hide())
                w.bind("<B1-Motion>",       lambda e, idx=i: self._drag_start(idx))
                w.bind("<ButtonRelease-1>", lambda e, idx=i: self._drag_end(idx))

            self._btn_pool.append({
                "outer": outer, "plus": plus_lbl, "content": content,
                "icon_box": icon_box, "icon_lbl": icon_lbl,
                "name_lbl": name_lbl, "badge": badge,
            })

        feed = ctk.CTkFrame(self._center, fg_color=C["surface2"],
                            border_color=C["border"], border_width=1, corner_radius=10)
        feed.grid(row=2, column=0, sticky="ew", padx=16, pady=(0,14))
        fi = ctk.CTkFrame(feed, fg_color="transparent")
        fi.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(fi, text="ÚLTIMA ACCIÓN", font=("Arial",9,"bold"),
                     text_color=C["text_dim"]).pack(anchor="w")
        fr = ctk.CTkFrame(fi, fg_color="transparent")
        fr.pack(fill="x", pady=(5,0))
        dot = ctk.CTkFrame(fr, fg_color=C["green"], width=7, height=7, corner_radius=4)
        dot.pack(side="left", padx=(0,8))
        dot.pack_propagate(False)
        ctk.CTkLabel(fr, textvariable=self.last_action, font=("Arial",12),
                     text_color=C["text_muted"]).pack(side="left")

    # ══════════════════════════════════════════════════════════════════════════
    # OPTIMIZACIÓN 4: _paint_grid con snapshots — solo repinta lo que cambió
    # ══════════════════════════════════════════════════════════════════════════

    def _paint_grid(self, force=False):
        """
        Repinta la grilla comparando snapshots.
        Solo llama .configure() en los slots que realmente cambiaron.
        force=True fuerza repintado completo (cambio de perfil, tema, grid size).
        """
        C     = self.C
        p     = self._profile
        cols  = p["cols"]
        total = p["cols"] * p["rows"]

        for (c,r), btn in self._preset_btns.items():
            active = (c == p["cols"] and r == p["rows"])
            btn.configure(
                fg_color=C["accent_bg"] if active else C["surface3"],
                text_color=C["text"] if active else C["text_dim"],
                border_width=1 if active else 0,
                border_color=C["accent_bd"] if active else C["surface3"])

        self._grid_title.configure(text=f"{p['emoji']}  {p['name']}")

        for i, slot in enumerate(self._btn_pool):
            if i < total:
                cfg = self._buttons[i] if i < len(self._buttons) else {}
                snap = _btn_snapshot(cfg) + (i == self._sel_btn,)

                # OPT: skip si el snapshot no cambió
                if not force and self._grid_snapshots[i] == snap:
                    # Solo re-grid si estaba oculto
                    if not slot["outer"].winfo_ismapped():
                        slot["outer"].grid(row=i//cols, column=i%cols,
                                           padx=6, pady=6, sticky="nsew")
                    continue

                self._grid_snapshots[i] = snap
                self._paint_slot_inner(i, slot, cfg, cols)
            else:
                slot["outer"].grid_remove()
                self._grid_snapshots[i] = None

        self._grid_sel_cache = self._sel_btn

        for c in range(cols):
            self._grid_scroll.grid_columnconfigure(c, weight=1, minsize=100)
        rows_used = (total + cols - 1) // cols
        for r in range(rows_used):
            self._grid_scroll.grid_rowconfigure(r, weight=1, minsize=95)

    def _paint_slot_inner(self, i, slot, cfg, cols):
        """Pinta un slot individual — extraído para reutilizar."""
        C            = self.C
        tipo         = cfg.get("action_type","")
        name         = cfg.get("name", f"Botón {i+1}")
        is_sel       = (i == self._sel_btn)
        empty        = not tipo
        custom_color = cfg.get("custom_color","")
        icon_path    = cfg.get("icon_path","")
        icon_bg, icon_fg = self._tcolors(tipo, custom_color)

        slot["outer"].grid(row=i//cols, column=i%cols, padx=6, pady=6, sticky="nsew")
        slot["outer"].configure(
            fg_color=C["accent_bg"] if is_sel else C["surface2"],
            border_color=C["accent"] if is_sel else (C["border"] if not empty else C["btn_empty"]))

        if empty:
            slot["plus"].configure(text_color=C["btn_empty"])
            slot["plus"].place(relx=.5, rely=.5, anchor="center")
            slot["content"].place_forget()
            slot["badge"].configure(text="")
        else:
            slot["plus"].place_forget()
            slot["content"].place(relx=.5, rely=.5, anchor="center")
            slot["icon_box"].configure(fg_color=icon_bg)

            if icon_path and os.path.exists(icon_path):
                img = self._load_img(icon_path, 22)
                if img:
                    slot["icon_lbl"].configure(image=img, text="")
                else:
                    slot["icon_lbl"].configure(image=None,
                        text=TYPE_SYMBOL.get(tipo,"?"), text_color=icon_fg)
            else:
                slot["icon_lbl"].configure(image=None,
                    text=TYPE_SYMBOL.get(tipo,"?"), text_color=icon_fg)

            slot["name_lbl"].configure(
                text=name,
                text_color=C["text"] if is_sel else C["text_muted"])
            slot["badge"].configure(text=tipo)

    def _paint_single_slot(self, i):
        """Repinta un solo slot — invalida su snapshot para forzar repintado."""
        C     = self.C
        p     = self._profile
        total = p["cols"] * p["rows"]
        if i >= total or i >= MAX_BUTTONS:
            return
        cfg = self._buttons[i] if i < len(self._buttons) else {}
        self._grid_snapshots[i] = None   # invalidar
        self._paint_slot_inner(i, self._btn_pool[i], cfg, p["cols"])
        # Actualizar snapshot
        self._grid_snapshots[i] = _btn_snapshot(cfg) + (i == self._sel_btn,)

    # ── Editor estático ───────────────────────────────────────────────────────

    def _build_editor_static(self):
        C = self.C
        self._editor = ctk.CTkFrame(self._main, fg_color=C["surface"],
                                    border_width=0, corner_radius=0)
        self._editor.grid(row=0, column=2, sticky="nsew")
        self._editor.grid_rowconfigure(0, weight=0)
        self._editor.grid_rowconfigure(1, weight=0)
        self._editor.grid_rowconfigure(2, weight=0)
        self._editor.grid_rowconfigure(3, weight=0)
        self._editor.grid_rowconfigure(4, weight=1)
        self._editor.grid_columnconfigure(0, weight=1)

        # Header
        self._ed_hdr = ctk.CTkFrame(self._editor, fg_color=C["surface2"],
                                    border_color=C["border"], border_width=1,
                                    corner_radius=0, height=66)
        self._ed_hdr.grid(row=0, column=0, sticky="ew")
        self._ed_hdr.grid_propagate(False)
        hi = ctk.CTkFrame(self._ed_hdr, fg_color="transparent")
        hi.pack(fill="both", expand=True, padx=14, pady=10)

        self._ed_avatar = ctk.CTkFrame(hi, fg_color=C["surface3"],
                                       border_color=C["accent_bd"], border_width=1,
                                       width=36, height=36, corner_radius=8)
        self._ed_avatar.pack(side="left", padx=(0,10))
        self._ed_avatar.pack_propagate(False)
        self._ed_avatar_lbl = ctk.CTkLabel(self._ed_avatar, text="?",
                                           font=("Arial",14), text_color=C["text_dim"])
        self._ed_avatar_lbl.place(relx=.5, rely=.5, anchor="center")

        info = ctk.CTkFrame(hi, fg_color="transparent")
        info.pack(side="left")
        self._ed_title = ctk.CTkLabel(info, text="", font=("Arial",13,"bold"),
                                      text_color=C["text"])
        self._ed_title.pack(anchor="w")
        self._ed_sub = ctk.CTkLabel(info, text="", font=("Arial",10),
                                    text_color=C["text_dim"])
        self._ed_sub.pack(anchor="w")

        # Nombre
        name_row = ctk.CTkFrame(self._editor, fg_color="transparent")
        name_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(8,0))
        ctk.CTkLabel(name_row, text="NOMBRE", font=("Arial",9,"bold"),
                     text_color=C["text_dim"]).pack(anchor="w", pady=(0,3))
        self._ed_name = ctk.CTkEntry(name_row, fg_color=C["surface3"],
                                     border_color=C["border"], border_width=1,
                                     corner_radius=7, font=("Arial",12),
                                     text_color=C["text"],
                                     placeholder_text="Nombre del botón")
        self._ed_name.pack(fill="x")

        # Tab bar
        tab_bar = ctk.CTkFrame(self._editor, fg_color=C["surface2"],
                               height=34, corner_radius=0,
                               border_color=C["border"], border_width=0)
        tab_bar.grid(row=2, column=0, sticky="ew", pady=(8,0))
        tab_bar.grid_propagate(False)

        self._tab_names  = ["Acción", "Apariencia", "Avanzado"]
        self._active_tab = tk.StringVar(value="Acción")
        self._tab_btns   = {}

        for tname in self._tab_names:
            tb = ctk.CTkButton(
                tab_bar, text=tname, height=34,
                font=("Arial",11),
                fg_color=C["surface"],
                text_color=C["text"],
                hover_color=C["surface3"],
                corner_radius=0, border_width=0,
                command=lambda t=tname: self._switch_tab(t))
            tb.pack(side="left", fill="y", expand=True)
            self._tab_btns[tname] = tb

        self._tab_indicator_bar = tk.Frame(
            self._editor, bg=C["surface2"], height=3)
        self._tab_indicator_bar.grid(row=3, column=0, sticky="ew")
        self._tab_canvas = tk.Canvas(
            self._tab_indicator_bar, height=3, bg=C["surface2"],
            highlightthickness=0)
        self._tab_canvas.pack(fill="x")

        self._tab_body = ctk.CTkScrollableFrame(
            self._editor, fg_color="transparent")
        self._tab_body.grid(row=4, column=0, sticky="nsew")

        # ── OPT: flag para saber si los tabs necesitan repintarse ─────────
        self._tab_dirty = {"Acción": True, "Apariencia": True, "Avanzado": True}

        def sec(text):
            f = ctk.CTkFrame(self._tab_body, fg_color=C["surface2"],
                             corner_radius=8)
            f.pack(fill="x", padx=12, pady=(8,0))
            hdr = ctk.CTkFrame(f, fg_color="transparent")
            hdr.pack(fill="x", padx=10, pady=(8,4))
            ctk.CTkLabel(hdr, text=text, font=("Arial",9,"bold"),
                         text_color=C["text_dim"]).pack(anchor="w")
            body = ctk.CTkFrame(f, fg_color="transparent")
            body.pack(fill="x", padx=10, pady=(0,10))
            return body

        # ╔══════════════════════════════════╗
        # ║  TAB 1: ACCIÓN                  ║
        # ╚══════════════════════════════════╝
        self._page_accion_widgets = []

        s_tipo = sec("TIPO DE ACCIÓN")
        self._page_accion_widgets.append(s_tipo.master)

        grid_tipos = ctk.CTkFrame(s_tipo, fg_color="transparent")
        grid_tipos.pack(fill="x")
        self._ed_pills = {}
        TYPE_LABELS = {
            "program": ("▶","Program"),  "url":   ("⊕","URL"),
            "urls":    ("⊕","URLs"),     "file":  ("▤","Archivo"),
            "text":    ("✎","Texto"),    "macro": ("⛓","Macro"),
            "toggle":  ("⇄","Toggle"),  "confirm":("⚠","Confirm"),
            "script":  ("🐍","Script"),  "api":   ("🌐","API"),
        }
        for col, at in enumerate(ACTION_TYPES):
            icon, label = TYPE_LABELS.get(at, ("?", at))
            icon_bg, icon_fg = TYPE_COLORS[self._theme].get(at, (C["surface3"], C["text_dim"]))
            cell = ctk.CTkFrame(grid_tipos, fg_color=C["surface3"],
                                corner_radius=8, border_width=1,
                                border_color=C["border"],
                                width=52, height=52)
            cell.grid(row=col//5, column=col%5, padx=3, pady=3)
            cell.grid_propagate(False)
            inner_cell = ctk.CTkFrame(cell, fg_color="transparent")
            inner_cell.place(relx=.5, rely=.5, anchor="center")
            ctk.CTkLabel(inner_cell, text=icon, font=("Arial",14),
                         text_color=icon_fg).pack()
            ctk.CTkLabel(inner_cell, text=label, font=("Arial",8),
                         text_color=C["text_dim"]).pack()
            for w in [cell, inner_cell] + inner_cell.winfo_children():
                w.bind("<Button-1>", lambda e, t=at: self._set_editor_type(t))
            self._ed_pills[at] = cell

        s_val = sec("VALOR")
        self._page_accion_widgets.append(s_val.master)

        self._ed_help = ctk.CTkLabel(s_val, text="", font=("Arial",9),
                                     text_color=C["text_dim"],
                                     wraplength=220, justify="left")
        self._ed_help.pack(anchor="w", pady=(0,4))

        self._ed_val_container = ctk.CTkFrame(s_val, fg_color="transparent")
        self._ed_val_container.pack(fill="x")

        self._ed_val_entry = ctk.CTkEntry(self._ed_val_container,
                                          fg_color=C["surface3"],
                                          border_color=C["border"], border_width=1,
                                          corner_radius=7, font=("Arial",11),
                                          text_color=C["text"],
                                          placeholder_text="Ingresá el valor...")
        self._ed_val_text = ctk.CTkTextbox(self._ed_val_container,
                                           fg_color=C["surface3"],
                                           border_color=C["border"], border_width=1,
                                           corner_radius=7, font=("Arial",11),
                                           text_color=C["text"], height=80)
        self._ed_val_entry.pack(fill="x")

        self._ed_system_frame = ctk.CTkFrame(self._ed_val_container,
                                             fg_color=C["surface3"],
                                             border_color=C["border"],
                                             border_width=1, corner_radius=7)
        sys_inner = ctk.CTkFrame(self._ed_system_frame, fg_color="transparent")
        sys_inner.pack(fill="x", padx=8, pady=6)
        self._ed_system_lbl = ctk.CTkLabel(sys_inner,
                                           text="Ningún comando seleccionado",
                                           font=("Arial",11),
                                           text_color=C["text_dim"])
        self._ed_system_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(sys_inner, text="Cambiar", width=70, height=26,
                      font=("Arial",10),
                      fg_color=C["accent"], hover_color="#4a55e0",
                      text_color="white", corner_radius=6,
                      command=self._open_system_picker).pack(side="right")

        val_btns = ctk.CTkFrame(s_val, fg_color="transparent")
        val_btns.pack(fill="x", pady=(6,0))
        ctk.CTkButton(val_btns, text="📂 Archivo", width=80, height=26,
                      font=("Arial",10), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._pick_file).pack(side="left", padx=(0,4))
        ctk.CTkButton(val_btns, text="📜 Script .py", width=90, height=26,
                      font=("Arial",10), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._pick_script).pack(side="left")

        s_macro = sec("PASOS DEL MACRO")
        self._page_accion_widgets.append(s_macro.master)
        self._macro_frame = s_macro

        self._macro_preview_lbl = ctk.CTkLabel(
            s_macro, text="Sin pasos configurados",
            font=("Arial",10), text_color=C["text_dim"])
        self._macro_preview_lbl.pack(anchor="w", pady=(0,6))

        ctk.CTkButton(s_macro, text="Abrir constructor de macro",
                      height=32, font=("Arial",11,"bold"),
                      fg_color=C["accent"], hover_color="#4a55e0",
                      text_color="white", corner_radius=7,
                      command=self._open_macro_builder).pack(fill="x")

        s_actions = sec("EJECUTAR")
        self._page_accion_widgets.append(s_actions.master)
        self._ed_status = ctk.CTkLabel(s_actions, textvariable=self.status_var,
                                       font=("Arial",10), text_color=C["green"])
        self._ed_status.pack(anchor="w", pady=(0,4))
        ctk.CTkButton(s_actions, text="💾  Guardar cambios", height=34,
                      font=("Arial",12,"bold"),
                      fg_color=C["accent"], hover_color="#4a55e0",
                      text_color="white", corner_radius=7,
                      command=self._save_current).pack(fill="x")
        ctk.CTkButton(s_actions, text="▶  Probar ahora", height=28,
                      font=("Arial",11),
                      fg_color=C["surface3"], hover_color=C["surface2"],
                      text_color=C["text_muted"],
                      border_width=1, border_color=C["border"], corner_radius=7,
                      command=self._test_action).pack(fill="x", pady=(6,0))

        self._script_out_frame = ctk.CTkFrame(s_actions, fg_color=C["surface3"],
                                              corner_radius=6)
        self._script_out_box   = ctk.CTkTextbox(self._script_out_frame,
                                                height=70, font=("Courier",9),
                                                fg_color=C["surface3"],
                                                text_color=C["text_muted"],
                                                border_width=0)
        self._script_out_box.pack(fill="x", padx=6, pady=4)

        # ╔══════════════════════════════════╗
        # ║  TAB 2: APARIENCIA              ║
        # ╚══════════════════════════════════╝
        self._page_apariencia_widgets = []

        s_color = sec("COLOR DEL BOTÓN")
        self._page_apariencia_widgets.append(s_color.master)

        quick_grid = ctk.CTkFrame(s_color, fg_color="transparent")
        quick_grid.pack(anchor="w", pady=(0,6))
        self._quick_color_btns = []
        for qc in QUICK_COLORS:
            cb = ctk.CTkFrame(quick_grid, fg_color=qc,
                              width=22, height=22, corner_radius=5,
                              border_width=1, border_color=C["border"])
            cb.pack(side="left", padx=2)
            cb.bind("<Button-1>", lambda e, c=qc: self._set_quick_color(c))
            self._quick_color_btns.append(cb)

        color_row2 = ctk.CTkFrame(s_color, fg_color="transparent")
        color_row2.pack(fill="x")
        self._ed_color_preview = ctk.CTkFrame(color_row2,
            fg_color=C["surface3"], width=30, height=30, corner_radius=7,
            border_width=1, border_color=C["border"])
        self._ed_color_preview.pack(side="left", padx=(0,8))
        self._ed_color_preview.pack_propagate(False)
        self._ed_color_label = ctk.CTkLabel(color_row2, text="Por defecto",
            font=("Arial",11), text_color=C["text_muted"])
        self._ed_color_label.pack(side="left")
        ctk.CTkButton(color_row2, text="Elegir", width=54, height=26,
                      font=("Arial",10), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._pick_color).pack(side="right")
        ctk.CTkButton(color_row2, text="✕", width=26, height=26,
                      font=("Arial",10), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._clear_color).pack(side="right", padx=(0,4))

        s_icon = sec("ÍCONO PERSONALIZADO")
        self._page_apariencia_widgets.append(s_icon.master)

        icon_row2 = ctk.CTkFrame(s_icon, fg_color="transparent")
        icon_row2.pack(fill="x")
        self._ed_icon_preview = ctk.CTkLabel(icon_row2, text="Sin imagen",
            font=("Arial",9), text_color=C["text_dim"],
            fg_color=C["surface3"], corner_radius=6, width=44, height=44)
        self._ed_icon_preview.pack(side="left", padx=(0,10))
        icon_col = ctk.CTkFrame(icon_row2, fg_color="transparent")
        icon_col.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(icon_col, text="📂 Explorar imagen", height=28,
                      font=("Arial",10), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._pick_icon).pack(fill="x")
        ctk.CTkButton(icon_col, text="✕ Quitar", height=24,
                      font=("Arial",10), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._clear_icon).pack(fill="x", pady=(4,0))

        # ╔══════════════════════════════════╗
        # ║  TAB 3: AVANZADO               ║
        # ╚══════════════════════════════════╝
        self._page_avanzado_widgets = []

        s_stats = sec("ESTADÍSTICAS DE USO")
        self._page_avanzado_widgets.append(s_stats.master)

        stats_row1 = ctk.CTkFrame(s_stats, fg_color="transparent")
        stats_row1.pack(fill="x")
        ctk.CTkLabel(stats_row1, text="Total:", font=("Arial",11),
                     text_color=C["text_dim"]).pack(side="left")
        self._ed_stat_total = ctk.CTkLabel(stats_row1, text="0",
            font=("Arial",13,"bold"), text_color=C["green"])
        self._ed_stat_total.pack(side="right")

        stats_row2 = ctk.CTkFrame(s_stats, fg_color="transparent")
        stats_row2.pack(fill="x", pady=(4,6))
        ctk.CTkLabel(stats_row2, text="Hoy:", font=("Arial",11),
                     text_color=C["text_dim"]).pack(side="left")
        self._ed_stat_today = ctk.CTkLabel(stats_row2, text="0",
            font=("Arial",13,"bold"), text_color=C["text_muted"])
        self._ed_stat_today.pack(side="right")
        ctk.CTkButton(s_stats, text="📊 Ver historial", height=26,
                      font=("Arial",10), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._show_stats_window).pack(fill="x")

        s_sched = sec("ACCIÓN PROGRAMADA")
        self._page_avanzado_widgets.append(s_sched.master)

        sched_r = ctk.CTkFrame(s_sched, fg_color="transparent")
        sched_r.pack(fill="x")
        ctk.CTkLabel(sched_r, text="Hora HH:MM", font=("Arial",11),
                     text_color=C["text_dim"]).pack(side="left")
        self._ed_sched_time = ctk.CTkEntry(sched_r, width=80, height=28,
                                           fg_color=C["surface3"],
                                           border_color=C["border"], border_width=1,
                                           corner_radius=6, font=("Arial",11),
                                           text_color=C["text"],
                                           placeholder_text="14:30")
        self._ed_sched_time.pack(side="right")
        self._ed_sched_lbl = ctk.CTkLabel(s_sched, text="Sin programar",
                                          font=("Arial",10), text_color=C["text_dim"])
        self._ed_sched_lbl.pack(anchor="w", pady=(4,6))
        sched_btns2 = ctk.CTkFrame(s_sched, fg_color="transparent")
        sched_btns2.pack(fill="x")
        ctk.CTkButton(sched_btns2, text="Programar", height=28,
                      font=("Arial",11), fg_color=C["accent"],
                      text_color="white", corner_radius=6,
                      command=self._schedule_btn).pack(side="left", fill="x",
                                                        expand=True, padx=(0,4))
        ctk.CTkButton(sched_btns2, text="Cancelar", height=28,
                      font=("Arial",11), fg_color=C["surface3"],
                      text_color=C["text_muted"], hover_color=C["surface2"],
                      border_width=1, border_color=C["border"], corner_radius=6,
                      command=self._cancel_schedule).pack(side="left", fill="x",
                                                          expand=True)

        s_hotkey = sec("ATAJO GLOBAL")
        self._page_avanzado_widgets.append(s_hotkey.master)
        hk_row = ctk.CTkFrame(s_hotkey, fg_color="transparent")
        hk_row.pack(fill="x")
        ctk.CTkLabel(hk_row, text="Ctrl +", font=("Arial",11),
                     text_color=C["text_dim"]).pack(side="left")
        self._ed_hotkey = ctk.CTkEntry(hk_row, width=50, height=28,
                                       fg_color=C["surface3"],
                                       border_color=C["border"], border_width=1,
                                       corner_radius=6, font=("Arial",11),
                                       text_color=C["text"],
                                       placeholder_text="1")
        self._ed_hotkey.pack(side="right")
        ctk.CTkLabel(s_hotkey,
                     text="Ctrl+1..9 asignados por posición. Extra aquí.",
                     font=("Arial",9), text_color=C["text_dim"],
                     wraplength=220, justify="left").pack(anchor="w", pady=(4,0))

        self._switch_tab("Acción")

    # ══════════════════════════════════════════════════════════════════════════
    # OPTIMIZACIÓN 5: _paint_editor con tabs lazy
    # ══════════════════════════════════════════════════════════════════════════

    def _paint_editor(self):
        C    = self.C
        idx  = self._sel_btn
        btns = self._buttons
        cfg  = btns[idx] if idx < len(btns) else {}
        name = cfg.get("name", f"Botón {idx+1}")
        tipo = cfg.get("action_type", ACTION_TYPES[0])
        val  = cfg.get("action_value", "")
        custom_color = cfg.get("custom_color", "")
        icon_path    = cfg.get("icon_path", "")

        self._editor_type = tipo
        icon_bg, icon_fg = self._tcolors(tipo, custom_color)

        # Header — siempre visible
        self._ed_avatar.configure(fg_color=icon_bg)
        self._ed_avatar_lbl.configure(text=TYPE_SYMBOL.get(tipo,"?"), text_color=icon_fg)
        self._ed_title.configure(text=name)
        self._ed_sub.configure(text=f"Botón {idx+1}  ·  {tipo}")

        # Nombre — siempre visible
        self._ed_name.delete(0, "end")
        self._ed_name.insert(0, name)

        # Marcar todos los tabs como dirty
        for t in self._tab_names:
            self._tab_dirty[t] = True

        # Solo pintar el tab activo — los demás se pintan al cambiar de tab
        active = self._active_tab.get()
        self._paint_tab_content(active)

        self._switch_tab(active)

    def _paint_tab_content(self, tab_name):
        """Pinta solo el contenido del tab indicado si está dirty."""
        if not self._tab_dirty.get(tab_name, False):
            return
        self._tab_dirty[tab_name] = False

        C    = self.C
        idx  = self._sel_btn
        btns = self._buttons
        cfg  = btns[idx] if idx < len(btns) else {}
        tipo = cfg.get("action_type", ACTION_TYPES[0])
        val  = cfg.get("action_value", "")
        custom_color = cfg.get("custom_color", "")
        icon_path    = cfg.get("icon_path", "")

        if tab_name == "Acción":
            self._paint_pills(tipo)
            self._ed_help.configure(text=TYPE_HELP.get(tipo, ""))

            self._ed_val_entry.pack_forget()
            self._ed_val_text.pack_forget()
            self._ed_system_frame.pack_forget()

            if tipo == "text":
                self._ed_val_text.pack(fill="x")
                self._ed_val_text.delete("1.0", "end")
                self._ed_val_text.insert("1.0", val)
            elif tipo == "system":
                self._ed_system_frame.pack(fill="x")
                if val and val in SYSTEM_COMMANDS:
                    name_cmd, icon_cmd, _ = SYSTEM_COMMANDS[val]
                    self._ed_system_lbl.configure(
                        text=f"{icon_cmd}  {name_cmd}", text_color=C["text"])
                else:
                    self._ed_system_lbl.configure(
                        text="Ningún comando seleccionado", text_color=C["text_dim"])
            else:
                self._ed_val_entry.pack(fill="x")
                self._ed_val_entry.delete(0, "end")
                self._ed_val_entry.insert(0, val)

            if tipo == "macro":
                self._macro_frame.master.pack(fill="x", padx=12, pady=(8,0))
                try:
                    steps = json.loads(val) if val else []
                    n = len(steps)
                    if n == 0:
                        self._macro_preview_lbl.configure(text="Sin pasos configurados")
                    else:
                        names = [f"{TYPE_SYMBOL.get(s.get('type',''),'?')} {s.get('type','')} — {s.get('value','')[:20]}"
                                 for s in steps[:3]]
                        extra = f"  +{n-3} más" if n > 3 else ""
                        self._macro_preview_lbl.configure(text="\n".join(names) + extra)
                except Exception:
                    self._macro_preview_lbl.configure(text="Sin pasos configurados")
            else:
                self._macro_frame.master.pack_forget()

            self._script_out_frame.pack_forget()

        elif tab_name == "Apariencia":
            if custom_color:
                self._ed_color_preview.configure(fg_color=custom_color)
                self._ed_color_label.configure(text=custom_color)
            else:
                self._ed_color_preview.configure(fg_color=C["surface3"])
                self._ed_color_label.configure(text="Por defecto")

            if icon_path and os.path.exists(icon_path):
                img = self._load_img(icon_path, 28)
                if img:
                    self._ed_icon_preview.configure(image=img, text="")
                else:
                    self._ed_icon_preview.configure(image=None, text="Error")
            else:
                self._ed_icon_preview.configure(image=None, text="Sin imagen")

        elif tab_name == "Avanzado":
            key   = f"{self._profile['name']}/{idx}"
            stats = _stats_cache.get(key)
            today = datetime.date.today().isoformat()
            self._ed_stat_total.configure(text=str(stats.get("total", 0)))
            self._ed_stat_today.configure(text=str(stats.get("history",{}).get(today, 0)))

            sched_time = cfg.get("scheduled_time","")
            self._ed_sched_time.delete(0,"end")
            if sched_time:
                self._ed_sched_time.insert(0, sched_time)
            self._ed_sched_lbl.configure(
                text=f"Programado: {sched_time}" if sched_time else "Sin programar")

            hotkey = cfg.get("extra_hotkey","")
            self._ed_hotkey.delete(0,"end")
            if hotkey:
                self._ed_hotkey.insert(0, hotkey)


    def _paint_pills(self, tipo_activo):
        C = self.C
        for at, cell in self._ed_pills.items():
            active = (at == tipo_activo)
            icon_bg, icon_fg = self._tcolors(at)
            cell.configure(
                fg_color=icon_bg if active else C["surface3"],
                border_color=C["accent"] if active else C["border"],
                border_width=2 if active else 1)

    def _set_editor_type(self, tipo):
        self._editor_type = tipo
        self._paint_pills(tipo)
        self._tab_dirty["Acción"] = True
        self._switch_tab("Acción")

        self._ed_val_entry.pack_forget()
        self._ed_val_text.pack_forget()
        self._ed_system_frame.pack_forget()

        if tipo == "text":
            self._ed_val_text.pack(fill="x")
        elif tipo == "system":
            self._ed_system_frame.pack(fill="x")
        else:
            self._ed_val_entry.pack(fill="x")

        if tipo == "macro":
            self._macro_frame.master.pack(fill="x", padx=12, pady=(8,0))
        else:
            self._macro_frame.master.pack_forget()

        self._ed_help.configure(text=TYPE_HELP.get(tipo, ""))
        icon_bg, icon_fg = self._tcolors(tipo)
        self._ed_avatar.configure(fg_color=icon_bg)
        self._ed_avatar_lbl.configure(text=TYPE_SYMBOL.get(tipo,"?"), text_color=icon_fg)
        self._ed_sub.configure(text=f"Botón {self._sel_btn+1}  ·  {tipo}")

    def _pick_file(self):
        path = filedialog.askopenfilename(title="Seleccionar archivo")
        if path:
            self._ed_val_entry.delete(0, "end")
            self._ed_val_entry.insert(0, path)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        C = self.C
        bar = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0,
                           height=32, border_width=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=16)
        inner.pack_propagate(False)

        dot = ctk.CTkFrame(inner, fg_color=C["green"], width=6, height=6, corner_radius=3)
        dot.pack(side="left", pady=13)
        dot.pack_propagate(False)

        self._status_bar_lbl = ctk.CTkLabel(inner, text="",
                                            font=("Arial",11), text_color=C["text_dim"])
        self._status_bar_lbl.pack(side="left", padx=(6,0))

        ctk.CTkLabel(inner, text=f"v{VERSION}", font=("Arial",11),
                     text_color=C["text_dim"]).pack(side="right")

    def _paint_statusbar(self):
        p = self._profile
        self._status_bar_lbl.configure(
            text=f"Perfil: {p['name']}  ·  {p['cols']}×{p['rows']}")

    # ═══════════════════════════════════════════════════════════════════════════
    # ACCIONES
    # ═══════════════════════════════════════════════════════════════════════════

    def _select_btn(self, idx):
        if idx >= self._total():
            return
        prev = self._sel_btn
        self._sel_btn = idx
        self._paint_single_slot(prev)
        self._paint_single_slot(idx)
        self._paint_editor()

    def _switch_profile(self, idx):
        if idx == self._active_idx or idx >= len(self._data["profiles"]):
            return
        self._active_idx = idx
        self._sel_btn    = 0
        self._data["active"] = idx
        save_all(self._data)
        self._paint_profile_list()
        self._paint_sidebar_info()
        self._paint_grid(force=True)
        self._paint_editor()
        self._paint_statusbar()

    def _change_grid(self, cols, rows):
        n = cols * rows
        p = self._profile
        p["cols"] = cols
        p["rows"] = rows
        cur = p["buttons"]
        if len(cur) < n:
            cur.extend([{} for _ in range(n - len(cur))])
        p["buttons"] = cur[:n]
        self._sel_btn = 0
        save_all(self._data)
        self._paint_grid(force=True)
        self._paint_editor()
        self._paint_sidebar_info()
        self._paint_statusbar()

    def _save_current(self):
        idx  = self._sel_btn
        name = self._ed_name.get().strip() or f"Botón {idx+1}"
        tipo = self._editor_type

        PRESERVE_TYPES = {"macro", "system", "toggle", "confirm"}

        if tipo == "text":
            val = self._ed_val_text.get("1.0","end").strip()
        elif tipo in PRESERVE_TYPES:
            val = ""
        else:
            val = self._ed_val_entry.get().strip()

        existing = self._buttons[idx] if idx < len(self._buttons) else {}

        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})

        if tipo in PRESERVE_TYPES and not val:
            val = existing.get("action_value", "")

        self._profile["buttons"][idx] = {
            "name":         name,
            "action_type":  tipo,
            "action_value": val,
            "custom_color": existing.get("custom_color",""),
            "icon_path":    existing.get("icon_path",""),
        }

        ok = save_all(self._data)
        self._show_status("✓ Guardado" if ok else "✗ Error", ok)
        self._paint_single_slot(idx)
        self._paint_editor()
        self._paint_sidebar_info()

    def _test_action(self):
        idx  = self._sel_btn
        btns = self._buttons
        cfg  = btns[idx] if idx < len(btns) else {}
        ok   = execute_action(cfg, app=self)
        self._show_status("✓ Ejecutado" if ok else "✗ Sin configuración", ok)
        if ok and cfg.get("action_type"):
            show_toast(cfg.get("name","Botón"), "Acción ejecutada", self)

    def _show_status(self, msg, ok=True):
        self.status_var.set(msg)
        self._ed_status.configure(
            text_color=self.C["green"] if ok else self.C["red"])
        self.after(3000, lambda: self.status_var.set(""))

    # ── Gestión de perfiles ───────────────────────────────────────────────────

    def _new_profile(self):
        name = simpledialog.askstring("Nuevo perfil", "Nombre:", parent=self)
        if not name or not name.strip():
            return
        self._data["profiles"].append({
            "name": name.strip(),
            "emoji": EMOJIS[len(self._data["profiles"]) % len(EMOJIS)],
            "cols": 3, "rows": 3,
            "buttons": [{} for _ in range(9)],
        })
        self._active_idx = len(self._data["profiles"]) - 1
        self._data["active"] = self._active_idx
        self._sel_btn = 0
        save_all(self._data)
        self._paint_profile_list()
        self._paint_sidebar_info()
        self._paint_grid(force=True)
        self._paint_editor()
        self._paint_statusbar()

    def _profile_menu(self, idx):
        if idx >= len(self._data["profiles"]):
            return
        C = self.C
        menu = tk.Menu(self, tearoff=0,
                       bg=C["surface2"], fg=C["text"],
                       activebackground=C["accent_bg"],
                       activeforeground=C["text"], font=("Arial",11))
        menu.add_command(label="Renombrar",     command=lambda: self._rename_profile(idx))
        menu.add_command(label="Cambiar emoji", command=lambda: self._change_emoji(idx))
        menu.add_separator()
        menu.add_command(label="Duplicar",      command=lambda: self._duplicate_profile(idx))
        menu.add_separator()
        menu.add_command(label="Eliminar",      command=lambda: self._delete_profile(idx))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _rename_profile(self, idx):
        old = self._data["profiles"][idx]["name"]
        new = simpledialog.askstring("Renombrar","Nuevo nombre:",
                                     initialvalue=old, parent=self)
        if new and new.strip():
            self._data["profiles"][idx]["name"] = new.strip()
            save_all(self._data)
            self._paint_profile_list()
            if idx == self._active_idx:
                self._paint_grid()
                self._paint_statusbar()

    def _change_emoji(self, idx):
        e = simpledialog.askstring("Emoji",
            f"Disponibles: {' '.join(EMOJIS)}\nEscribí uno:", parent=self)
        if e and e.strip():
            self._data["profiles"][idx]["emoji"] = e.strip()
            save_all(self._data)
            self._paint_profile_list()
            if idx == self._active_idx:
                self._paint_grid()

    def _duplicate_profile(self, idx):
        clone = copy.deepcopy(self._data["profiles"][idx])
        clone["name"] += " (copia)"
        self._data["profiles"].insert(idx+1, clone)
        save_all(self._data)
        self._paint_profile_list()

    def _delete_profile(self, idx):
        if len(self._data["profiles"]) <= 1:
            messagebox.showwarning("Aviso","Debe quedar al menos un perfil.", parent=self)
            return
        name = self._data["profiles"][idx]["name"]
        if not messagebox.askyesno("Eliminar", f"¿Eliminar '{name}'?", parent=self):
            return
        self._data["profiles"].pop(idx)
        if self._active_idx >= len(self._data["profiles"]):
            self._active_idx = len(self._data["profiles"]) - 1
        self._data["active"] = self._active_idx
        self._sel_btn = 0
        save_all(self._data)
        self._paint_profile_list()
        self._paint_sidebar_info()
        self._paint_grid(force=True)
        self._paint_editor()
        self._paint_statusbar()

    # ── Tema ──────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        self._data["theme"] = self._theme
        ctk.set_appearance_mode("light" if self._theme == "light" else "dark")
        save_all(self._data)
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=self.C["bg"])
        # Invalidar snapshots al cambiar tema
        self._grid_snapshots = [None] * MAX_BUTTONS
        self._build_ui()

    # ── Serial ────────────────────────────────────────────────────────────────

    def _start_serial(self):
        threading.Thread(target=self._serial_loop, daemon=True).start()

    def _serial_loop(self):
        while True:
            port = detectar_arduino()
            if not port:
                self.after(0, lambda: self.arduino_var.set("Sin conexión"))
                time.sleep(2)
                continue
            try:
                self.after(0, lambda p=port: self.arduino_var.set(f"Arduino · {p}"))
                with serial.Serial(port, 9600, timeout=1) as ser:
                    while True:
                        if ser.in_waiting:
                            raw = ser.readline().decode(errors="ignore").strip()
                            if raw.isdigit():
                                idx = int(raw) - 1
                                if 0 <= idx < self._total():
                                    self.after(0, lambda i=idx: self._hw_press(i))
            except Exception as e:
                print(f"[serial] {e}")
                self.after(0, lambda: self.arduino_var.set("Reconectando..."))
                time.sleep(2)

    def _hw_press(self, idx):
        btns = self._buttons
        cfg  = btns[idx] if idx < len(btns) else {}
        ok   = execute_action(cfg, app=self)
        name = cfg.get("name", f"Botón {idx+1}")
        self.last_action.set(f"Botón {idx+1}  ·  {name}  {'✓' if ok else '✗'}")
        if ok and cfg.get("action_type"):
            # OPT: usa cache en RAM en vez de leer/escribir disco
            _stats_cache.record(self._profile["name"], idx, name)
            show_toast(name, "Acción ejecutada", self)


    # ── Tab system ────────────────────────────────────────────────────────────

    def _switch_tab(self, tab_name):
        C = self.C
        self._active_tab.set(tab_name)

        for name, btn in self._tab_btns.items():
            active = (name == tab_name)
            btn.configure(
                fg_color=C["surface"] if active else C["surface2"],
                text_color=C["text"] if active else C["text_dim"],
                font=("Arial", 11, "bold") if active else ("Arial", 11))

        tab_idx = self._tab_names.index(tab_name)
        def _draw_indicator():
            self._tab_canvas.update_idletasks()
            total_w = self._tab_canvas.winfo_width()
            if total_w < 10:
                return
            tab_w = total_w // len(self._tab_names)
            x0 = tab_idx * tab_w
            x1 = x0 + tab_w
            self._tab_canvas.delete("indicator")
            accent = THEMES[self._theme]["accent"]
            self._tab_canvas.create_rectangle(x0, 0, x1, 3, fill=accent,
                                              outline="", tags="indicator")
        self.after(10, _draw_indicator)

        # OPT: pintar contenido lazy del tab antes de mostrarlo
        self._paint_tab_content(tab_name)

        for w in self._page_accion_widgets:
            if tab_name == "Acción":
                w.pack(fill="x", padx=12, pady=(8,0))
            else:
                w.pack_forget()

        for w in self._page_apariencia_widgets:
            if tab_name == "Apariencia":
                w.pack(fill="x", padx=12, pady=(8,0))
            else:
                w.pack_forget()

        for w in self._page_avanzado_widgets:
            if tab_name == "Avanzado":
                w.pack(fill="x", padx=12, pady=(8,0))
            else:
                w.pack_forget()

        if tab_name == "Acción" and self._editor_type == "macro":
            self._macro_frame.master.pack(fill="x", padx=12, pady=(8,0))
        elif tab_name != "Acción":
            self._macro_frame.master.pack_forget()

    # ── Comandos de sistema ───────────────────────────────────────────────────

    def _open_system_picker(self):
        idx = self._sel_btn
        btns = self._buttons
        current = (btns[idx].get("action_value","") if idx < len(btns) else "")
        SystemCommandPicker(self, current,
                            on_select=lambda cmd: self._system_selected(cmd))

    def _system_selected(self, cmd):
        idx = self._sel_btn
        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})
        existing = self._profile["buttons"][idx]

        name_cmd = SYSTEM_COMMANDS[cmd][0] if cmd in SYSTEM_COMMANDS else cmd
        icon_cmd = SYSTEM_COMMANDS[cmd][1] if cmd in SYSTEM_COMMANDS else "⚙"

        self._profile["buttons"][idx] = {
            "name":         existing.get("name") or f"{icon_cmd} {name_cmd}",
            "action_type":  "system",
            "action_value": cmd,
            "custom_color": existing.get("custom_color",""),
            "icon_path":    existing.get("icon_path",""),
        }
        save_all(self._data)

        self._ed_name.delete(0,"end")
        self._ed_name.insert(0, self._profile["buttons"][idx]["name"])

        self._ed_system_lbl.configure(
            text=f"{icon_cmd}  {name_cmd}",
            text_color=self.C["text"])

        self._show_status(f"✓ Comando: {name_cmd}", True)
        self._paint_single_slot(idx)
        self._paint_sidebar_info()

    def _open_macro_builder(self):
        idx = self._sel_btn

        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})

        cfg = self._profile["buttons"][idx]

        if not cfg.get("name",""):
            cfg["name"] = f"Botón {idx+1}"

        cfg["action_type"] = "macro"

        current_steps = []
        try:
            val = cfg.get("action_value", "")
            if val:
                current_steps = json.loads(val)
        except Exception:
            current_steps = []

        btn_name = cfg.get("name", f"Botón {idx+1}")
        win = MacroBuilderWindow(self, btn_name, current_steps,
                                 on_save=lambda steps: self._macro_save_steps(idx, steps))
        win.grab_set()

    def _macro_save_steps(self, idx, steps):
        try:
            while len(self._profile["buttons"]) <= idx:
                self._profile["buttons"].append({})
            existing = self._profile["buttons"][idx]
            json_val = json.dumps(steps, ensure_ascii=False)
            self._profile["buttons"][idx] = {
                "name":         existing.get("name", f"Botón {idx+1}"),
                "action_type":  "macro",
                "action_value": json_val,
                "custom_color": existing.get("custom_color",""),
                "icon_path":    existing.get("icon_path",""),
            }
            ok = save_all(self._data)
            self._show_status(f"✓ Macro guardada — {len(steps)} pasos", True)
            self._sel_btn = idx
            self._editor_type = "macro"
            self._paint_editor()
            self._paint_single_slot(idx)
            self._paint_sidebar_info()
        except Exception as e:
            print(f"[macro] Error guardando: {e}")
            self._show_status(f"✗ Error: {e}", False)

    def _pick_script(self):
        path = filedialog.askopenfilename(
            title="Seleccionar script Python",
            filetypes=[("Python","*.py"),("Todos","*.*")],
            parent=self)
        if path:
            self._ed_val_entry.delete(0,"end")
            self._ed_val_entry.insert(0, path)

    # ── Color ─────────────────────────────────────────────────────────────────

    def _pick_color(self):
        idx     = self._sel_btn
        btns    = self._buttons
        current = (btns[idx].get("custom_color","") if idx < len(btns) else "") or "#5865f2"
        result  = colorchooser.askcolor(color=current, title="Color del botón", parent=self)
        if result and result[1]:
            self._apply_color(result[1])

    def _set_quick_color(self, color):
        self._apply_color(color)

    def _apply_color(self, color):
        idx = self._sel_btn
        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})
        self._profile["buttons"][idx]["custom_color"] = color
        save_all(self._data)
        # OPT: solo repintar lo necesario, marcar tab dirty
        self._tab_dirty["Apariencia"] = True
        self._paint_tab_content(self._active_tab.get())
        self._paint_single_slot(idx)

    def _clear_color(self):
        idx = self._sel_btn
        if idx < len(self._profile["buttons"]):
            self._profile["buttons"][idx]["custom_color"] = ""
            save_all(self._data)
            self._tab_dirty["Apariencia"] = True
            self._paint_tab_content(self._active_tab.get())
            self._paint_single_slot(idx)

    # ── Ícono ─────────────────────────────────────────────────────────────────

    def _pick_icon(self):
        path = filedialog.askopenfilename(
            title="Seleccionar ícono",
            filetypes=[("Imágenes","*.png *.ico *.jpg *.jpeg *.bmp"),
                       ("Todos","*.*")],
            parent=self)
        if not path:
            return
        idx = self._sel_btn
        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})
        self._img_cache.pop((path, 22), None)
        self._img_cache.pop((path, 28), None)
        self._profile["buttons"][idx]["icon_path"] = path
        save_all(self._data)
        self._tab_dirty["Apariencia"] = True
        self._paint_tab_content(self._active_tab.get())
        self._paint_single_slot(idx)

    def _clear_icon(self):
        idx = self._sel_btn
        if idx < len(self._profile["buttons"]):
            old = self._profile["buttons"][idx].get("icon_path","")
            if old:
                self._img_cache.pop((old, 22), None)
                self._img_cache.pop((old, 28), None)
            self._profile["buttons"][idx]["icon_path"] = ""
            save_all(self._data)
            self._tab_dirty["Apariencia"] = True
            self._paint_tab_content(self._active_tab.get())
            self._paint_single_slot(idx)

    # ── Tooltip ───────────────────────────────────────────────────────────────

    def _tooltip_show(self, event, idx):
        self._tooltip_hide()
        btns = self._buttons
        if idx >= len(btns):
            return
        cfg  = btns[idx]
        tipo = cfg.get("action_type","")
        val  = cfg.get("action_value","").strip()
        if not tipo or not val:
            return

        val_display = val if len(val) <= 60 else val[:60] + "…"
        text = f"{tipo}: {val_display}"
        C    = self.C

        win = tk.Toplevel(self)
        win.wm_overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg=C["surface"])

        frame = tk.Frame(win, bg=C["surface2"],
                         highlightbackground=C["border"],
                         highlightthickness=1)
        frame.pack()
        tk.Label(frame, text=text, bg=C["surface2"], fg=C["text_muted"],
                 font=("Arial",11), padx=10, pady=6).pack()

        win.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
        self._tooltip_win = win
        win.after(4000, self._tooltip_hide)

    def _tooltip_hide(self):
        if self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except Exception:
                pass
            self._tooltip_win = None

    # ── Copiar / Pegar ────────────────────────────────────────────────────────

    def _btn_context_menu(self, event, idx):
        self._select_btn(idx)
        C    = self.C
        btns = self._buttons
        cfg  = btns[idx] if idx < len(btns) else {}
        empty = not cfg.get("action_type","")

        menu = tk.Menu(self, tearoff=0,
                       bg=C["surface2"], fg=C["text"],
                       activebackground=C["accent_bg"],
                       activeforeground=C["text"],
                       font=("Arial",11))

        menu.add_command(
            label="Copiar botón",
            state="normal" if not empty else "disabled",
            command=lambda: self._copy_btn(idx))

        paste_label = (f"Pegar  ({self._btn_clipboard['name']})"
                       if self._btn_clipboard else "Pegar")
        menu.add_command(
            label=paste_label,
            state="normal" if self._btn_clipboard else "disabled",
            command=lambda: self._paste_btn(idx))

        menu.add_separator()
        menu.add_command(
            label="Limpiar botón",
            state="normal" if not empty else "disabled",
            command=lambda: self._clear_btn(idx))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_btn(self, idx):
        btns = self._buttons
        if idx < len(btns) and btns[idx].get("action_type",""):
            self._btn_clipboard = copy.deepcopy(btns[idx])
            self._show_status(f"✓ Copiado: {btns[idx].get('name','')}", True)

    def _paste_btn(self, idx):
        if not self._btn_clipboard:
            return
        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})
        self._profile["buttons"][idx] = copy.deepcopy(self._btn_clipboard)
        save_all(self._data)
        self._paint_single_slot(idx)
        self._paint_editor()
        self._paint_sidebar_info()
        self._show_status(f"✓ Pegado en botón {idx+1}", True)

    def _clear_btn(self, idx):
        if not messagebox.askyesno("Limpiar",
                f"¿Limpiar botón {idx+1}?", parent=self):
            return
        if idx < len(self._profile["buttons"]):
            old = self._profile["buttons"][idx].get("icon_path","")
            if old:
                self._img_cache.pop((old, 22), None)
                self._img_cache.pop((old, 28), None)
        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})
        self._profile["buttons"][idx] = {}
        save_all(self._data)
        self._paint_single_slot(idx)
        self._paint_editor()
        self._paint_sidebar_info()

    # ── Toggle persist ────────────────────────────────────────────────────────

    def _persist_toggle(self, cfg):
        idx = self._sel_btn
        if idx < len(self._profile["buttons"]):
            self._profile["buttons"][idx]["action_value"] = cfg.get("action_value","")
            save_all(self._data)

    def _show_script_output(self, output):
        self._script_out_box.configure(state="normal")
        self._script_out_box.delete("1.0","end")
        self._script_out_box.insert("1.0", output.strip() or "(sin salida)")
        self._script_out_box.configure(state="disabled")
        self._script_out_frame.pack(fill="x", pady=(6,0))

    # ── Atajos globales ───────────────────────────────────────────────────────

    def _start_hotkeys(self):
        if not KEYBOARD_OK:
            return
        try:
            for i in range(1, 10):
                keyboard.add_hotkey(f"ctrl+{i}",
                    lambda idx=i-1: self.after(0, lambda i=idx: self._hotkey_press(i)))
            self._hotkeys_active = True
        except Exception as e:
            print(f"[hotkeys] {e}")

    def _hotkey_press(self, idx):
        if idx < self._total():
            self._hw_press(idx)

    def _stop_hotkeys(self):
        if not KEYBOARD_OK or not self._hotkeys_active:
            return
        try:
            for i in range(1, 10):
                keyboard.remove_hotkey(f"ctrl+{i}")
            self._hotkeys_active = False
        except Exception:
            pass

    # ── System tray ───────────────────────────────────────────────────────────

    def _minimize_to_tray(self):
        if not PIL_ICON:
            self.iconify()
            return
        self.withdraw()
        try:
            img = Image.new("RGB", (64,64), color="#5865f2")
            from PIL import ImageDraw
            d = ImageDraw.Draw(img)
            d.rectangle([16,16,48,48], fill="#ffffff")

            menu = pystray.Menu(
                TrayItem("Abrir Stream Deck", self._restore_from_tray, default=True),
                pystray.Menu.SEPARATOR,
                TrayItem("Salir", self._quit_from_tray),
            )
            self._tray_icon = pystray.Icon("StreamDeck", img, "Stream Deck", menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"[tray] {e}")
            self.deiconify()

    def _restore_from_tray(self, icon=None, item=None):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        self.after(0, self.deiconify)

    def _quit_from_tray(self, icon=None, item=None):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.after(0, self._on_app_close)

    # ── Drag & drop ───────────────────────────────────────────────────────────

    def _drag_start(self, idx):
        if self._drag_source is None and idx < self._total():
            self._drag_source = idx

    def _drag_end(self, idx):
        src = self._drag_source
        self._drag_source = None
        if src is None or src == idx or idx >= self._total():
            return
        btns = self._profile["buttons"]
        while len(btns) <= max(src, idx):
            btns.append({})
        btns[src], btns[idx] = btns[idx], btns[src]
        save_all(self._data)
        # OPT: solo repintar los 2 slots intercambiados
        self._paint_single_slot(src)
        self._paint_single_slot(idx)
        self._paint_editor()
        self._show_status(f"✓ Botones {src+1} y {idx+1} intercambiados", True)

    # ── Exportar / Importar ───────────────────────────────────────────────────

    def _export_import_menu(self):
        C = self.C
        menu = tk.Menu(self, tearoff=0,
                       bg=C["surface2"], fg=C["text"],
                       activebackground=C["accent_bg"],
                       activeforeground=C["text"], font=("Arial",11))
        menu.add_command(label="Exportar perfil activo…", command=self._export_profile)
        menu.add_command(label="Importar perfil…",        command=self._import_profile)
        menu.add_separator()
        menu.add_command(label="Exportar todos los perfiles…", command=self._export_all)
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _export_profile(self):
        # OPT: flush antes de exportar para garantizar datos frescos
        _config_saver.flush_now()
        p    = self._profile
        path = filedialog.asksaveasfilename(
            title="Exportar perfil",
            defaultextension=".json",
            initialfile=f"{p['name']}.json",
            filetypes=[("JSON","*.json"),("Todos","*.*")],
            parent=self)
        if not path:
            return
        try:
            with open(path,"w",encoding="utf-8") as f:
                json.dump(p, f, indent=4, ensure_ascii=False)
            self._show_status(f"✓ Exportado: {os.path.basename(path)}", True)
        except Exception as e:
            self._show_status(f"✗ Error: {e}", False)

    def _export_all(self):
        _config_saver.flush_now()
        path = filedialog.asksaveasfilename(
            title="Exportar todos los perfiles",
            defaultextension=".json",
            initialfile="streamdeck_backup.json",
            filetypes=[("JSON","*.json"),("Todos","*.*")],
            parent=self)
        if not path:
            return
        try:
            with open(path,"w",encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
            self._show_status(f"✓ Backup exportado", True)
        except Exception as e:
            self._show_status(f"✗ Error: {e}", False)

    def _import_profile(self):
        path = filedialog.askopenfilename(
            title="Importar perfil",
            filetypes=[("JSON","*.json"),("Todos","*.*")],
            parent=self)
        if not path:
            return
        try:
            with open(path,"r",encoding="utf-8") as f:
                data = json.load(f)
            if "profiles" in data:
                if messagebox.askyesno("Importar backup",
                    "¿Reemplazar TODOS los perfiles con el backup?", parent=self):
                    self._data["profiles"] = data["profiles"]
                    self._active_idx = 0
                    self._data["active"] = 0
            else:
                required = {"name","cols","rows","buttons"}
                if not required.issubset(data.keys()):
                    raise ValueError("Formato de perfil inválido")
                self._data["profiles"].append(data)
                self._active_idx = len(self._data["profiles"]) - 1
                self._data["active"] = self._active_idx

            self._sel_btn = 0
            save_all(self._data)
            self._paint_profile_list()
            self._paint_sidebar_info()
            self._paint_grid(force=True)
            self._paint_editor()
            self._paint_statusbar()
            self._show_status("✓ Perfil importado", True)
        except Exception as e:
            self._show_status(f"✗ Error al importar: {e}", False)

    # ── Stats window ──────────────────────────────────────────────────────────

    def _show_stats_window(self):
        idx   = self._sel_btn
        btns  = self._buttons
        cfg   = btns[idx] if idx < len(btns) else {}
        name  = cfg.get("name", f"Botón {idx+1}")
        key   = f"{self._profile['name']}/{idx}"
        stats = _stats_cache.get(key)
        hist  = stats.get("history", {})

        C   = self.C
        win = tk.Toplevel(self)
        win.title(f"Historial — {name}")
        win.geometry("340x400")
        win.configure(bg=C["bg"])
        win.grab_set()

        hdr = tk.Frame(win, bg=C["surface2"], pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text=name, bg=C["surface2"], fg=C["text"],
                 font=("Arial",14,"bold")).pack()
        tk.Label(hdr, text=f"Total: {stats.get('total',0)} usos",
                 bg=C["surface2"], fg=C["text_muted"],
                 font=("Arial",11)).pack()

        frame = tk.Frame(win, bg=C["bg"])
        frame.pack(fill="both", expand=True, padx=16, pady=12)

        if not hist:
            tk.Label(frame, text="Sin historial aún",
                     bg=C["bg"], fg=C["text_dim"],
                     font=("Arial",12)).pack(expand=True)
        else:
            tk.Label(frame, text="Fecha", bg=C["bg"], fg=C["text_dim"],
                     font=("Arial",10,"bold"), width=14, anchor="w").grid(row=0,col=0,pady=2)
            tk.Label(frame, text="Usos", bg=C["bg"], fg=C["text_dim"],
                     font=("Arial",10,"bold"), width=8, anchor="e").grid(row=0,col=1,pady=2)

            for r, (date, count) in enumerate(
                    sorted(hist.items(), reverse=True)[:30], start=1):
                tk.Label(frame, text=date, bg=C["bg"], fg=C["text_muted"],
                         font=("Arial",11), anchor="w").grid(
                             row=r, column=0, sticky="w", pady=1)
                tk.Label(frame, text=str(count), bg=C["bg"], fg=C["green"],
                         font=("Arial",11,"bold"), anchor="e").grid(
                             row=r, column=1, sticky="e", pady=1)

        tk.Button(win, text="Cerrar", bg=C["accent"], fg="white",
                  font=("Arial",11), relief="flat", padx=12, pady=4,
                  command=win.destroy).pack(pady=(0,12))

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def _start_scheduler(self):
        def _run():
            while True:
                self._scheduler.run(blocking=False)
                time.sleep(10)
        self._sched_thread = threading.Thread(target=_run, daemon=True)
        self._sched_thread.start()

    def _load_scheduled_actions(self):
        for p in self._data["profiles"]:
            for idx, btn in enumerate(p.get("buttons",[])):
                t = btn.get("scheduled_time","")
                if t:
                    self._enqueue_schedule(p["name"], idx, btn, t)

    def _schedule_btn(self):
        idx  = self._sel_btn
        t    = self._ed_sched_time.get().strip()
        if not t:
            self._show_status("✗ Ingresá una hora (HH:MM)", False)
            return
        try:
            datetime.datetime.strptime(t, "%H:%M")
        except ValueError:
            self._show_status("✗ Formato inválido — usá HH:MM", False)
            return

        while len(self._profile["buttons"]) <= idx:
            self._profile["buttons"].append({})
        self._profile["buttons"][idx]["scheduled_time"] = t
        save_all(self._data)

        btn = self._profile["buttons"][idx]
        self._enqueue_schedule(self._profile["name"], idx, btn, t)
        self._ed_sched_lbl.configure(text=f"Programado: {t}")
        self._show_status(f"✓ Programado para las {t}", True)

    def _cancel_schedule(self):
        idx = self._sel_btn
        if idx < len(self._profile["buttons"]):
            self._profile["buttons"][idx]["scheduled_time"] = ""
            save_all(self._data)
        self._ed_sched_lbl.configure(text="Sin programar")
        self._show_status("✓ Programación cancelada", True)

    def _enqueue_schedule(self, profile_name, btn_idx, btn_cfg, time_str):
        try:
            now    = datetime.datetime.now()
            hh, mm = map(int, time_str.split(":"))
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=1)
            delay = (target - now).total_seconds()

            def _fire():
                btn = self._data["profiles"]
                for p in btn:
                    if p["name"] == profile_name:
                        b = p["buttons"][btn_idx] if btn_idx < len(p["buttons"]) else {}
                        if b.get("scheduled_time") == time_str:
                            self.after(0, lambda c=b: execute_action(c, app=self))
                            name = b.get("name", f"Botón {btn_idx+1}")
                            self.after(0, lambda n=name: show_toast(
                                n, f"Acción programada ({time_str})", self))
                            _stats_cache.record(profile_name, btn_idx, name)
                            self._enqueue_schedule(profile_name, btn_idx, b, time_str)

            self._scheduler.enter(delay, 1, _fire)
        except Exception as e:
            print(f"[scheduler] {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SELECTOR VISUAL DE COMANDOS DE SISTEMA
# ══════════════════════════════════════════════════════════════════════════════

class SystemCommandPicker(tk.Toplevel):
    def __init__(self, parent, current_cmd, on_select):
        super().__init__(parent)
        self._on_select = on_select
        self._selected  = current_cmd
        self._btn_refs  = {}

        C = THEMES[parent._theme]
        self._C = C
        self.configure(bg=C["bg"])
        self.title("Comandos de sistema")
        self.geometry("560x460")
        self.resizable(True, True)
        self.grab_set()
        self._build()

    def _build(self):
        C = self._C

        hdr = tk.Frame(self, bg=C["surface"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Elegí un comando",
                 bg=C["surface"], fg=C["text"],
                 font=("Arial",13,"bold"),
                 padx=14, pady=10).pack(side="left")
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        info = tk.Frame(self, bg=C["green_bg"])
        info.pack(fill="x")
        tk.Label(info,
                 text="  ⚠  Apagar y Reiniciar pedirán confirmación antes de ejecutar  ",
                 bg=C["green_bg"], fg=C["green"],
                 font=("Arial",9), pady=4).pack(side="left")

        outer = tk.Frame(self, bg=C["bg"])
        outer.pack(fill="both", expand=True, padx=14, pady=10)

        for group_name, cmd_keys in SYSTEM_GROUPS.items():
            group_f = tk.Frame(outer, bg=C["bg"])
            group_f.pack(fill="x", pady=(0,8))

            tk.Label(group_f, text=group_name.upper(),
                     bg=C["bg"], fg=C["text_dim"],
                     font=("Arial",9,"bold")).pack(anchor="w", pady=(0,4))

            btns_row = tk.Frame(group_f, bg=C["bg"])
            btns_row.pack(fill="x")

            for key in cmd_keys:
                if key not in SYSTEM_COMMANDS:
                    continue
                name, icon, _ = SYSTEM_COMMANDS[key]
                is_danger = key in SYSTEM_CONFIRM
                self._make_cmd_btn(btns_row, key, name, icon, is_danger)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        footer = tk.Frame(self, bg=C["surface"])
        footer.pack(fill="x")

        self._sel_lbl = tk.Label(footer, text="Ningún comando seleccionado",
                                 bg=C["surface"], fg=C["text_dim"],
                                 font=("Arial",10))
        self._sel_lbl.pack(side="left", padx=14, pady=8)

        tk.Button(footer, text="Cancelar",
                  bg=C["surface3"], fg=C["text_muted"],
                  font=("Arial",11), relief="flat",
                  padx=12, pady=5, cursor="hand2",
                  command=self.destroy).pack(side="right", padx=8, pady=8)

        self._ok_btn = tk.Button(footer, text="  ✓  Seleccionar  ",
                  bg=C["surface3"], fg=C["text_dim"],
                  font=("Arial",11,"bold"), relief="flat",
                  padx=12, pady=5, cursor="hand2",
                  command=self._confirm)
        self._ok_btn.pack(side="right", pady=8)

        if self._selected:
            self._highlight(self._selected)

    def _make_cmd_btn(self, parent, key, name, icon, is_danger):
        C = self._C
        is_sel = (key == self._selected)

        bg_border = C["accent"] if is_sel else ("#f87171" if is_danger else C["border"])
        frame = tk.Frame(parent, bg=bg_border, padx=1, pady=1)
        frame.pack(side="left", padx=3, pady=2)

        bg_inner = C["accent_bg"] if is_sel else ("#2a1010" if is_danger else C["surface2"])
        fg_text  = C["text"] if is_sel else ("#f87171" if is_danger else C["text_muted"])

        btn = tk.Button(frame,
                        text=f" {icon}  {name} ",
                        bg=bg_inner, fg=fg_text,
                        font=("Arial",10,"bold" if is_sel else "normal"),
                        relief="flat", padx=8, pady=6,
                        cursor="hand2",
                        command=lambda k=key: self._select(k))
        btn.pack()
        self._btn_refs[key] = (frame, btn)

    def _select(self, key):
        if self._selected and self._selected in self._btn_refs:
            self._unhighlight(self._selected)
        self._selected = key
        self._highlight(key)
        if key in SYSTEM_COMMANDS:
            name, icon, _ = SYSTEM_COMMANDS[key]
            self._sel_lbl.configure(
                text=f"Seleccionado: {icon}  {name}", fg=self._C["green"])
            self._ok_btn.configure(bg=self._C["accent"], fg="white")

    def _highlight(self, key):
        C = self._C
        if key not in self._btn_refs:
            return
        frame, btn = self._btn_refs[key]
        frame.configure(bg=C["accent"])
        btn.configure(bg=C["accent_bg"], fg=C["text"], font=("Arial",10,"bold"))

    def _unhighlight(self, key):
        C = self._C
        if key not in self._btn_refs:
            return
        is_danger = key in SYSTEM_CONFIRM
        frame, btn = self._btn_refs[key]
        frame.configure(bg="#f87171" if is_danger else C["border"])
        btn.configure(
            bg="#2a1010" if is_danger else C["surface2"],
            fg="#f87171" if is_danger else C["text_muted"],
            font=("Arial",10,"normal"))

    def _confirm(self):
        if self._selected:
            self._on_select(self._selected)
            self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCTOR VISUAL DE MACROS — OPTIMIZADO
# ══════════════════════════════════════════════════════════════════════════════

MACRO_TYPES = {
    "program": ("▶ Abrir programa",    "#1e2440", "#8890e0"),
    "url":     ("⊕ Abrir URL",         "#1a2520", "#4caf50"),
    "urls":    ("⊕ Abrir URLs",        "#1a2520", "#4caf50"),
    "file":    ("▤ Abrir archivo",     "#251e10", "#f59e0b"),
    "text":    ("✎ Pegar texto",       "#1e2a20", "#4ade80"),
    "script":  ("🐍 Ejecutar script",  "#1a2510", "#86efac"),
    "key":     ("⌨ Presionar tecla",   "#1a1020", "#c084fc"),
    "system":  ("⚙ Cmd. sistema",      "#0a1a2a", "#38bdf8"),
}


class MacroBuilderWindow(tk.Toplevel):
    """
    Constructor + Grabador visual de macros — OPTIMIZADO.
    
    Cambios vs v12.0:
    - Widget pool para la lista de pasos (evita destroy/recreate)
    - Debounce en trace_add para valor y delay
    - _render_rec usa pool de labels en vez de recrear
    """

    STEP_COLORS = {
        "program": ("#1e2440","#8890e0","▶ Programa"),
        "url":     ("#1a2520","#4caf50","⊕ URL"),
        "urls":    ("#1a2520","#4caf50","⊕ URLs"),
        "file":    ("#251e10","#f59e0b","▤ Archivo"),
        "text":    ("#1e2a20","#4ade80","✎ Texto"),
        "script":  ("#1a2510","#86efac","🐍 Script"),
        "key":     ("#1a1020","#c084fc","⌨ Tecla"),
        "click":   ("#1a2520","#4caf50","◉ Clic"),
    }

    KEY_PRESETS = [
        ("Copiar","ctrl+c"),("Pegar","ctrl+v"),("Cortar","ctrl+x"),
        ("Deshacer","ctrl+z"),("Guardar","ctrl+s"),("Sel. todo","ctrl+a"),
        ("Cerrar","alt+f4"),("Escritorio","win+d"),("Enter","enter"),
        ("Escape","esc"),("Tab","tab"),("Imprimir","ctrl+p"),
    ]

    # Pool sizes
    MAX_REC_ROWS  = 60
    MAX_STEP_CARDS = 40

    def __init__(self, parent, btn_name, initial_steps, on_save):
        super().__init__(parent)
        self._app    = parent
        self._on_save = on_save
        self._steps  = [self._clean_step(s) for s in initial_steps]
        self._drag_src = None

        self._recording   = False
        self._rec_steps   = []
        self._kb_listener = None
        self._ms_listener = None
        self._text_buf    = []
        self._fixed_delay = 0.3

        # OPT: debounce timers for trace callbacks
        self._val_debounce_timers = {}
        self._delay_debounce_timers = {}

        C = THEMES[parent._theme]
        self._C = C
        self.configure(bg=C["bg"])
        self.title(f"Macro: {btn_name}")
        self.geometry("580x640")
        self.minsize(460, 500)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()

    @staticmethod
    def _clean_step(s):
        return {
            "type":  s.get("type","key"),
            "value": s.get("value",""),
            "delay": float(s.get("delay", 0.3)),
        }

    def _step_color(self, tipo):
        return self.STEP_COLORS.get(tipo, ("#1e1f24","#888888","? Desconocido"))

    def _build(self):
        C = self._C

        # Topbar
        tb = tk.Frame(self, bg=C["surface"])
        tb.pack(fill="x")
        tk.Label(tb, text="⛓  Macro builder", bg=C["surface"],
                 fg=C["text"], font=("Arial",13,"bold"),
                 padx=14, pady=10).pack(side="left")
        self._total_lbl = tk.Label(tb, text="0 pasos",
                                   bg=C["surface"], fg=C["text_muted"],
                                   font=("Arial",11))
        self._total_lbl.pack(side="right", padx=14)
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        # ── GRABADOR ──────────────────────────────────────────────────────────
        rec_outer = tk.LabelFrame(self, text=" ⏺  Grabador automático ",
                                  bg=C["bg"], fg=C["text_muted"],
                                  font=("Arial",10), padx=10, pady=6,
                                  relief="flat",
                                  highlightbackground=C["border"],
                                  highlightthickness=1)
        rec_outer.pack(fill="x", padx=12, pady=(10,4))

        ctl = tk.Frame(rec_outer, bg=C["bg"])
        ctl.pack(fill="x")

        self._rec_btn = tk.Button(ctl,
            text="⏺  Iniciar grabación",
            bg="#c62828", fg="white",
            font=("Arial",11,"bold"), relief="flat",
            padx=12, pady=5, cursor="hand2",
            command=self._toggle_recording)
        self._rec_btn.pack(side="left", padx=(0,8))

        tk.Button(ctl, text="✕ Descartar",
                  bg=C["surface3"], fg=C["text_muted"],
                  font=("Arial",10), relief="flat",
                  padx=8, pady=5, cursor="hand2",
                  command=self._discard_rec).pack(side="left")

        delay_f = tk.Frame(ctl, bg=C["bg"])
        delay_f.pack(side="right")
        tk.Label(delay_f, text="Delay:", bg=C["bg"],
                 fg=C["text_dim"], font=("Arial",9)).pack(side="left")
        self._delay_var = tk.DoubleVar(value=3)
        self._delay_lbl = tk.Label(delay_f, text="0.3s",
                                   bg=C["bg"], fg=C["text"],
                                   font=("Arial",10,"bold"), width=4)
        self._delay_lbl.pack(side="right")
        sc = tk.Scale(delay_f, from_=0, to=30,
                      variable=self._delay_var, orient="horizontal",
                      length=90, bg=C["bg"], fg=C["text_dim"],
                      troughcolor=C["surface3"],
                      highlightthickness=0, showvalue=False,
                      command=self._on_delay_change)
        sc.pack(side="left", padx=4)

        self._rec_status = tk.Label(rec_outer, text="Presioná Iniciar y usá el teclado/mouse",
                                    bg=C["bg"], fg=C["text_dim"], font=("Arial",10))
        self._rec_status.pack(anchor="w", pady=(4,2))

        # OPT: Pool de filas para la lista de grabación
        rec_list = tk.Frame(rec_outer, bg=C["bg"])
        rec_list.pack(fill="x")
        self._rec_canvas = tk.Canvas(rec_list, bg=C["bg"],
                                     highlightthickness=0, height=80)
        rec_sb = tk.Scrollbar(rec_list, orient="vertical",
                              command=self._rec_canvas.yview)
        self._rec_frame = tk.Frame(self._rec_canvas, bg=C["bg"])
        self._rec_frame.bind("<Configure>", lambda e:
            self._rec_canvas.configure(
                scrollregion=self._rec_canvas.bbox("all")))
        self._rec_canvas.create_window((0,0), window=self._rec_frame, anchor="nw")
        self._rec_canvas.configure(yscrollcommand=rec_sb.set)
        rec_sb.pack(side="right", fill="y")
        self._rec_canvas.pack(side="left", fill="x", expand=True)

        # Pre-crear pool de filas para grabador
        self._rec_pool = []
        for _ in range(self.MAX_REC_ROWS):
            row = tk.Frame(self._rec_frame, bg=C["surface2"])
            num_lbl = tk.Label(row, text="", bg=C["surface2"],
                               fg=C["text_dim"], font=("Arial",8),
                               width=3, anchor="e")
            num_lbl.pack(side="left", padx=(4,0))
            type_lbl = tk.Label(row, text="", bg=C["surface3"],
                                fg=C["text_muted"], font=("Arial",10), padx=3)
            type_lbl.pack(side="left", padx=3, pady=2)
            text_lbl = tk.Label(row, text="", bg=C["surface2"],
                                fg=C["text_muted"], font=("Arial",9),
                                anchor="w")
            text_lbl.pack(side="left", fill="x", expand=True)
            del_btn = tk.Button(row, text="✕",
                                bg=C["surface2"], fg=C["text_dim"],
                                font=("Arial",9), relief="flat",
                                cursor="hand2", padx=3)
            del_btn.pack(side="right", padx=4)
            self._rec_pool.append({
                "row": row, "num": num_lbl, "type": type_lbl,
                "text": text_lbl, "del": del_btn
            })

        self._rec_empty_lbl = tk.Label(self._rec_frame,
                     text="(sin acciones grabadas)",
                     bg=C["bg"], fg=C["text_dim"],
                     font=("Arial",9))

        apply_row = tk.Frame(rec_outer, bg=C["bg"])
        apply_row.pack(fill="x", pady=(6,0))
        tk.Button(apply_row,
                  text="➕  Agregar grabación a la lista de pasos",
                  bg=C["accent"], fg="white",
                  font=("Arial",10,"bold"), relief="flat",
                  padx=10, pady=4, cursor="hand2",
                  command=self._apply_rec).pack(side="right")

        # ── LISTA DE PASOS ────────────────────────────────────────────────────
        steps_outer = tk.LabelFrame(self, text=" ☰  Pasos de la macro ",
                                    bg=C["bg"], fg=C["text_muted"],
                                    font=("Arial",10), padx=10, pady=6,
                                    relief="flat",
                                    highlightbackground=C["border"],
                                    highlightthickness=1)
        steps_outer.pack(fill="both", expand=True, padx=12, pady=(4,8))

        chips = tk.Frame(steps_outer, bg=C["bg"])
        chips.pack(fill="x", pady=(0,6))
        tk.Label(chips, text="Agregar:", bg=C["bg"],
                 fg=C["text_dim"], font=("Arial",9)).pack(side="left", padx=(0,4))
        for tipo, (bg_c, fg_c, label) in self.STEP_COLORS.items():
            if tipo == "click":
                continue
            tk.Button(chips, text=label,
                      bg=bg_c, fg=fg_c,
                      font=("Arial",8,"bold"), relief="flat",
                      padx=5, pady=2, cursor="hand2",
                      command=lambda t=tipo: self._add_step(t)
                      ).pack(side="left", padx=2)

        tk.Frame(steps_outer, bg=C["border"], height=1).pack(fill="x", pady=(0,4))

        presets_row = tk.Frame(steps_outer, bg=C["bg"])
        presets_row.pack(fill="x", pady=(0,6))
        tk.Label(presets_row, text="Teclas:", bg=C["bg"],
                 fg=C["text_dim"], font=("Arial",9)).pack(side="left", padx=(0,4))
        for label, combo in self.KEY_PRESETS:
            tk.Button(presets_row, text=label,
                      bg=C["surface3"], fg=C["text_muted"],
                      font=("Arial",8), relief="flat",
                      padx=4, pady=2, cursor="hand2",
                      command=lambda c=combo: self._add_key(c)
                      ).pack(side="left", padx=1)

        tk.Frame(steps_outer, bg=C["border"], height=1).pack(fill="x", pady=(0,4))

        list_f = tk.Frame(steps_outer, bg=C["bg"])
        list_f.pack(fill="both", expand=True)
        self._steps_canvas = tk.Canvas(list_f, bg=C["bg"], highlightthickness=0)
        steps_sb = tk.Scrollbar(list_f, orient="vertical",
                                command=self._steps_canvas.yview)
        self._steps_frame = tk.Frame(self._steps_canvas, bg=C["bg"])
        self._steps_frame.bind("<Configure>", lambda e:
            self._steps_canvas.configure(
                scrollregion=self._steps_canvas.bbox("all")))
        self._steps_canvas.create_window((0,0), window=self._steps_frame, anchor="nw")
        self._steps_canvas.configure(yscrollcommand=steps_sb.set)
        steps_sb.pack(side="right", fill="y")
        self._steps_canvas.pack(side="left", fill="both", expand=True)

        self._steps_canvas.bind("<MouseWheel>", lambda e:
            self._steps_canvas.yview_scroll(int(-1*(e.delta/120)),"units"))
        self._steps_frame.bind("<MouseWheel>", lambda e:
            self._steps_canvas.yview_scroll(int(-1*(e.delta/120)),"units"))

        self._steps_empty_lbl = tk.Label(self._steps_frame,
                     text="Sin pasos. Usá el grabador o los chips de arriba.",
                     bg=C["bg"], fg=C["text_dim"],
                     font=("Arial",10))

        # Footer
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        footer = tk.Frame(self, bg=C["surface"])
        footer.pack(fill="x")
        self._footer_status = tk.Label(footer, text="",
                                       bg=C["surface"], fg=C["green"],
                                       font=("Arial",10))
        self._footer_status.pack(side="left", padx=14, pady=8)
        tk.Button(footer, text="Cancelar",
                  bg=C["surface3"], fg=C["text_muted"],
                  font=("Arial",11), relief="flat",
                  padx=14, pady=6, cursor="hand2",
                  command=self._on_close).pack(side="right", padx=8, pady=6)
        tk.Button(footer, text="  💾  Guardar macro  ",
                  bg=C["accent"], fg="white",
                  font=("Arial",11,"bold"), relief="flat",
                  padx=14, pady=6, cursor="hand2",
                  command=self._save).pack(side="right", pady=6)

        self._render_steps()
        self._render_rec()

    # ══ Grabador ══════════════════════════════════════════════════════════════

    def _on_delay_change(self, val):
        d = round(float(val)/10, 1)
        self._fixed_delay = d
        self._delay_lbl.configure(text=f"{d}s")

    def _toggle_recording(self):
        if self._recording:
            self._stop_rec()
        else:
            self._start_rec()

    def _start_rec(self):
        if self._kb_listener:
            try: self._kb_listener.stop()
            except Exception: pass
            self._kb_listener = None
        if self._ms_listener:
            try: self._ms_listener.stop()
            except Exception: pass
            self._ms_listener = None
        self._recording = True
        self._rec_steps = []
        self._text_buf  = []
        self._rec_btn.configure(
            text="■  Detener grabación",
            bg="#1a2520", fg="#f87171")
        self._rec_status.configure(
            text="● GRABANDO — usá el teclado y el mouse normalmente",
            fg="#f87171")
        self._blink()
        threading.Thread(target=self._start_listeners, daemon=True).start()

    def _blink(self):
        if not self._recording:
            return
        try:
            if not self.winfo_exists():
                return
            c = self._rec_status.cget("fg")
            self._rec_status.configure(fg="#f87171" if c=="#1a0a0a" else "#1a0a0a")
            self.after(500, self._blink)
        except Exception:
            pass

    def _start_listeners(self):
        if not PYNPUT_OK:
            self.after(0, lambda: self._rec_status.configure(
                text="⚠ instala pynput:  pip install pynput",
                fg=self._C["red"]))
            if KEYBOARD_OK:
                keyboard.hook(self._kb_fallback)
            return
        self._kb_listener = _pynput_kb.Listener(
            on_press=self._on_key, suppress=False)
        self._ms_listener = _pynput_mouse.Listener(
            on_click=self._on_click)
        self._kb_listener.start()
        self._ms_listener.start()

    def _kb_fallback(self, event):
        if not self._recording:
            keyboard.unhook(self._kb_fallback)
            return
        if event.event_type == "down":
            self._add_rec_key(event.name)

    def _stop_rec(self):
        self._recording = False
        self._flush_text()
        if self._kb_listener:
            try: self._kb_listener.stop()
            except Exception: pass
            self._kb_listener = None
        if self._ms_listener:
            try: self._ms_listener.stop()
            except Exception: pass
            self._ms_listener = None
        n = len(self._rec_steps)
        self._rec_btn.configure(
            text="⏺  Iniciar grabación",
            bg="#c62828", fg="white")
        self._rec_status.configure(
            text=f"✓ Grabación detenida — {n} {'acción' if n==1 else 'acciones'} capturadas",
            fg=self._C["green"])
        self._render_rec()

    def _discard_rec(self):
        if self._recording:
            self._stop_rec()
        self._rec_steps = []
        self._render_rec()
        self._rec_status.configure(
            text="Grabación descartada", fg=self._C["text_dim"])

    def _on_key(self, key):
        if not self._recording:
            return False
        try:
            ch = key.char
            if ch and ch.isprintable():
                self._text_buf.append(ch)
                self.after(0, self._render_rec)
                return
        except AttributeError:
            pass

        self._flush_text()

        try:
            kname = key.name
        except AttributeError:
            kname = str(key).replace("Key.", "")

        MODIFIERS = {"ctrl_l","ctrl_r","shift_l","shift_r",
                     "alt_l","alt_r","cmd_l","cmd_r","alt_gr"}
        if kname.lower() in MODIFIERS:
            return

        kname = self._norm_key(kname)
        if kname:
            self._add_rec_key(kname)

    def _on_click(self, x, y, button, pressed):
        if not self._recording or not pressed:
            return
        self._flush_text()
        btn_name = "izquierdo" if "left" in str(button) else "derecho"
        self._rec_steps.append({
            "type":  "click",
            "value": f"{x},{y}",
            "delay": self._fixed_delay,
            "_label": f"Clic {btn_name}  ({x}, {y})",
        })
        try:
            self.after(0, self._render_rec)
        except Exception:
            pass

    def _flush_text(self):
        if not self._text_buf:
            return
        text = "".join(self._text_buf)
        self._text_buf = []
        if text.strip():
            short = text[:40] + ("..." if len(text)>40 else "")
            self._rec_steps.append({
                "type":  "text",
                "value": text,
                "delay": self._fixed_delay,
                "_label": f"Tipeo: \"{short}\"",
            })

    def _add_rec_key(self, kname):
        if not kname:
            return
        self._rec_steps.append({
            "type":  "key",
            "value": kname,
            "delay": self._fixed_delay,
            "_label": f"Tecla: {kname}",
        })
        try:
            self.after(0, self._render_rec)
        except Exception:
            pass

    def _norm_key(self, raw):
        MAP = {
            "ctrl_l":"ctrl","ctrl_r":"ctrl",
            "shift_l":"shift","shift_r":"shift",
            "alt_l":"alt","alt_r":"alt","alt_gr":"alt",
            "cmd_l":"win","cmd_r":"win","cmd":"win",
            "caps_lock":"caps lock","num_lock":"num lock",
            "scroll_lock":"scroll lock","print_screen":"print screen",
            "pause":"pause","insert":"insert",
            "backspace":"backspace","delete":"del",
            "enter":"enter","return":"enter",
            "space":"space","tab":"tab",
            "escape":"esc",
            "up":"up","down":"down","left":"left","right":"right",
            "home":"home","end":"end",
            "page_up":"page up","page_down":"page down",
            "f1":"f1","f2":"f2","f3":"f3","f4":"f4",
            "f5":"f5","f6":"f6","f7":"f7","f8":"f8",
            "f9":"f9","f10":"f10","f11":"f11","f12":"f12",
        }
        normalized = MAP.get(raw.lower(), raw.lower())
        if normalized.startswith("<") and normalized.endswith(">"):
            return ""
        return normalized

    # ══════════════════════════════════════════════════════════════════════════
    # OPT 6: _render_rec con pool — .configure() en vez de destroy/recreate
    # ══════════════════════════════════════════════════════════════════════════

    def _render_rec(self):
        C = self._C
        items = list(self._rec_steps)
        if self._text_buf:
            items.append({"type":"text","value":"".join(self._text_buf),
                         "_label":f'Tipeo: "{"".join(self._text_buf)}"',
                         "_live":True})

        if not items:
            # Ocultar pool, mostrar empty label
            for p in self._rec_pool:
                p["row"].pack_forget()
            self._rec_empty_lbl.pack(padx=10, pady=4)
            return

        self._rec_empty_lbl.pack_forget()

        for idx, p in enumerate(self._rec_pool):
            if idx < len(items):
                s     = items[idx]
                tipo  = s.get("type","key")
                label = s.get("_label", f"{tipo}: {s.get('value','')}")
                live  = s.get("_live", False)
                bg_c, fg_c, _ = self._step_color(tipo)

                row_bg = C["accent_bg"] if live else C["surface2"]
                p["row"].configure(bg=row_bg)
                p["num"].configure(text=str(idx+1), bg=row_bg)
                p["type"].configure(text=_[0] if _ else "?", bg=bg_c, fg=fg_c)
                p["text"].configure(
                    text=label, bg=row_bg,
                    fg=C["accent"] if live else C["text_muted"],
                    font=("Arial",9,"italic" if live else "normal"))
                if live:
                    p["del"].pack_forget()
                else:
                    p["del"].configure(bg=row_bg,
                        command=lambda i=idx: self._remove_rec(i))
                    p["del"].pack(side="right", padx=4)
                p["row"].pack(fill="x", pady=1, padx=2)
            else:
                p["row"].pack_forget()

        self._rec_canvas.after(30, lambda:
            self._rec_canvas.yview_moveto(1.0))

    def _remove_rec(self, idx):
        if idx < len(self._rec_steps):
            self._rec_steps.pop(idx)
            self._render_rec()

    def _apply_rec(self):
        self._flush_text()
        if not self._rec_steps:
            self._footer_status.configure(
                text="No hay acciones grabadas todavía", fg=self._C["red"])
            self.after(3000, lambda: self._footer_status.configure(text=""))
            return
        for s in self._rec_steps:
            self._steps.append(self._clean_step(s))
        n = len(self._rec_steps)
        self._rec_steps = []
        self._render_rec()
        self._render_steps()
        self._footer_status.configure(
            text=f"✓ {n} pasos agregados", fg=self._C["green"])
        self.after(3000, lambda: self._footer_status.configure(text=""))

    # ══ Pasos manuales — con destroy/recreate (necesario por widgets dinámicos)
    # Pero con debounce en los trace callbacks ═════════════════════════════════

    def _add_step(self, tipo):
        self._steps.append({"type":tipo,"value":"","delay":self._fixed_delay})
        self._render_steps()
        self._steps_canvas.after(50, lambda:
            self._steps_canvas.yview_moveto(1.0))

    def _add_key(self, combo):
        self._steps.append({"type":"key","value":combo,"delay":self._fixed_delay})
        self._render_steps()
        self._steps_canvas.after(50, lambda:
            self._steps_canvas.yview_moveto(1.0))

    def _render_steps(self):
        C = self._C
        # Cancelar todos los debounce timers pendientes
        for timer_id in self._val_debounce_timers.values():
            self.after_cancel(timer_id)
        self._val_debounce_timers.clear()
        for timer_id in self._delay_debounce_timers.values():
            self.after_cancel(timer_id)
        self._delay_debounce_timers.clear()

        for w in self._steps_frame.winfo_children():
            w.destroy()

        n = len(self._steps)
        self._total_lbl.configure(
            text=f"{n} {'paso' if n==1 else 'pasos'}")

        if n == 0:
            self._steps_empty_lbl = tk.Label(self._steps_frame,
                         text="Sin pasos. Usá el grabador o los chips de arriba.",
                         bg=C["bg"], fg=C["text_dim"],
                         font=("Arial",10))
            self._steps_empty_lbl.pack(padx=14, pady=10)
            return

        for i, step in enumerate(self._steps):
            self._build_card(i, step)

    def _build_card(self, i, step):
        C    = self._C
        tipo = step.get("type","key")
        bg_c, fg_c, type_label = self._step_color(tipo)

        card = tk.Frame(self._steps_frame, bg=C["surface2"], pady=0)
        card.pack(fill="x", pady=2, padx=2)

        hdr = tk.Frame(card, bg=C["surface2"])
        hdr.pack(fill="x", padx=8, pady=(5,0))

        drag = tk.Label(hdr, text="⋮⋮", bg=C["surface2"],
                        fg=C["text_dim"], font=("Arial",11), cursor="fleur")
        drag.pack(side="left", padx=(0,4))
        tk.Label(hdr, text=str(i+1), bg=bg_c, fg=fg_c,
                 font=("Arial",9,"bold"), padx=4, pady=1
                 ).pack(side="left", padx=(0,4))
        tk.Label(hdr, text=type_label, bg=bg_c, fg=fg_c,
                 font=("Arial",9,"bold"), padx=6, pady=1
                 ).pack(side="left")

        tk.Button(hdr, text="✕",
                  bg=C["surface2"], fg=C["text_dim"],
                  font=("Arial",9), relief="flat", cursor="hand2", padx=3,
                  command=lambda idx=i: self._remove_step(idx)
                  ).pack(side="right")
        tk.Button(hdr, text="↓",
                  bg=C["surface2"], fg=C["text_dim"],
                  font=("Arial",9), relief="flat", cursor="hand2", padx=3,
                  command=lambda idx=i: self._move(idx, 1)
                  ).pack(side="right")
        tk.Button(hdr, text="↑",
                  bg=C["surface2"], fg=C["text_dim"],
                  font=("Arial",9), relief="flat", cursor="hand2", padx=3,
                  command=lambda idx=i: self._move(idx, -1)
                  ).pack(side="right")
        tk.Button(hdr, text="⧉",
                  bg=C["surface2"], fg=C["text_dim"],
                  font=("Arial",9), relief="flat", cursor="hand2", padx=3,
                  command=lambda idx=i: self._dup(idx)
                  ).pack(side="right", padx=(0,4))

        body = tk.Frame(card, bg=C["surface2"])
        body.pack(fill="x", padx=10, pady=(3,7))

        vrow = tk.Frame(body, bg=C["surface2"])
        vrow.pack(fill="x", pady=1)
        tk.Label(vrow, text="Valor:", bg=C["surface2"],
                 fg=C["text_dim"], font=("Arial",9), width=6,
                 anchor="w").pack(side="left")

        if tipo == "system":
            raw_val = step.get("value","")
            display = raw_val
            if raw_val in SYSTEM_COMMANDS:
                ic, nm = SYSTEM_COMMANDS[raw_val][1], SYSTEM_COMMANDS[raw_val][0]
                display = f"{ic} {nm}"
            tk.Label(vrow, text=display, bg=C["surface2"],
                     fg=C["text"], font=("Arial",10), anchor="w"
                     ).pack(side="left", fill="x", expand=True)
            vvar = tk.StringVar(value=raw_val)
        else:
            vvar = tk.StringVar(value=step.get("value",""))
            e = tk.Entry(vrow, textvariable=vvar,
                         bg=C["surface3"], fg=C["text"],
                         insertbackground=C["text"],
                         font=("Arial",10), relief="flat", bd=0)
            e.pack(side="left", fill="x", expand=True, ipady=3, padx=(0,4))
            if tipo in ("program","file","script"):
                tk.Button(vrow, text="📂",
                          bg=C["surface3"], fg=C["text_muted"],
                          font=("Arial",10), relief="flat",
                          cursor="hand2", padx=3,
                          command=lambda idx=i, vv=vvar: self._browse(idx,vv)
                          ).pack(side="left")

        # OPT: debounced trace para valor
        vvar.trace_add("write",
            lambda *a, idx=i, vv=vvar: self._debounced_update_val(idx, vv))

        drow = tk.Frame(body, bg=C["surface2"])
        drow.pack(fill="x", pady=1)
        tk.Label(drow, text="Espera:", bg=C["surface2"],
                 fg=C["text_dim"], font=("Arial",9), width=6,
                 anchor="w").pack(side="left")
        dvar = tk.StringVar(value=str(step.get("delay",0.3)))
        tk.Entry(drow, textvariable=dvar,
                 bg=C["surface3"], fg=C["text"],
                 insertbackground=C["text"],
                 font=("Arial",10), relief="flat", bd=0, width=5
                 ).pack(side="left", ipady=3, padx=(0,6))
        tk.Label(drow, text="seg antes del siguiente paso",
                 bg=C["surface2"], fg=C["text_dim"],
                 font=("Arial",9)).pack(side="left")

        # OPT: debounced trace para delay
        dvar.trace_add("write",
            lambda *a, idx=i, dv=dvar: self._debounced_update_delay(idx, dv))

        for w in [drag]:
            w.bind("<ButtonPress-1>",   lambda e, idx=i: self._ds(idx))
            w.bind("<ButtonRelease-1>", lambda e, idx=i: self._de(idx))

    # ── OPT: Debounced trace callbacks ────────────────────────────────────────

    def _debounced_update_val(self, idx, vvar):
        """Actualiza el valor del paso con debounce de 150ms."""
        if idx in self._val_debounce_timers:
            self.after_cancel(self._val_debounce_timers[idx])
        self._val_debounce_timers[idx] = self.after(
            150, lambda: self._update_val(idx, vvar.get()))

    def _debounced_update_delay(self, idx, dvar):
        """Actualiza el delay del paso con debounce de 150ms."""
        if idx in self._delay_debounce_timers:
            self.after_cancel(self._delay_debounce_timers[idx])
        self._delay_debounce_timers[idx] = self.after(
            150, lambda: self._update_delay(idx, dvar.get()))

    def _remove_step(self, idx):
        self._steps.pop(idx); self._render_steps()

    def _move(self, idx, d):
        ni = idx+d
        if 0 <= ni < len(self._steps):
            self._steps[idx], self._steps[ni] = self._steps[ni], self._steps[idx]
            self._render_steps()

    def _dup(self, idx):
        self._steps.insert(idx+1, dict(self._steps[idx]))
        self._render_steps()

    def _update_val(self, idx, v):
        if idx < len(self._steps):
            self._steps[idx]["value"] = v

    def _update_delay(self, idx, v):
        if idx < len(self._steps):
            try: self._steps[idx]["delay"] = max(0.0, float(v))
            except ValueError: pass

    def _browse(self, idx, vvar):
        tipo = self._steps[idx].get("type","")
        ftypes = [("Python","*.py"),("Todos","*.*")] if tipo=="script" else [("Todos","*.*")]
        path = filedialog.askopenfilename(parent=self, filetypes=ftypes)
        if path:
            vvar.set(path)
            self._steps[idx]["value"] = path

    def _ds(self, idx): self._drag_src = idx
    def _de(self, idx):
        if self._drag_src is not None and self._drag_src != idx:
            m = self._steps.pop(self._drag_src)
            self._steps.insert(idx, m)
            self._render_steps()
        self._drag_src = None

    # ══ Guardar ═══════════════════════════════════════════════════════════════

    def _save(self):
        if not self._steps:
            self._footer_status.configure(
                text="Agregá al menos un paso", fg=self._C["red"])
            self.after(3000, lambda: self._footer_status.configure(text=""))
            return
        NEED = {"program","url","urls","file","text","script","key","api"}
        empty = [i+1 for i,s in enumerate(self._steps)
                 if s.get("type") in NEED and not s.get("value","").strip()]
        if empty:
            nums = ", ".join(str(p) for p in empty)
            self._footer_status.configure(
                text=f"Paso{'s' if len(empty)>1 else ''} {nums}: falta el valor",
                fg=self._C["red"])
            self.after(4000, lambda: self._footer_status.configure(text=""))
            return
        clean = [self._clean_step(s) for s in self._steps]
        self._on_save(clean)
        self.destroy()

    def _on_close(self):
        self._recording = False
        for l in [self._kb_listener, self._ms_listener]:
            if l:
                try: l.stop()
                except Exception: pass
        try:
            self._steps_canvas.unbind("<MouseWheel>")
            self._steps_frame.unbind("<MouseWheel>")
        except Exception:
            pass
        # Cancelar debounce timers
        for timer_id in self._val_debounce_timers.values():
            try: self.after_cancel(timer_id)
            except Exception: pass
        for timer_id in self._delay_debounce_timers.values():
            try: self.after_cancel(timer_id)
            except Exception: pass
        self.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = StreamDeckApp()
    app.mainloop()