# -*- coding: utf-8 -*-
"""端到端：启动打包好的 exe，听广播拿令牌，推 200MB 文件 + 一个文件夹，校验落盘。"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "成品" / "LanBeam.exe"
CFG = Path(os.environ["APPDATA"]) / "LanBeam" / "config.json"
INBOX = Path(os.environ["USERPROFILE"]) / "Downloads" / "LanBeam"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


cfg = json.loads(CFG.read_text("utf-8")) if CFG.exists() else {}
cfg.update({"auto_accept": True})
CFG.parent.mkdir(parents=True, exist_ok=True)
CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")

subprocess.run(["taskkill", "/F", "/IM", "LanBeam.exe"], capture_output=True)
time.sleep(0.6)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(("", 47820))
sock.settimeout(1.0)

proc = subprocess.Popen([str(EXE)])
print("exe pid", proc.pid)
token, port = None, None
end = time.time() + 15
while time.time() < end and not token:
    try:
        data, addr = sock.recvfrom(4096)
    except socket.timeout:
        continue
    try:
        o = json.loads(data.decode("utf-8"))
    except Exception:
        continue
    if (o.get("app") == "LanBeam" and o.get("port") == 47821
            and o.get("id") == cfg.get("id")):
        token, port = o.get("token"), o.get("port")

if not token:
    print("RESULT: FAIL (no beacon)")
    proc.terminate()
    sys.exit(1)
print("discovered token", token, "port", port)

py = sys.executable
script = str(ROOT / "脚本" / "lanbeam.py")
ok = True

# ---- 1. 单文件 200MB
src = Path(os.environ["TEMP"]) / "lanbeam_e2e_200mb.bin"
if not src.exists() or src.stat().st_size != 200 * 1024 * 1024:
    block = os.urandom(1 << 20)
    with open(src, "wb") as f:
        for _ in range(200):
            f.write(block)
t0 = time.time()
r = subprocess.run([py, script, "--send-files", str(src), "--to", f"127.0.0.1:{port}",
                    "--token", token], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
dt = time.time() - t0
dst = INBOX / src.name
good = r.returncode == 0 and dst.exists() and sha(src) == sha(dst)
print(f"file 200MB: {'PASS' if good else 'FAIL'}  {dt:.2f}s  {200 / max(dt, .001):.0f} MB/s")
print("  sender:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:200])
ok &= good

# ---- 2. 文件夹（嵌套 + 空目录 + 中文）
root = Path(os.environ["TEMP"]) / "lanbeam_e2e_folder" / "我的资料"
if root.exists():
    shutil.rmtree(root)
(root / "2026" / "十月").mkdir(parents=True)
(root / "空目录").mkdir()
(root / "说明 文档.txt").write_text("LanBeam 文件夹测试", "utf-8")
(root / "2026" / "十月" / "照片 01.bin").write_bytes(os.urandom(3 << 20))
(root / "2026" / "数据.bin").write_bytes(os.urandom(7 << 20))
t0 = time.time()
r = subprocess.run([py, script, "--send-folder", str(root), "--to", f"127.0.0.1:{port}",
                    "--token", token], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
dt = time.time() - t0
base = INBOX / root.name
checks = {
    "text": (base / "说明 文档.txt").exists(),
    "nested": (base / "2026" / "十月" / "照片 01.bin").exists(),
    "big": (base / "2026" / "数据.bin").exists(),
    "emptydir": (base / "空目录").is_dir(),
    "hash": (base / "2026" / "数据.bin").exists()
            and sha(base / "2026" / "数据.bin") == sha(root / "2026" / "数据.bin"),
}
good2 = r.returncode == 0 and all(checks.values())
print(f"folder: {'PASS' if good2 else 'FAIL'}  {dt:.2f}s  {checks}")
print("  sender:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:300])
ok &= good2

# 清理
for p in (dst, base):
    try:
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    except Exception:
        pass
src.unlink(missing_ok=True)
shutil.rmtree(root.parent, ignore_errors=True)
proc.terminate()
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
