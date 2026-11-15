# -*- coding: utf-8 -*-
"""单实例：第二次启动不再开新进程，而是把已在运行的那个窗口叫回来。"""

import ctypes
import logging
import threading
from ctypes import wintypes

LOG = logging.getLogger("lanbeam.instance")

MUTEX_NAME = "Local\\LanBeam_SingleInstance_v1"
EVENT_NAME = "Local\\LanBeam_ShowRequest_v1"
ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
INFINITE = 0xFFFFFFFF

kernel32 = ctypes.windll.kernel32
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.OpenMutexW.restype = wintypes.HANDLE
kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]

SYNCHRONIZE = 0x00100000
_mutex = None
_show_event = None


def create_show_event():
    """先建好事件再抢互斥体，避免第二个实例信号发空。"""
    global _show_event
    if _show_event is None:
        _show_event = kernel32.CreateEventW(None, False, False, EVENT_NAME)
    return _show_event


def acquire() -> bool:
    """返回 True 表示本进程是唯一实例；False 表示已有实例在跑。

    不用 GetLastError 判断——ctypes 调用之间可能把它冲掉；
    直接 OpenMutex 探一下更稳。
    """
    global _mutex
    try:
        h = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
        if h:
            kernel32.CloseHandle(h)
            return False
    except Exception:
        pass
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return True


def signal_existing() -> bool:
    h = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, EVENT_NAME)
    if not h:
        return False
    try:
        return bool(kernel32.SetEvent(h))
    finally:
        kernel32.CloseHandle(h)


class ShowListener:
    """在已有实例里等"再启动"信号，收到就把窗口拉回来。"""

    def __init__(self, on_show):
        self.on_show = on_show
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name="lanbeam-instance")
        self.thread.start()

    def _run(self):
        h = _show_event or kernel32.CreateEventW(None, False, False, EVENT_NAME)
        if not h:
            LOG.warning("create show event failed")
            return
        while not self.stop.is_set():
            r = kernel32.WaitForSingleObject(h, 500)
            if r == 0:
                LOG.info("show requested by second launch")
                try:
                    self.on_show()
                except Exception:
                    LOG.exception("show callback")
        kernel32.CloseHandle(h)

    def shutdown(self):
        self.stop.set()
