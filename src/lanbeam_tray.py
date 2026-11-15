# -*- coding: utf-8 -*-
"""Windows 托盘图标：纯 ctypes 调 Shell_NotifyIcon，不引第三方库。

托盘线程只负责收消息、置标志位；真正的界面操作由 Tk 主线程轮询执行，
避免跨线程碰 Tk。
"""

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from pathlib import Path

LOG = logging.getLogger("lanbeam.tray")

WM_USER = 0x0400
WM_TRAY = WM_USER + 20
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_INFO, NIIF_NOSOUND = 0x1, 0x10
IMAGE_ICON = 1
LR_LOADFROMFILE, LR_DEFAULTSIZE = 0x0010, 0x0040
IDI_APPLICATION = 32512

MF_STRING = 0x0000
TPM_LEFTALIGN, TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0000, 0x0002, 0x0100

ID_SHOW, ID_OPEN, ID_QUIT = 1001, 1002, 1003

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

# 64 位下必须显式声明参数类型，否则 LPARAM 会被截成 int32 而溢出
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             WPARAM, LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND), ("message", wintypes.UINT),
        ("wParam", WPARAM), ("lParam", LPARAM),
        ("time", wintypes.DWORD), ("pt", wintypes.POINT),
    ]


def icon_path() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    p = base / "lanbeam.ico"
    return str(p) if p.exists() else ""


class Tray:
    def __init__(self, tooltip: str, on_show, on_open, on_quit):
        self.tooltip = tooltip[:100]
        self.on_show = on_show
        self.on_open = on_open
        self.on_quit = on_quit
        self.ok = False
        self.hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._wndproc = WNDPROC(self._proc)
        self._class_name = f"LanBeamTrayWnd_{id(self)}"

    # -- 线程入口 ------------------------------------------------------
    def start(self) -> bool:
        if sys.platform != "win32":
            return False
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="lanbeam-tray")
        self._thread.start()
        self._ready.wait(3)
        return self.ok

    def notify(self, title: str, text: str):
        """气泡提示：告诉用户程序收哪儿去了。"""
        if not self.ok:
            return
        try:
            nid = self._nid
            nid.uFlags = NIF_INFO
            nid.szInfoTitle = title[:60]
            nid.szInfo = text[:240]
            nid.dwInfoFlags = NIIF_INFO | NIIF_NOSOUND
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        except Exception:
            LOG.exception("notify failed")

    def stop(self):
        if self.hwnd:
            try:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass

    # -- 内部 ----------------------------------------------------------
    def _run(self):
        try:
            hinst = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = hinst
            wc.lpszClassName = self._class_name
            user32.RegisterClassW(ctypes.byref(wc))

            # 用普通顶层窗口（不显示）：message-only 窗口当不了前台窗口，
            # 右键菜单可能弹不出来或关不掉，整条托盘线程就卡住了。
            self.hwnd = user32.CreateWindowExW(
                0, self._class_name, self._class_name, 0,
                0, 0, 0, 0, None, None, hinst, None)
            if not self.hwnd:
                LOG.warning("tray window create failed")
                return

            hicon = None
            path = icon_path()
            if path:
                hicon = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0,
                                          LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if not hicon:
                hicon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
            self._hicon = hicon

            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = hicon
            nid.szTip = self.tooltip
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                LOG.warning("Shell_NotifyIcon add failed")
                return
            self._nid = nid
            self.ok = True
            self._ready.set()
            LOG.info("tray icon added hwnd=%s", int(self.hwnd))

            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            LOG.exception("tray thread failed")
        finally:
            self._ready.set()
            self.ok = False

    def _menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, ID_SHOW, "显示 LanBeam")
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "打开收件文件夹")
        user32.AppendMenuW(menu, MF_STRING, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "退出")
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        return cmd

    def _proc(self, hwnd, umsg, wparam, lparam):
        try:
            if umsg == WM_TRAY:
                event = lparam & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.on_show()
                elif event == WM_RBUTTONUP:
                    cmd = self._menu()
                    if cmd == ID_SHOW:
                        self.on_show()
                    elif cmd == ID_OPEN:
                        self.on_open()
                    elif cmd == ID_QUIT:
                        self.on_quit()
                return 0
            if umsg == WM_COMMAND:
                return 0
            if umsg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if umsg == WM_DESTROY:
                try:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                except Exception:
                    pass
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            LOG.exception("tray proc")
        return user32.DefWindowProcW(hwnd, umsg, wparam, lparam)


def tray_selftest() -> int:
    LOG.info("tray selftest start")
    t = Tray("LanBeam selftest", lambda: None, lambda: None, lambda: None)
    ok = t.start()
    print("tray ok:", ok)
    t.stop()
    return 0 if ok else 1
