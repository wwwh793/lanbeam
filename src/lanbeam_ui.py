# -*- coding: utf-8 -*-
"""LanBeam 界面层：只做展示与交互，所有网络逻辑在 lanbeam_core。"""

import ctypes
import os
import queue
import sys
import threading
import time
import webbrowser
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk

import handoff
import shellmenu
import startup
from lanbeam_core import (APP_NAME, DISCOVERY_PORT, VERSION, Core, Peer, human,
                          save_config, send_batch, TransferControl,
                          TransferCancelled)
from lanbeam_instance import ShowListener
from lanbeam_tray import Tray
from ui_style import RADIUS

# v1.6.4 起只有一个界面：v1.5.3 的 beta 视觉转正，两版不再维护两套皮肤
LIGHT = {
    "bg": "#F4F6FB", "card": "#FFFFFF", "border": "#E4E9F2",
    "text": "#101828", "muted": "#667085", "soft": "#EEF4FF",
    "trough": "#E9EEF6",
}
DARK = {
    "bg": "#0A0E14", "card": "#121821", "border": "#1F2836",
    "text": "#E8EEF8", "muted": "#8A94A6", "soft": "#16202F",
    "trough": "#1B2433",
}
ACCENT = "#4C8DFF"
ACCENT_DARK = "#2F6BFF"
ACRYLIC = {
    "bg": "#0D131D", "card": "#1A2230", "border": "#2E3A4E",
    "text": "#EAF1FB", "muted": "#94A1B8", "soft": "#243149",
    "trough": "#202B40",
}
PROJECT_URL = "https://wwwh793.github.io/lanbeam/"
OK = "#12A594"
WARN = "#E5484D"

BG = LIGHT["bg"]
CARD = LIGHT["card"]
BORDER = LIGHT["border"]
TEXT = LIGHT["text"]
MUTED = LIGHT["muted"]
SOFT = LIGHT["soft"]
TROUGH = LIGHT["trough"]


SCALE = 1.0


def enable_dpi_awareness() -> float:
    """开 DPI 感知，返回缩放比（96dpi=1.0）。"""
    global SCALE
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    SCALE = max(1.0, min(3.0, dpi / 96.0))
    return SCALE


def S(v: float) -> int:
    return int(round(v * SCALE))


def rad() -> int:
    """全界面统一圆角：逻辑像素 RADIUS × DPI 缩放。"""
    return max(2, S(RADIUS))


def set_dark_titlebar(win, dark: bool) -> None:
    try:
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                      ctypes.sizeof(value))
    except Exception:
        pass


def set_backdrop(win, acrylic: bool) -> None:
    """Windows 11 的 Mica/亚克力背景（仅影响窗口框架区域）。"""
    try:
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        value = ctypes.c_int(3 if acrylic else 1)
        dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(value),
                                  ctypes.sizeof(value))
    except Exception:
        pass


def detect_system_theme() -> str:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if val else "dark"
    except Exception:
        return "light"


def apply_theme(name: str) -> None:
    global BG, CARD, BORDER, TEXT, MUTED, SOFT, TROUGH
    if name == "acrylic":
        p = ACRYLIC
    else:
        p = DARK if name == "dark" else LIGHT
    BG = p["bg"]
    CARD = p["card"]
    BORDER = p["border"]
    TEXT = p["text"]
    MUTED = p["muted"]
    SOFT = p["soft"]
    TROUGH = p["trough"]

F_UI = ("Microsoft YaHei UI", 10)
F_SMALL = ("Microsoft YaHei UI", 9)
F_BOLD = ("Microsoft YaHei UI", 10, "bold")
F_TITLE = ("Microsoft YaHei UI", 19, "bold")
F_BIG = ("Microsoft YaHei UI", 11, "bold")


