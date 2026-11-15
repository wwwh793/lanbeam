# -*- coding: utf-8 -*-
"""资源管理器右键菜单：「通过 LanBeam 发送」。

只写当前用户的 Classes（HKCU 下 Software / Classes），不需要管理员、不弹 UAC。
文件和多选走 * / shell，文件夹走 Directory / shell；点一下会把路径用
--send 交给 LanBeam，已经在跑的实例直接收下，没跑的会先起来再接。
路径全部用 os.path.join 拼，源码里不出现反斜杠。
"""

import os
import sys
import winreg
from pathlib import Path

ROOT = os.path.join("Software", "Classes")
VERB_KEY = "LanBeam.Send"
VERB_LABEL = "通过 LanBeam 发送"
TARGETS = (
    os.path.join(ROOT, "*", "shell", VERB_KEY),
    os.path.join(ROOT, "Directory", "shell", VERB_KEY),
)


def exe_path() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    here = Path(__file__).resolve().parent
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    return f'"{exe}" "{here / "lanbeam.py"}"'


def command() -> str:
    p = exe_path()
    if p.startswith('"'):
        return f'{p} --send "%1"'
    return f'"{p}" --send "%1"'


def icon_spec() -> str:
    p = exe_path()
    return p if p.startswith('"') else f'"{p}",0'


def install() -> bool:
    try:
        for key in TARGETS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
                winreg.SetValueEx(k, None, 0, winreg.REG_SZ, VERB_LABEL)
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon_spec())
                winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ,
                                  "Document")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  os.path.join(key, "command")) as k:
                winreg.SetValueEx(k, None, 0, winreg.REG_SZ, command())
        return True
    except OSError:
        return False


def remove() -> bool:
    for key in TARGETS:
        for sub in (os.path.join(key, "command"), key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass
    return True


def _key_exists(key: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            return True
    except OSError:
        return False


def installed_command() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            os.path.join(TARGETS[0], "command")) as k:
            return str(winreg.QueryValueEx(k, None)[0])
    except OSError:
        return ""


def is_installed() -> bool:
    return all(_key_exists(k) for k in TARGETS)


def sync(enabled: bool) -> bool:
    if enabled:
        install()
    else:
        remove()
    return is_installed()
