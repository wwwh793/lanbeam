# -*- coding: utf-8 -*-
"""开机自启：写当前用户的 Run 键（HKCU 下 Software / Microsoft / Windows /
CurrentVersion / Run）。

写 HKCU 不需要管理员，也不往「启动」文件夹里塞快捷方式——注册表这种方式
删得干净，设置里一个开关就能开或关。路径用 os.path.join 拼，源码里不出现反斜杠。
"""

import os
import sys
import winreg
from pathlib import Path

RUN_KEY = os.path.join("Software", "Microsoft", "Windows", "CurrentVersion", "Run")
VALUE_NAME = "LanBeam"


def exe_path() -> str:
    """打包后就是 exe 自己；开发态退化成 pythonw + lanbeam.py，方便测。"""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    here = Path(__file__).resolve().parent
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    return f'"{exe}" "{here / "lanbeam.py"}"'


def command() -> str:
    p = exe_path()
    if p.startswith('"'):
        return f"{p} --tray"
    return f'"{p}" --tray'


def current_value() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return str(val)
    except OSError:
        return ""


def is_enabled() -> bool:
    return bool(current_value())


def install() -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, command())
        return True
    except OSError:
        return False


def remove() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE_NAME)
        return True
    except OSError:
        return False


def sync(enabled: bool) -> bool:
    """设置页开关调用：开就写、关就删，返回最终状态。"""
    if enabled:
        install()
    else:
        remove()
    return is_enabled()
