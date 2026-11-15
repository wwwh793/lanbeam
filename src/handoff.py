# -*- coding: utf-8 -*-
"""把「右键 → 通过 LanBeam 发送」选中的路径交给已经在跑的那个实例。

第二个进程（资源管理器拉起来的）只做三件事：把路径写成 JSON 小文件、
敲一下单实例的事件、退出。真正的主实例收到事件后扫目录、读走、删掉。
不碰网络、不加端口，也不依赖命令行窗口。
"""

import json
import os
import time
import uuid
from pathlib import Path


MAX_AGE = 30 * 60  # 秒；超过半小时的旧清单当过期丢掉


def handoff_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    d = Path(base) / "LanBeam" / "handoff"
    d.mkdir(parents=True, exist_ok=True)
    return d


def push(paths) -> int:
    """写一份待处理清单，返回写进去几个路径。"""
    items, seen = [], set()
    for p in paths or []:
        try:
            s = str(Path(str(p)))
        except Exception:
            continue
        if s and s not in seen:
            seen.add(s)
            items.append(s)
    if not items:
        return 0
    name = f"{time.time_ns()}-{os.getpid()}-{uuid.uuid4().hex[:6]}.json"
    tmp = handoff_dir() / (name + ".tmp")
    tmp.write_text(json.dumps({"paths": items, "at": time.time()},
                              ensure_ascii=False), "utf-8")
    tmp.replace(handoff_dir() / name)  # 写完再改名，主实例不会读到半个文件
    return len(items)


def take() -> list:
    """取走所有待处理路径（读完即删，按时间顺序合并去重）。

    超过 MAX_AGE 的旧清单直接丢掉——比如旧版程序没接住的那一条，
    别让用户隔天打开新版时突然冒出一个待发送。
    """
    out = []
    now = time.time()
    try:
        files = sorted(handoff_dir().glob("*.json"))
    except Exception:
        return out
    for f in files:
        try:
            data = json.loads(f.read_text("utf-8"))
        except Exception:
            data = {}
        try:
            f.unlink()
        except Exception:
            pass
        try:
            if now - float(data.get("at") or now) > MAX_AGE:
                continue
        except Exception:
            pass
        for p in data.get("paths") or []:
            if p and p not in out:
                out.append(p)
    return out


def count_pending() -> int:
    try:
        return len(list(handoff_dir().glob("*.json")))
    except Exception:
        return 0
