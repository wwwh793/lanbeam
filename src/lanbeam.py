#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LanBeam 入口：图形界面 / 命令行 / 自检。"""

import argparse
import hashlib
import http.client
import json
import os
import queue
import sys
import tempfile
import time
from pathlib import Path

import handoff
from lanbeam_core import (APP_NAME, DEFAULT_HTTP_PORT, VERSION, Core, Peer,
                          file_fid, human, load_config, save_config, send_batch)
from lanbeam_ui import App


def _runtime_file() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME / "running.json"


def _running_info() -> dict:
    try:
        return json.loads(_runtime_file().read_text("utf-8"))
    except Exception:
        return {}


def _pid_alive(pid) -> bool:
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def _write_running() -> None:
    try:
        p = _runtime_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"version": VERSION, "pid": os.getpid(),
                                 "exe": sys.executable}, ensure_ascii=False),
                     "utf-8")
    except Exception:
        pass


def _clear_running() -> None:
    try:
        p = _runtime_file()
        info = json.loads(p.read_text("utf-8"))
        if int(info.get("pid") or 0) == os.getpid():
            p.unlink()
    except Exception:
        pass


def _warn_old_version(ver: str) -> None:
    """已经在跑的是另一个版本：说清楚要先退出旧的，别让人以为新版打不开。"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        try:
            messagebox.showwarning(
                APP_NAME,
                f"现在运行的是 {ver}，跟这个 v{VERSION} 不是同一版。\n\n"
                "先在托盘图标上右键 →「退出」，再重新打开，就能换上新版。\n"
                "（两版共用一个单实例锁，旧版不退，新版只会把旧窗口叫出来。）",
                parent=root)
        finally:
            root.destroy()
    except Exception:
        pass


def run_gui(port=None, send=None, tray=False) -> int:
    from lanbeam_instance import acquire, create_show_event, signal_existing
    create_show_event()
    if send:
        # 先把路径放下，再敲门；主实例被叫醒时一定能读到
        handoff.push(send)
    if not acquire():
        # 已经有实例在跑：把它叫回前台，然后自己安静退出
        info = _running_info()
        try:
            # 没有 running.json 说明在跑的是 1.7.0 之前的版本（它不写这个文件）
            same = (info.get("version") == VERSION
                    and _pid_alive(info.get("pid")))
            if not same:
                ver = f"v{info['version']}" if info.get("version") else "旧版本的 LanBeam"
                _warn_old_version(ver)
        except Exception:
            pass
        signal_existing()
        return 0
    _write_running()
    cfg = load_config()
    if port:
        cfg["port"] = int(port)
    core = Core(cfg, queue.Queue())
    cfg["port"] = core.port
    save_config(cfg)
    try:
        core.start()
    except Exception as e:
        try:
            from tkinter import messagebox
            messagebox.showerror(APP_NAME, f"启动失败：{e}")
        except Exception:
            pass
        return 1
    app = App(core, start_in_tray=tray)
    try:
        app.mainloop()
    finally:
        _clear_running()
    return 0


def headless_serve(port=None, downloads=None) -> int:
    cfg = load_config()
    if port:
        cfg["port"] = int(port)
    cfg["auto_accept"] = True
    inbox = Path(downloads) if downloads else None
    core = Core(cfg, queue.Queue(), inbox=inbox)
    core.start()
    print(f"{APP_NAME} serving on 0.0.0.0:{core.port}  token={core.token}")
    print(f"inbox: {core.inbox}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        core.stop()
    return 0


def headless_send(to: str, token: str, paths) -> int:
    host, port = to.rsplit(":", 1)
    peer = Peer(id="cli", name="cli", host=host, port=int(port), token=token.upper())
    cfg = {"id": "cli", "name": "cli", "port": 0, "auto_accept": True,
           "trusted": {}}
    core = Core(cfg, queue.Queue())
    try:
        send_batch(core, peer, [Path(p) for p in paths],
                   on_progress=lambda f, t, d: print(f"  {f * 100:5.1f}%  {t}  {d}"),
                   on_log=lambda m: print("  " + m))
    except Exception as e:
        print(f"FAIL {e}")
        return 1
    print("OK")
    return 0


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _make(path: Path, mb: int):
    block = os.urandom(1 << 20)
    with open(path, "wb") as f:
        for _ in range(mb):
            f.write(block)


def selftest() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lanbeam-test-"))
    inbox = tmp / "Downloads" / "LanBeam"
    cfg = {"id": "selftest-id", "name": "selftest", "port": 0,
           "auto_accept": True, "trusted": {}}
    core = Core(cfg, queue.Queue(), inbox=inbox)
    core._start_server()
    peer = Peer(id="self", name="self", host="127.0.0.1", port=core.port,
                token=core.token)
    ok = True

    # 1) 单文件
    src = tmp / "plain_48mb.bin"
    _make(src, 48)
    t0 = time.time()
    send_batch(core, peer, [src])
    dt = time.time() - t0
    dst = inbox / src.name
    good = dst.exists() and _sha(src) == _sha(dst)
    print(f"case1 单文件 48MB: {'PASS' if good else 'FAIL'}  {dt:.2f}s  "
          f"{48 / max(dt, 0.001):.0f} MB/s")
    ok &= good

    # 2) 断点续传
    src2 = tmp / "resume_24mb.bin"
    _make(src2, 24)
    fid = file_fid("", src2.name, src2.stat().st_size)
    core.parts.mkdir(parents=True, exist_ok=True)
    (core.parts / f"{fid}.part").write_bytes(src2.read_bytes()[: 8 << 20])
    t0 = time.time()
    send_batch(core, peer, [src2])
    dt2 = time.time() - t0
    dst2 = inbox / src2.name
    good2 = dst2.exists() and _sha(src2) == _sha(dst2)
    print(f"case2 断点续传 24MB(8MB): {'PASS' if good2 else 'FAIL'}  {dt2:.2f}s")
    ok &= good2

    # 3) 错误令牌
    try:
        bad = Peer(id="bad", name="bad", host="127.0.0.1", port=core.port,
                   token="000000")
        send_batch(core, bad, [src2])
        print("case3 错误令牌: FAIL（竟然放行）")
        ok = False
    except Exception:
        print("case3 错误令牌: PASS（已拒绝）")

    # 4) 文件夹（含空目录、中文名、嵌套）
    root = tmp / "我的照片"
    (root / "2026" / "10月").mkdir(parents=True)
    (root / "空文件夹").mkdir()
    (root / "说明.txt").write_text("hello lanbeam", "utf-8")
    _make(root / "2026" / "10月" / "风景 01.bin", 6)
    _make(root / "2026" / "big.bin", 9)
    send_batch(core, peer, [root])
    base = inbox / "我的照片"
    checks = [
        (base / "说明.txt").exists(),
        (base / "2026" / "10月" / "风景 01.bin").exists(),
        (base / "2026" / "big.bin").exists(),
        (base / "空文件夹").is_dir(),
        _sha(base / "2026" / "big.bin") == _sha(root / "2026" / "big.bin"),
    ]
    good4 = all(checks)
    print(f"case4 文件夹（嵌套/空目录/中文）: {'PASS' if good4 else 'FAIL'}  {checks}")
    ok &= good4

    # 5) 路径穿越必须被挡
    try:
        conn = http.client.HTTPConnection("127.0.0.1", core.port, timeout=10)
        body = json.dumps({"batch": "evil", "kind": "files", "root": "",
                           "files": [["../evil.txt", 10]], "dirs": [],
                           "total": 10}).encode()
        conn.request("POST", f"/offer?token={core.token}", body=body,
                     headers={"Content-Type": "application/json"})
        code = conn.getresponse().status
        conn.close()
        good5 = code == 400
        print(f"case5 路径穿越: {'PASS' if good5 else 'FAIL'}（HTTP {code}）")
        ok &= good5
    except Exception as e:
        print(f"case5 路径穿越: FAIL {e}")
        ok = False

    core.stop()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=APP_NAME, description="局域网文件互传")
    ap.add_argument("--serve", action="store_true", help="无界面接收")
    ap.add_argument("--send-files", nargs="+", metavar="FILE", help="发文件")
    ap.add_argument("--send-folder", metavar="DIR", help="发文件夹")
    ap.add_argument("--to", help="目标 host:port")
    ap.add_argument("--token", help="目标令牌")
    ap.add_argument("--port", type=int, help="监听端口")
    ap.add_argument("--downloads", help="收件目录（默认 下载/LanBeam）")
    ap.add_argument("--send", nargs="+", metavar="PATH",
                    help="把文件/文件夹交给 LanBeam 发送（资源管理器右键菜单用）")
    ap.add_argument("--tray", action="store_true",
                    help="启动后直接收进托盘（开机自启用）")
    ap.add_argument("--selftest", action="store_true", help="内部自检")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.serve:
        return headless_serve(args.port, args.downloads)
    if args.send_files or args.send_folder:
        if not args.to or not args.token:
            print("需要 --to 与 --token")
            return 2
        paths = args.send_files or [args.send_folder]
        return headless_send(args.to, args.token, paths)
    return run_gui(args.port, send=args.send, tray=args.tray)


if __name__ == "__main__":
    sys.exit(main())