def asset_path(name: str) -> str:
    """打包后用 _MEIPASS，开发时依次找脚本目录、素材、成品。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / name
        if p.exists():
            return str(p)
    here = Path(__file__).resolve().parent
    for cand in (here / name, here.parent / "素材" / name, here.parent / "成品" / name):
        if cand.exists():
            return str(cand)
    return ""


def set_taskbar_identity() -> None:
    """让任务栏认自己的图标，而不是 python.exe 的。"""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Moyuli.LanBeam.Desktop.1")
    except Exception:
        pass


def _round_rect(c: tk.Canvas, x0, y0, x1, y1, r, fill, outline=""):
    """圆角矩形：先填色，再单独描边。

    描边必须用 style=ARC 的圆弧；默认的 PIESLICE 会顺带把扇形两条半径
    也描出来，那两道线会把圆角切出“台阶”。
    """
    r = max(1, int(round(r)))
    arcs = ((x0, y0, 90), (x1 - 2 * r, y0, 0),
            (x0, y1 - 2 * r, 180), (x1 - 2 * r, y1 - 2 * r, 270))
    if fill:
        for ax, ay, start in arcs:
            c.create_arc(ax, ay, ax + 2 * r, ay + 2 * r, start=start,
                         extent=90, fill=fill, outline=fill)
        c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=fill)
        c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill, outline=fill)
    if outline:
        for ax, ay, start in arcs:
            c.create_arc(ax, ay, ax + 2 * r, ay + 2 * r, start=start,
                         extent=90, style="arc", outline=outline)
        c.create_line(x0 + r, y0, x1 - r, y0, fill=outline)
        c.create_line(x0 + r, y1, x1 - r, y1, fill=outline)
        c.create_line(x0, y0 + r, x0, y1 - r, fill=outline)
        c.create_line(x1, y0 + r, x1, y1 - r, fill=outline)


def tree_size(p: Path) -> int:
    """文件或文件夹的总字节数，用来给「待发送」估个大小。"""
    try:
        if p.is_file():
            return p.stat().st_size
        total = 0
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                continue
        return total
    except OSError:
        return 0


def _pill(c: tk.Canvas, x0, y0, x1, y1, fill):
    """两端半圆的胶囊，进度条和开关用；比 create_arc 拼角干净。"""
    h = max(2, y1 - y0)
    r = h / 2.0
    if x1 - x0 < h:
        x1 = x0 + h
    c.create_oval(x0, y0, x0 + h, y1, fill=fill, outline="")
    c.create_oval(x1 - h, y0, x1, y1, fill=fill, outline="")
    c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline="")


class RoundButton(tk.Canvas):
    def __init__(self, master, text, command, kind="ghost", height=None,
                 bg=None, font=None):
        bg = bg or CARD
        h = height or (S(42) if kind == "accent" else S(38))
        self.text = text
        self.font = font or F_UI
        # Canvas 默认宽 378，不显式给宽度会把所在的卡片/栅格撑爆
        w = tkfont.Font(font=self.font).measure(text) + S(30)
        super().__init__(master, width=w, height=h, bg=bg, highlightthickness=0,
                         cursor="hand2")
        self.command = command
        self.kind = kind
        self._hover = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.after(10, self._draw)

    def _set_hover(self, on):
        self._hover = on
        self._draw()

    def _draw(self):
        try:
            w = max(self.winfo_width(), 8)
            h = max(self.winfo_height(), 8)
            self.delete("all")
            r = min(rad(), max(2, h // 2))
            if self.kind == "accent":
                fill = ACCENT_DARK if self._hover else ACCENT
                edge = ""
                fg = "#FFFFFF"
            elif self.kind == "link":
                fill = SOFT if self._hover else CARD
                edge = ""
                fg = ACCENT
            else:
                fill = SOFT if self._hover else CARD
                edge = BORDER
                fg = TEXT
            _round_rect(self, 1, 1, w - 1, h - 1, r, fill, edge)
            self.create_text(w / 2, h / 2, text=self.text, fill=fg,
                             font=self.font)
        except Exception:
            pass


class Card(tk.Frame):
    """Canvas 背板 + 正常 Frame 布局：四角圆角、一圈描边。

    fill / border / radius / bg 可覆盖，日志框那种“凹陷输入区”复用同一个类，
    保证所有圆角都取同一个 RADIUS。
    """

    def __init__(self, master, fill=None, border=None, radius=None, bg=None, **kw):
        self._bg = bg or BG
        super().__init__(master, bg=self._bg, highlightthickness=0, **kw)
        self._fill = fill
        self._border = border
        self._radius = radius
        self.canvas = tk.Canvas(self, bg=self._bg, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self._paint)
        self.after(20, self._paint)

    def _paint(self, _=None):
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 4 or h < 4:
                return
            fill = self._fill or CARD
            border = BORDER if self._border is None else self._border
            r = rad() if self._radius is None else S(self._radius)
            r = min(r, max(2, h // 2), max(2, w // 2))
            self.canvas.delete("all")
            _round_rect(self.canvas, 1, 1, w - 1, h - 1, r, fill, border)
            self.canvas.lower()
        except Exception:
            pass


class ScrollList(tk.Frame):
    """Canvas 套一个 Frame，做出可滚动的设备列表。"""

    def __init__(self, master, bg=CARD):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.bar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_wheel(False))

    def _on_inner(self, _):
        self.update_idletasks()
        need = self.inner.winfo_reqheight()
        have = self.canvas.winfo_height()
        h = max(need, have)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), h))
        self.update_bar()

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self.win, width=event.width)
        self.update_bar()

    def update_bar(self):
        """内容没超过可视区就把滚动条藏起来，省得一条设备也挂根条。"""
        try:
            self.update_idletasks()
            need = self.inner.winfo_reqheight()
            have = self.canvas.winfo_height()
        except Exception:
            return
        if need > have + 2:
            if not self.bar.winfo_ismapped():
                self.bar.pack(side="right", fill="y")
        elif self.bar.winfo_ismapped():
            self.bar.pack_forget()

    def _bind_wheel(self, on):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")

    def _wheel(self, event):
        try:
            region = str(self.canvas.cget("scrollregion")).split()
            if len(region) == 4:
                content_h = int(float(region[3]))
                if content_h <= self.canvas.winfo_height() + 2:
                    return
        except Exception:
            pass
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()


class Switch(tk.Canvas):
    """大号开关，替代 Tk 自带的小复选框。"""

    def __init__(self, master, value: bool, on_change, bg=CARD):
        w, h = S(46), S(23)
        super().__init__(master, width=w, height=h, bg=bg,
                         highlightthickness=0, cursor="hand2")
        self.value = bool(value)
        self.on_change = on_change
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _draw(self):
        self.delete("all")
        w = max(self.winfo_width(), S(46)) - S(3)
        h = max(self.winfo_height(), S(23)) - S(2)
        r = h // 2
        dark = CARD != "#FFFFFF"
        if self.value:
            track, edge = ACCENT, "#6C9BFF"
        else:
            track, edge = ("#2A3140", "#3E4859") if dark else ("#DCE3F0", "#C2CBDA")
        # 轨道：左右半圆 + 中间矩形，四周一圈描边，和卡片分层
        self.create_oval(1, 1, h + 1, h + 1, fill=track, outline=edge)
        self.create_oval(w - h - 1, 1, w + 1, h + 1, fill=track, outline=edge)
        self.create_rectangle(r + 1, 1, w - r - 1, h + 1, fill=track, outline="")
        self.create_line(r + 1, 1, w - r - 1, 1, fill=edge)
        self.create_line(r + 1, h + 1, w - r - 1, h + 1, fill=edge)
        # 滑块：略小于轨道内高，带一圈浅边，避免“白饼贴上去”
        kr = r - S(4)
        cy = r + 1
        cx = (w - r - S(1)) if self.value else (r + S(1))
        self.create_oval(cx - kr, cy - kr, cx + kr, cy + kr,
                         fill="#FFFFFF", outline=("#D7DEEA" if dark else "#E3E8F2"))

    def _click(self, _):
        self.value = not self.value
        self._draw()
        self.on_change(self.value)

    def set(self, value: bool):
        self.value = bool(value)
        self._draw()


class Chip(tk.Canvas):
    """圆角小按钮 / 标签：主题选项、头部「设置」、数量徽标共用。"""

    def __init__(self, master, text, command=None, active=False, fg=None,
                 padx=16, height=34, bg=None, font=None):
        self._font = font or F_UI
        self._pad = padx
        self._bg = bg or CARD
        self._text = text
        self._command = command
        self._active = bool(active)
        self._fg = fg
        self._hover = False
        w = tkfont.Font(font=self._font).measure(text) + S(padx) * 2
        super().__init__(master, width=w, height=S(height), bg=self._bg,
                         highlightthickness=0, bd=0,
                         cursor="hand2" if command else "arrow")
        self.bind("<Configure>", lambda e: self._draw())
        if command:
            self.bind("<Button-1>", lambda e: self._command())
            self.bind("<Enter>", lambda e: self._hovered(True))
            self.bind("<Leave>", lambda e: self._hovered(False))
        self.after(20, self._draw)

    def _hovered(self, on):
        self._hover = on
        self._draw()

    def set_text(self, text):
        self._text = str(text)
        w = tkfont.Font(font=self._font).measure(self._text) + S(self._pad) * 2
        self.configure(width=max(S(18), w))
        self._draw()

    def set_active(self, on: bool):
        self._active = bool(on)
        self._draw()

    def _draw(self):
        try:
            w = max(self.winfo_width(), 8)
            h = max(self.winfo_height(), 8)
            self.delete("all")
            r = min(rad(), max(2, h // 2))
            if self._active:
                fill, edge, fg = ACCENT, "", "#FFFFFF"
            else:
                fill = SOFT
                edge = ACCENT if self._hover else ""
                fg = self._fg or TEXT
            _round_rect(self, 1, 1, w - 1, h - 1, r, fill, edge)
            self.create_text(w / 2, h / 2, text=self._text, fill=fg,
                             font=self._font)
        except Exception:
            pass


class ProgressBar(tk.Canvas):
    """自绘圆角进度条：胶囊轨道 + 胶囊填充，数值变化带缓动。

    set(frac)  0..1，平滑追过去，不会一跳一跳
    busy(True) 还不确定进度（准备/握手）→ 一段胶囊来回跑
    """

    def __init__(self, master, height=None, bg=None):
        super().__init__(master, height=S(height or 10), bg=bg or CARD,
                         highlightthickness=0, bd=0)
        self._target = 0.0
        self._shown = 0.0
        self._busy = False
        self._phase = 0.0
        self._job = None
        self.bind("<Configure>", lambda e: self._draw())
        self.after(30, self._draw)

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def set(self, frac: float):
        try:
            self._target = max(0.0, min(1.0, float(frac)))
        except Exception:
            self._target = 0.0
        self._busy = False
        self._tick()

    def busy(self, on: bool = True):
        self._busy = bool(on)
        if self._busy:
            self._target = 0.0
        self._tick()

    def _tick(self):
        # 界面重建时旧控件会先被销毁，动画回调必须自己认路，别往 stderr 抛 TclError
        if not self._alive():
            return
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        moving = False
        if self._busy:
            self._phase = (self._phase + 0.05) % 1.0
            moving = True
        diff = self._target - self._shown
        if abs(diff) > 0.002:
            self._shown += diff * 0.25
            moving = True
        elif self._shown != self._target:
            self._shown = self._target
        self._draw()
        if moving:
            try:
                self._job = self.after(28, self._tick)
            except Exception:
                self._job = None

    def _draw(self):
        try:
            if not self._alive():
                return
            w = self.winfo_width()
            h = self.winfo_height()
            if w < 8 or h < 4:
                return
            self.delete("all")
            _pill(self, 0, 0, w, h, TROUGH)
            if self._busy:
                bw = max(h * 3, w * 0.22)
                x0 = -bw + (w + bw) * self._phase
                a, b = max(0, x0), min(w, x0 + bw)
                if b - a > h:
                    _pill(self, a, 1, b, h - 1, ACCENT)
            elif self._shown > 0.0005:
                _pill(self, 0, 0, max(h, w * self._shown), h, ACCENT)
        except Exception:
            pass


class DeviceRow(tk.Frame):
    def __init__(self, master, peer: Peer, app):
        super().__init__(master, bg=CARD, cursor="hand2")
        self.peer = peer
        self.app = app
        self.on = False

        self.bar = tk.Frame(self, bg=CARD, width=S(3))
        self.bar.pack(side="left", fill="y")

        self.avatar = tk.Canvas(self, width=S(38), height=S(38), bg=CARD,
                                highlightthickness=0)
        self.avatar.pack(side="left", padx=(S(12), S(10)), pady=S(8))
        self.avatar.create_oval(0, 0, S(38), S(38), fill=SOFT, outline="")
        self.avatar.create_text(S(19), S(19),
                                text=(peer.name[:1] or "?").upper(),
                                fill=ACCENT,
                                font=("Microsoft YaHei UI", 12, "bold"))

        text = tk.Frame(self, bg=CARD)
        text.pack(side="left", fill="both", expand=True, pady=S(9))
        self.name = tk.Label(text, text=peer.name, bg=CARD, fg=TEXT, font=F_BOLD,
                             anchor="w")
        self.name.pack(fill="x")
        self.sub = tk.Label(text, text=f"{peer.host}:{peer.port}", bg=CARD,
                            fg=MUTED, font=F_SMALL, anchor="w")
        self.sub.pack(fill="x")

        self.go = tk.Label(self, text="发送 ›", bg=CARD,
                           fg=ACCENT, font=F_SMALL,
                           cursor="hand2", padx=S(12))
        self.go.pack(side="right", padx=(0, S(6)))
        self.go.bind("<Button-1>", self._hit_send)
        widgets = [self, text, self.name, self.sub]
        if self.avatar is not None:
            widgets.append(self.avatar)
        for w in widgets:
            w.bind("<Button-1>", self._hit_select)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _enter(self, _):
        if not self.on:
            self._paint(SOFT)

    def _leave(self, _):
        if not self.on:
            self._paint(CARD)

    def _paint(self, color):
        for w in (self, self.name, self.sub, self.avatar):
            try:
                w.configure(bg=color)
            except Exception:
                pass
        self.go.configure(bg=color)
        self.bar.configure(bg=ACCENT if color == SOFT else color)

    def set_selected(self, on: bool):
        self.on = on
        self._paint(SOFT if on else CARD)

    def _hit_select(self, _):
        self.app.select_peer(self.peer.id)

    def _hit_send(self, _):
        self.app.select_peer(self.peer.id, ask_pending=False)
        self.app.send_files()


class App(tk.Tk):
    def __init__(self, core: Core, start_in_tray: bool = False):
        self.scale = enable_dpi_awareness()
        set_taskbar_identity()
        super().__init__()
        if start_in_tray:
            self.withdraw()  # 开机自启：先藏起来，托盘起来就别闪一下
        try:
            self.tk.call("tk", "scaling", 96 * self.scale / 72.0)
        except Exception:
            pass
        self.core = core
        self.theme = core.cfg.get("theme") or "system"
        apply_theme(detect_system_theme() if self.theme == "system" else self.theme)
        self.control = None
        self.last_progress = (0.0, "空闲", "等待发送或接收")
        self._last_log = ""
        self._last_log_at = 0.0
        self._peer_at = 0.0
        self.full_log = deque(maxlen=400)
        self.peers = []
        self.rows = {}
        self.selected_id = None
        self.pending = []
        self._handoff_buffer = []
        self._handoff_job = None
        self.recent = deque(maxlen=3)
        self._labels = []
        self.title(f"{APP_NAME} · 局域网文件互传")
        self._apply_icon()
        try:
            self.option_add("*Font", F_UI)
        except Exception:
            pass
        self.configure(bg=BG)
        self.geometry(self._center_geometry(S(1000), S(724)))
        self.minsize(S(940), S(680))
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tray = None
        self._tray_show = False
        self._tray_open = False
        self._tray_quit = False
        self._quitting = False
        self._listener = None
        self._styles()
        self._build()
        self.after(200, self._apply_titlebar)
        self.bind("<Map>", lambda e: self.after(80, self._apply_titlebar))
        self._setup_tray()
        self._start_listener()
        self._sync_shell_menu()
        if start_in_tray and self.tray is None:
            self.deiconify()  # 托盘不可用就别装死
        self.after(120, self._poll)
        self.after(300, self._refresh_peers)
        self.after(600, self._drain_handoff)
        self.after(2200, self._check_handoff)

    def _center_geometry(self, w: int, h: int) -> str:
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w = min(w, sw - S(60))
            h = min(h, sh - S(90))
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2 - 10)
            return f"{w}x{h}+{x}+{y}"
        except Exception:
            return f"{w}x{h}"

    def _logo_image(self, size: int):
        png = asset_path("lanbeam.png")
        if not png:
            return None
        try:
            from PIL import Image, ImageTk
            im = Image.open(png).convert("RGBA").resize((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(im)
        except Exception:
            return None

    def _apply_icon(self):
        ico = asset_path("lanbeam.ico")
        if ico:
            try:
                self.iconbitmap(default=ico)
            except Exception:
                pass
        png = asset_path("lanbeam.png")
        if png:
            try:
                img = tk.PhotoImage(file=png)
                w = img.width() or 64
                if w > 96:
                    img = img.subsample(max(1, w // 64))
                self.iconphoto(True, img)
                self._iconphoto = img
            except Exception:
                pass

    # -- 样式 ----------------------------------------------------------
    def _styles(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF",
                    borderwidth=0, focusthickness=0,
                    padding=(S(16), S(11)),
                    font=("Microsoft YaHei UI", 10, "bold"))
        s.map("Accent.TButton",
              background=[("active", ACCENT_DARK), ("disabled", "#C3D0F2")],
              foreground=[("disabled", "#F2F5FF")])
        s.configure("Ghost.TButton", background=CARD, foreground=TEXT,
                    borderwidth=1, relief="solid", focusthickness=0,
                    padding=(S(16), S(10)),
                    font=F_UI)
        s.map("Ghost.TButton",
              background=[("active", SOFT)],
              bordercolor=[("!disabled", BORDER)])
        s.configure("Tiny.TButton", background=CARD, foreground=MUTED,
                    borderwidth=0, padding=(6, 2), font=F_SMALL)
        s.map("Tiny.TButton", background=[("active", SOFT)])
        s.configure("TCheckbutton", background=CARD, foreground=TEXT, font=F_UI)

    # -- 布局 ----------------------------------------------------------
    def _build(self):
        if getattr(self, "view", "main") == "settings":
            self._build_settings()
            return
        self._build_main()

    def _build_main(self):
        self._header()
        # 先占底部，再让主体吃剩余空间，否则 expand 会把底部卡片挤没
        self._recent_card()
        self._transfer_card()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=S(20), pady=(S(16), 0))

        # 右侧栏先打包，左侧再 expand，保证 300px 不被吃掉
        right = tk.Frame(body, bg=BG, width=S(300))
        right.pack(side="right", fill="y", padx=(16, 0))
        right.pack_propagate(False)
        self._send_card(right)
        self._recv_card(right)

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        self._devices_card(left)

        frac, title, detail = self.last_progress
        try:
            self.prog.set(frac)
            self.prog.busy(frac <= 0 and "准备" in (title or ""))
            self.title_lbl.configure(text=title)
            self.detail_lbl.configure(text=detail)
            self.percent_lbl.configure(text=f"{frac * 100:.0f}%" if frac > 0 else "")
        except Exception:
            pass
        if self.control is not None:
            self._show_controls(True)

    def _header(self):
        head = tk.Frame(self, bg=CARD, height=S(88))
        head.pack(fill="x")
        head.pack_propagate(False)

        logo_img = self._logo_image(S(46))
        if logo_img is not None:
            logo = tk.Label(head, image=logo_img, bg=CARD, bd=0)
            logo.image = logo_img
            logo.pack(side="left", padx=(S(20), S(12)), pady=S(20))
        else:
            logo = tk.Canvas(head, width=S(46), height=S(46), bg=CARD, highlightthickness=0)
            logo.pack(side="left", padx=(S(20), S(12)), pady=S(20))
            logo.create_rectangle(0, 0, S(46), S(46), fill=ACCENT, outline="")
            logo.create_line(S(11), S(18), S(32), S(18), fill="#FFFFFF", width=S(4))
            logo.create_polygon(S(34), S(18), S(26), S(12), S(26), S(24), fill="#FFFFFF")

        title_box = tk.Frame(head, bg=CARD)
        title_box.pack(side="left", pady=S(18))
        tk.Label(title_box, text="LanBeam", bg=CARD, fg=TEXT, font=F_TITLE,
                 anchor="w").pack(anchor="w")
        tk.Label(title_box, text="局域网文件互传 · 手机 / 平板 / 电脑",
                 bg=CARD, fg=MUTED, font=F_SMALL, anchor="w").pack(anchor="w")

        right = tk.Frame(head, bg=CARD)
        right.pack(side="right", padx=S(20))

        settings_btn = Chip(right, "设置", command=self.open_settings,
                            fg=ACCENT, height=32)
        settings_btn.pack(side="right", padx=(S(4), 0))

        self.token_lbl = tk.Label(right, text=f"令牌 {self.core.token}", bg=CARD,
                                  fg=MUTED, font=F_SMALL, padx=S(2), pady=2)
        self.token_lbl.pack(side="right", padx=(0, S(8)))

        status = tk.Frame(right, bg=CARD)
        status.pack(side="right", padx=(0, S(10)))
        dot = tk.Canvas(status, width=S(8), height=S(8), bg=CARD,
                        highlightthickness=0)
        dot.pack(side="left", padx=(0, S(6)))
        dot.create_oval(1, 1, S(7), S(7), fill=OK, outline="")
        self.status_lbl = tk.Label(status, text="已就绪", bg=CARD, fg=MUTED,
                                   font=F_SMALL)
        self.status_lbl.pack(side="left")

        tk.Label(right, text=f"v{VERSION}", bg=CARD, fg=MUTED,
                 font=F_SMALL).pack(side="right", padx=(0, S(10)))

    def _empty_block(self, parent):
        box = tk.Frame(parent, bg=CARD)
        icon = tk.Canvas(box, width=S(64), height=S(64), bg=CARD,
                         highlightthickness=0)
        icon.pack(pady=(S(18), S(10)))
        icon.create_oval(0, 0, S(64), S(64), fill=SOFT, outline="")
        icon.create_line(S(18), S(27), S(40), S(27), fill=ACCENT, width=S(4))
        icon.create_polygon(S(46), S(27), S(36), S(19), S(36), S(35), fill=ACCENT)
        icon.create_line(S(46), S(38), S(24), S(38), fill=ACCENT, width=S(4))
        icon.create_polygon(S(18), S(38), S(28), S(30), S(28), S(46), fill=ACCENT)
        tk.Label(box, text="正在寻找设备…", bg=CARD, fg=TEXT,
                 font=F_BIG).pack()
        tk.Label(box, text="确保两台设备在同一局域网，并允许防火墙访问",
                 bg=CARD, fg=MUTED, font=F_SMALL).pack(pady=(S(4), S(6)))
        return box

    def _devices_card(self, parent):
        card = Card(parent)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text="附近设备", bg=CARD, fg=TEXT, font=F_BIG).pack(side="left")
        self.count_lbl = Chip(top, "0", fg=ACCENT, padx=9, height=22,
                              font=F_SMALL)
        self.count_lbl.pack(side="left", padx=(8, 0))
        ttk.Button(top, text="刷新", style="Tiny.TButton",
                   command=self._refresh_peers).pack(side="right")

        self.list = ScrollList(card, bg=CARD)
        self.list.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.after(250, self.list.update_bar)
        self.empty = self._empty_block(self.list.inner)
        self.empty.pack(fill="x", pady=S(10))

    def _send_card(self, parent):
        card = Card(parent)
        card.pack(fill="x")
        tk.Label(card, text="发送", bg=CARD, fg=TEXT, font=F_BIG).pack(
            anchor="w", padx=14, pady=(10, 2))
        self.target_lbl = tk.Label(card, text="先在左侧选一台设备", bg=CARD,
                                   fg=MUTED, font=F_SMALL, anchor="w",
                                   wraplength=S(250), justify="left")
        self.target_lbl.pack(fill="x", padx=14, pady=(0, 6))
        self.pending_lbl = tk.Label(card, text="", bg=CARD, fg=ACCENT,
                                    font=F_SMALL, anchor="w", cursor="hand2",
                                    wraplength=S(250), justify="left")
        self.pending_lbl.bind("<Button-1>", lambda e: self._clear_pending())
        self.btn_files = RoundButton(card, "发送文件…", self.send_files, "accent")
        self.btn_files.pack(fill="x", padx=S(14))
        RoundButton(card, "发送文件夹…", self.send_folder).pack(
            fill="x", padx=S(14), pady=(S(6), S(12)))
        self._update_pending_ui()

    def _recv_card(self, parent):
        card = Card(parent)
        card.pack(fill="x", pady=(14, 0))
        tk.Label(card, text="接收", bg=CARD, fg=TEXT, font=F_BIG).pack(
            anchor="w", padx=14, pady=(10, 4))
        self.auto_var = tk.BooleanVar(value=bool(self.core.cfg.get("auto_accept")))
        auto_row = tk.Frame(card, bg=CARD)
        auto_row.pack(fill="x", padx=S(14), pady=(S(4), S(6)))
        tk.Label(auto_row, text="自动接收（不弹确认）", bg=CARD, fg=TEXT,
                 font=F_UI, anchor="w").pack(side="left")
        self.auto_switch = Switch(auto_row, bool(self.core.cfg.get("auto_accept")),
                                  self._toggle_auto, bg=CARD)
        self.auto_switch.pack(side="right")
        tk.Label(card, text="收件位置", bg=CARD, fg=MUTED, font=F_SMALL).pack(
            anchor="w", padx=14, pady=(6, 0))
        self.inbox_lbl = tk.Label(card, text=str(self.core.inbox), bg=CARD, fg=TEXT,
                                  font=F_SMALL, wraplength=S(250), justify="left")
        self.inbox_lbl.pack(anchor="w", padx=14)
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=S(14), pady=(S(8), S(10)))
        row.columnconfigure(0, weight=1, uniform="btn")
        row.columnconfigure(1, weight=1, uniform="btn")
        RoundButton(row, "更改…", self.choose_inbox, height=S(36)).grid(
            row=0, column=0, sticky="ew")
        RoundButton(row, "打开文件夹", self.open_inbox, height=S(36)).grid(
            row=0, column=1, sticky="ew", padx=(S(8), 0))

    def _transfer_card(self):
        card = Card(self)
        card.configure(height=S(112))
        card.pack_propagate(False)
        card.pack(side="bottom", fill="x", padx=S(20), pady=(12, 0))
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=16, pady=(8, 0))
        tk.Label(top, text="当前传输", bg=CARD, fg=MUTED, font=F_SMALL).pack(side="left")
        self.percent_lbl = tk.Label(top, text="", bg=CARD, fg=ACCENT, font=F_SMALL)
        self.percent_lbl.pack(side="right")
        self.btn_cancel = ttk.Button(top, text="取消", style="Tiny.TButton",
                                     command=self.cancel_send)
        self.btn_pause = ttk.Button(top, text="暂停", style="Tiny.TButton",
                                    command=self.toggle_pause)
        self.title_lbl = tk.Label(card, text="空闲", bg=CARD, fg=TEXT, font=F_BIG,
                                  anchor="w")
        self.title_lbl.pack(fill="x", padx=16, pady=(2, 4))
        self.prog = ProgressBar(card, height=10)
        self.prog.pack(fill="x", padx=S(16), pady=(S(2), 0))
        self.detail_lbl = tk.Label(card, text="等待发送或接收", bg=CARD, fg=MUTED,
                                   font=F_SMALL, anchor="w")
        self.detail_lbl.pack(fill="x", padx=16, pady=(4, 8))

    def _recent_card(self):
        card = Card(self)
        card.configure(height=S(90))
        card.pack_propagate(False)
        card.pack(side="bottom", fill="x", padx=S(20), pady=(10, 14))
        tk.Label(card, text="最近", bg=CARD, fg=MUTED, font=F_SMALL).pack(
            anchor="w", padx=16, pady=(6, 0))
        self.recent_lbls = []
        for i in range(2):
            lb = tk.Label(card, text="还没有传输记录" if i == 0 else "",
                          bg=CARD, fg=TEXT if i == 0 else MUTED,
                          font=F_SMALL, anchor="w")
            lb.pack(fill="x", padx=16)
            self.recent_lbls.append(lb)
        tk.Frame(card, bg=CARD, height=4).pack()

    # -- 事件 ----------------------------------------------------------
    def _handle_event(self, ev):
        kind = ev[0]
        if kind == "log":
            self._log(ev[1])
            return
        if kind == "progress":
            frac = float(ev[1])
            self.last_progress = (frac, ev[2], ev[3])
            if getattr(self, "view", "main") == "main":
                self.prog.set(frac)
                # 还没拿到字节数（握手/准备）时，进度条改成来回跑
                self.prog.busy(frac <= 0 and "准备" in (ev[2] or ""))
                self.title_lbl.configure(text=ev[2])
                self.detail_lbl.configure(text=ev[3])
                self.percent_lbl.configure(text=f"{frac * 100:.0f}%")
            return
        if kind == "done":
            self.last_progress = (1.0, self.last_progress[1], "完成")
            if getattr(self, "view", "main") == "main":
                self.prog.set(1.0)
            return
        if kind == "offer":
            self._on_offer(ev[1], ev[2], ev[3])

    def _poll(self):
        try:
            while True:
                ev = self.core.events.get_nowait()
                try:
                    self._handle_event(ev)
                except Exception:
                    pass
        except queue.Empty:
            pass
        finally:
            try:
                if self._tray_show:
                    self._tray_show = False
                    self._show_window()
                    self._drain_handoff()
                if self._tray_open:
                    self._tray_open = False
                    self.open_inbox()
                if self._tray_quit:
                    self._tray_quit = False
                    self.quit_app()
            except Exception:
                pass
            self.after(120, self._poll)

    def _setup_tray(self):
        try:
            tray = Tray(
                tooltip=f"LanBeam · {self.core.name} · 令牌 {self.core.token}",
                on_show=lambda: setattr(self, "_tray_show", True),
                on_open=lambda: setattr(self, "_tray_open", True),
                on_quit=lambda: setattr(self, "_tray_quit", True))
            if tray.start():
                self.tray = tray
                return
        except Exception:
            pass
        self.tray = None
        self._log("托盘不可用，关闭窗口即退出")

    def _start_listener(self):
        try:
            self._listener = ShowListener(
                lambda: setattr(self, "_tray_show", True))
            self._listener.start()
        except Exception:
            self._listener = None

    def _sync_shell_menu(self):
        """右键菜单默认开；exe 换位置了顺手把注册表里的路径更新掉。

        从源码跑（开发态）不写注册表，免得把正式 exe 的注册项改成 pythonw。
        """
        frozen = bool(getattr(sys, "frozen", False))
        try:
            if bool(self.core.cfg.get("shell_menu", True)):
                if frozen:
                    shellmenu.install()
            elif shellmenu.is_installed():
                shellmenu.remove()
        except Exception:
            pass
        try:
            self.core.cfg["startup"] = startup.is_enabled()
            # exe 挪了位置就把启动项里的命令改过来，别留一条指不到的路径
            if (frozen and startup.is_enabled()
                    and startup.current_value() != startup.command()):
                startup.install()
        except Exception:
            pass

    def _show_window(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self._log("窗口已恢复")
        except Exception:
            pass

    # -- 右键菜单 / 单实例传进来的待发送项 ------------------------------
    def _drain_handoff(self):
        try:
            paths = handoff.take()
        except Exception:
            paths = []
        if not paths:
            return
        # 多选文件时资源管理器会连着调好几次，先攒 0.45 秒，合成一份待发送
        for item in paths:
            try:
                p = Path(item)
            except Exception:
                continue
            if p.exists() and p not in self._handoff_buffer:
                self._handoff_buffer.append(p)
        if self._handoff_job is not None:
            try:
                self.after_cancel(self._handoff_job)
            except Exception:
                pass
        self._handoff_job = self.after(450, self._handoff_flush)

    def _handoff_flush(self):
        self._handoff_job = None
        items, self._handoff_buffer = self._handoff_buffer, []
        if not items:
            return
        try:
            self._accept_handoff(items)
        except Exception:
            self._log("待发送内容读取失败")

    def _check_handoff(self):
        self._drain_handoff()
        try:
            self.after(2000, self._check_handoff)
        except Exception:
            pass

    def _accept_handoff(self, raw):
        good = []
        for item in raw:
            try:
                p = Path(item)
                if p.exists():
                    good.append(p)
            except Exception:
                continue
        if not good:
            self._log("右键发送：路径已不存在，忽略")
            return
        self._show_window()
        merged = list(self.pending)
        for p in good:
            if p not in merged:
                merged.append(p)
        self.pending = merged
        total = sum(tree_size(p) for p in merged)
        self._log(f"待发送：{len(merged)} 项，共 {human(total)}")
        self._update_pending_ui()
        self._refresh_target_label()
        peer = next((p for p in self.peers if p.id == self.selected_id), None)
        if peer and messagebox.askyesno(
                "发送这些内容",
                f"把 {len(merged)} 项（{human(total)}）发给「{peer.name}」？",
                parent=self):
            self._send_pending()

    def _send_pending(self):
        if not self.pending:
            return
        paths = list(self.pending)
        self._start(paths)

    def _clear_pending(self):
        if not self.pending:
            return
        self.pending = []
        self._log("已取消待发送")
        self._update_pending_ui()
        self._refresh_target_label()

    def _refresh_target_label(self):
        try:
            peer = next((p for p in self.peers if p.id == self.selected_id), None)
            if peer:
                self.target_lbl.configure(text=f"发送到 {peer.name}")
            elif self.pending:
                self.target_lbl.configure(text="在左侧选一台设备发送")
            else:
                self.target_lbl.configure(text="先在左侧选一台设备")
        except Exception:
            pass

    def _update_pending_ui(self):
        lbl = getattr(self, "pending_lbl", None)
        try:
            if lbl is None or not lbl.winfo_exists():
                return
            if not self.pending:
                lbl.pack_forget()
                return
            total = sum(tree_size(p) for p in self.pending)
            lbl.configure(
                text=f"待发送 {len(self.pending)} 项 · {human(total)}（点这里取消）")
            if not lbl.winfo_ismapped():
                lbl.pack(fill="x", padx=S(14), pady=(0, S(6)),
                         before=self.btn_files)
        except Exception:
            pass

    def _on_offer(self, payload, ev, box):
        if self.state() == "withdrawn":
            self._show_window()
        sender, kind, root, nfiles, total = payload
        who = self.core.peer_name_for(sender)
        if kind == "folder":
            first = f"{who} 想发送文件夹「{root}」"
            second = f"{nfiles} 个文件，共 {human(total)}"
        else:
            first = f"{who} 想发送 {nfiles} 个文件"
            second = f"共 {human(total)}"
        ok = messagebox.askyesno(
            "收到发送请求",
            f"{first}\n{second}\n\n接受到 LanBeam 收件文件夹？",
            parent=self)
        box["ok"] = bool(ok)
        ev.set()
        what = "文件夹" if kind == "folder" else "文件"
        self._log(("已接受" if ok else "已拒绝") + f"{what} · 来自 {who}")

    def _refresh_peers(self):
        try:
            self._refresh_peers_once()
        finally:
            self.after(1000, self._refresh_peers)

    def _refresh_peers_once(self):
        if getattr(self, "view", "main") == "settings":
            return
        lst = getattr(self, "list", None)
        if lst is None or not lst.winfo_exists():
            return
        peers = self.core.discovery.snapshot()
        if not peers and self.peers and time.time() - self._peer_at < 6:
            return
        if peers:
            self._peer_at = time.time()
        labels = [p.label for p in peers]
        self.peers = peers
        if labels != self._labels or len(self.rows) != len(peers):
            self._labels = labels
            self.list.clear()
            self.rows = {}
            if not peers:
                self.empty = self._empty_block(self.list.inner)
                self.empty.pack(fill="x", pady=S(10))
            else:
                for p in peers:
                    row = DeviceRow(self.list.inner, p, self)
                    row.pack(fill="x", padx=6, pady=1)
                    self.rows[p.id] = row
            self.list.update_bar()
            self.count_lbl.set_text(len(peers))
            if self.selected_id and self.selected_id not in self.rows:
                self.selected_id = None
                self.target_lbl.configure(text="先在左侧选一台设备")
            if self.selected_id:
                self.rows[self.selected_id].set_selected(True)
        self.list.update_bar()

    def select_peer(self, pid, ask_pending=True):
        self.selected_id = pid
        for k, row in self.rows.items():
            row.set_selected(k == pid)
        peer = next((p for p in self.peers if p.id == pid), None)
        if peer:
            self.target_lbl.configure(text=f"发送到 {peer.name}")
            if ask_pending and self.pending:
                total = sum(tree_size(p) for p in self.pending)
                if messagebox.askyesno(
                        "发送待发内容",
                        f"把 {len(self.pending)} 项（{human(total)}）"
                        f"发给「{peer.name}」？", parent=self):
                    self._send_pending()
                else:
                    self._refresh_target_label()

    def send_files(self):
        if not self._need_target():
            return
        files = filedialog.askopenfilenames(parent=self, title="选择要发送的文件")
        if files:
            self._start([Path(f) for f in files])

    def send_folder(self):
        if not self._need_target():
            return
        folder = filedialog.askdirectory(parent=self, title="选择要发送的文件夹",
                                         mustexist=True)
        if folder:
            self._start([Path(folder)])

    def _need_target(self) -> bool:
        if not self.selected_id:
            messagebox.showinfo("先选设备", "在左边列表里点一下接收方。", parent=self)
            return False
        return True

    def _start(self, paths):
        peer = next((p for p in self.core.discovery.snapshot()
                     if p.id == self.selected_id), None)
        if peer is None:
            peer = next((p for p in self.peers if p.id == self.selected_id), None)
        if not peer:
            return
        if self.core.send_lock.locked():
            messagebox.showinfo("正在发送", "上一批还没传完，稍等。", parent=self)
            return
        self.pending = []
        self._update_pending_ui()
        self._refresh_target_label()
        threading.Thread(target=self._worker, args=(peer, paths), daemon=True).start()

    def _worker(self, peer: Peer, paths):
        with self.core.send_lock:
            self.control = TransferControl()
            self._show_controls(True)
            self.core.emit("progress", 0, "准备发送…", "")
            self._log(f"发送 {paths[0].name} → {peer.name}")
            try:
                send_batch(self.core, peer, paths,
                           on_progress=lambda f, t, d: self.core.emit("progress", f, t, d),
                           on_log=lambda m: self.core.emit("log", m),
                           control=self.control)
                self.core.emit("progress", 1.0, "发送完成", "")
                self._log(f"发送完成 → {peer.name}")
            except TransferCancelled:
                self.core.emit("progress", 0, "已取消", "")
                self._log("已取消发送")
            except Exception as e:
                self.core.emit("progress", 0, "发送失败", "")
                self._log(f"失败：{e}")
            finally:
                self.control = None
                self._show_controls(False)

    def add_manual(self):
        raw = simpledialog.askstring(
            "手动添加设备", "输入对方的 IP:端口 令牌\n例如 192.168.1.5:47821 A1B2C3",
            parent=self)
        if not raw:
            return
        try:
            addr, token = raw.split()
            host, port = addr.rsplit(":", 1)
            peer = Peer(id=f"manual-{host}-{port}", name=f"手动 {host}",
                        host=host, port=int(port), token=token.strip().upper())
        except Exception:
            messagebox.showerror("格式不对", "要写成 192.168.1.5:47821 A1B2C3", parent=self)
            return
        self.core.discovery.remember(peer)
        self._refresh_peers()
        self._log(f"已手动添加 {peer.host}:{peer.port}")

    def open_inbox(self):
        try:
            os.startfile(str(self.core.inbox))
        except Exception as e:
            messagebox.showerror("打不开", str(e), parent=self)

    def _toggle_auto(self, on: bool):
        self.auto_var.set(bool(on))
        self.core.cfg["auto_accept"] = bool(on)
        save_config(self.core.cfg)
        self._log("自动接收：" + ("开" if on else "关"))

    def _show_controls(self, on: bool):
        try:
            if on:
                self.btn_cancel.pack(side="right")
                self.btn_pause.pack(side="right", padx=(0, 6))
                self.btn_pause.configure(text="暂停")
            else:
                self.btn_pause.pack_forget()
                self.btn_cancel.pack_forget()
        except Exception:
            pass

    def toggle_pause(self):
        c = self.control
        if not c:
            return
        c.set_paused(not c.paused)
        self.btn_pause.configure(text="继续" if c.paused else "暂停")
        self._log("已暂停发送" if c.paused else "继续发送")

    def cancel_send(self):
        c = self.control
        if c:
            c.cancel()
            self._log("正在取消…")

    def choose_inbox(self):
        d = filedialog.askdirectory(parent=self, title="选择收件目录",
                                    initialdir=str(self.core.inbox))
        if not d:
            return
        self.core.set_inbox(Path(d))
        self._log("收件目录：" + str(self.core.inbox))
        self.rebuild_ui()

    def set_theme(self, name: str):
        self.theme = name
        apply_theme(detect_system_theme() if name == "system" else name)
        if name == "acrylic":
            self.after(30, lambda: set_backdrop(self, True))
        self.core.cfg["theme"] = name
        save_config(self.core.cfg)
        win = getattr(self, "_settings_win", None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
            self._settings_win = None
        self.rebuild_ui()

    def rebuild_ui(self):
        for w in self.winfo_children():
            w.destroy()
        self.rows = {}
        self._labels = []
        self.selected_id = None
        self.configure(bg=BG)
        self._styles()
        self._build()
        if getattr(self, "view", "main") != "settings":
            self._refresh_peers()
        self.after(60, self._apply_titlebar)

    def copy_log(self):
        text = "\n".join(self.full_log)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log("日志已复制到剪贴板")

    def _settings_card(self, parent, title):
        box = Card(parent)
        box.pack(fill="x", padx=S(18), pady=(S(12), 0))
        tk.Label(box, text=title, bg=CARD, fg=TEXT, font=F_BIG,
                 anchor="w").pack(fill="x", padx=S(14), pady=(S(10), S(4)))
        return box

    def _switch_row(self, parent, text, value, on_change, hint=None):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=S(14), pady=(S(4), S(4)))
        tk.Label(row, text=text, bg=CARD, fg=TEXT, font=F_UI,
                 anchor="w").pack(side="left")
        Switch(row, bool(value), on_change, bg=CARD).pack(side="right")
        if hint:
            tk.Label(parent, text=hint, bg=CARD, fg=MUTED, font=F_SMALL,
                     anchor="w", wraplength=S(820), justify="left").pack(
                fill="x", padx=S(14), pady=(0, S(10)))

    def _toggle_startup(self, on: bool):
        ok = startup.sync(bool(on))
        self.core.cfg["startup"] = bool(ok)
        save_config(self.core.cfg)
        self._log("开机自启：" + ("开" if ok else "关"))
        if bool(on) and not ok:
            messagebox.showwarning("没写进去",
                                   "启动项没写成，可能被安全软件拦了。", parent=self)

    def _toggle_shellmenu(self, on: bool):
        ok = shellmenu.sync(bool(on))
        self.core.cfg["shell_menu"] = bool(ok)
        save_config(self.core.cfg)
        self._log("右键菜单：" + ("已添加" if ok else "已移除"))
        if bool(on) and not ok:
            messagebox.showwarning("没写进去",
                                   "右键菜单没写上，可能被安全软件拦了。", parent=self)

    def _build_settings(self):
        head = tk.Frame(self, bg=CARD, height=S(58))
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="设置", bg=CARD, fg=TEXT, font=F_TITLE).pack(
            side="left", padx=S(16))
        RoundButton(head, "返回", self.close_settings, height=S(34)).pack(
            side="right", padx=(0, S(16)), pady=S(12))
        tk.Label(head, text=f"v{VERSION}", bg=CARD, fg=MUTED,
                 font=F_SMALL).pack(side="right", padx=S(16))

        scroller = ScrollList(self, bg=BG)
        scroller.pack(fill="both", expand=True)
        body = scroller.inner

        recv = self._settings_card(body, "接收")
        self._switch_row(recv, "自动接收（不弹确认）",
                         bool(self.core.cfg.get("auto_accept")), self._set_auto)
        tk.Label(recv, text="收件目录", bg=CARD, fg=MUTED, font=F_SMALL,
                 anchor="w").pack(fill="x", padx=S(14), pady=(S(6), 0))
        tk.Label(recv, text=str(self.core.inbox), bg=CARD, fg=TEXT, font=F_SMALL,
                 anchor="w", wraplength=S(820), justify="left").pack(
            fill="x", padx=S(14))
        row = tk.Frame(recv, bg=CARD)
        row.pack(fill="x", padx=S(14), pady=(S(8), S(12)))
        RoundButton(row, "更改…", self.choose_inbox, height=S(36)).pack(
            side="left", fill="x", expand=True)
        RoundButton(row, "打开", self.open_inbox, height=S(36)).pack(
            side="left", fill="x", expand=True, padx=(S(8), 0))

        syscard = self._settings_card(body, "系统集成")
        self._switch_row(syscard, "开机自启（启动后收进托盘）",
                         startup.is_enabled(), self._toggle_startup,
                         hint="写当前用户的启动项，不需要管理员；开机后窗口收在托盘，"
                              "照样能收文件。")
        self._switch_row(syscard, "右键菜单「通过 LanBeam 发送」",
                         shellmenu.is_installed(), self._toggle_shellmenu,
                         hint="在文件或文件夹上点右键就能直接发；已经在跑就交给它，"
                              "没跑会先起来再接。")

        look = self._settings_card(body, "界面样式")
        tk.Label(look, text="当前系统：" + ("深色" if detect_system_theme() == "dark" else "浅色"),
                 bg=CARD, fg=MUTED, font=F_SMALL, anchor="w").pack(
            fill="x", padx=S(14))
        line = tk.Frame(look, bg=CARD)
        line.pack(fill="x", padx=S(14), pady=(S(8), S(14)))
        for value, label in (("light", "浅色"), ("dark", "深色"),
                             ("system", "跟随系统")):
            chip = Chip(line, label, command=lambda v=value: self.set_theme(v),
                        active=(self.theme == value), height=34)
            chip.pack(side="left", padx=(0, S(10)))

        logs = self._settings_card(body, "日志")
        logbox = Card(logs, bg=CARD, fill=BG, border=BORDER)
        logbox.pack(fill="x", padx=S(14), pady=(0, S(8)))
        box = tk.Text(logbox, height=6, bg=BG, fg=MUTED, font=F_SMALL,
                      relief="flat", bd=0, highlightthickness=0, wrap="word",
                      insertwidth=0, spacing1=1, spacing3=1)
        box.pack(fill="both", expand=True, padx=S(RADIUS + 2), pady=S(RADIUS))
        box.insert("1.0", "\n".join(list(self.full_log)[:40]) or "暂无日志")
        box.configure(state="disabled")
        RoundButton(logs, "复制日志", self.copy_log, kind="link",
                    height=S(30)).pack(anchor="w", padx=S(14), pady=(0, S(12)))

        about = self._settings_card(body, "关于")
        tk.Label(about, text=f"LanBeam v{VERSION} · Windows", bg=CARD, fg=TEXT,
                 font=F_UI, anchor="w").pack(fill="x", padx=S(14))
        link = tk.Label(about, text="项目主页  ›", bg=CARD, fg=ACCENT,
                        font=F_UI, anchor="w", cursor="hand2")
        link.pack(fill="x", padx=S(14), pady=(S(6), S(12)))
        link.bind("<Button-1>", lambda e: webbrowser.open(PROJECT_URL))

        self.after(30, self._apply_titlebar)

    def open_settings(self):
        self.view = "settings"
        self.rebuild_ui()

    def close_settings(self):
        self.view = "main"
        self.rebuild_ui()

    def _apply_titlebar(self):
        dark = self.theme in ("dark", "acrylic") or (
            self.theme == "system" and detect_system_theme() == "dark")
        set_dark_titlebar(self, dark)
        set_backdrop(self, False)
        try:
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD]
            v = ctypes.c_int(2)
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(v),
                                      ctypes.sizeof(v))
        except Exception:
            pass

    def _set_auto(self, on: bool):
        self.core.cfg["auto_accept"] = bool(on)
        save_config(self.core.cfg)
        self._log("自动接收：" + ("开" if on else "关"))

    def _log(self, msg: str):
        now = time.time()
        if msg == self._last_log and now - self._last_log_at < 1.5:
            return
        self._last_log = msg
        self._last_log_at = now
        line = time.strftime("%H:%M ") + msg
        self.full_log.appendleft(line)
        self.recent.appendleft(line)
        items = list(self.recent) + [""] * 3
        for i, (lb, text) in enumerate(zip(self.recent_lbls, items)):
            try:
                if not lb.winfo_exists():
                    continue
                lb.configure(text=text[:110], fg=TEXT if i == 0 else MUTED)
            except Exception:
                continue

    def on_close(self):
        if self._quitting:
            return
        if self.tray:
            self.withdraw()
            self.tray.notify(
                "LanBeam 仍在后台运行",
                "已收进托盘，接收功能保持在线。双击托盘图标恢复窗口，右键可退出。")
            self._log("已转入托盘，后台继续接收；再双击 exe 也能把窗口叫回来")
        else:
            self.quit_app()

    def quit_app(self):
        if self._quitting:
            return
        self._quitting = True
        if self._listener:
            try:
                self._listener.shutdown()
            except Exception:
                pass
            self._listener = None
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None
        self.core.cfg["name"] = self.core.name
        save_config(self.core.cfg)
        try:
            self.core.stop()
        except Exception:
            pass
        self.destroy()