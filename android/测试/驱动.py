# -*- coding: utf-8 -*-
"""安卓端核心层对拍测试：桌面 JVM 跑 Java 核心，Python 端跑 LanBeam 官方实现。

在项目里跑：
    javac -encoding UTF-8 -d _build/classes app/src/main/java/com/moyuli/lanbeam/core/*.java 测试/CoreHarness.java
    python 测试/驱动.py
需要 JAVA_HOME（JDK 17+）指向可用的 java。
"""
import hashlib
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent      # .../测试
ANDROID = HERE.parent                        # 安卓端 / android
ROOT = ANDROID.parent                        # 项目根 / 仓库根
SRC = ROOT / "src" if (ROOT / "src" / "lanbeam_core.py").exists() else ROOT / "脚本"
sys.path.insert(0, str(SRC))
import lanbeam_core as lc  # noqa: E402

_JAVA_HOME = os.environ.get("JAVA_HOME", "")
JAVA = str(Path(_JAVA_HOME) / "bin" / ("java.exe" if os.name == "nt" else "java")) if _JAVA_HOME else "java"
CP = str(ANDROID / "_build" / "classes")
TMP = ANDROID / "_build" / "测试数据"

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class JavaProc:
    def __init__(self, mode, base_dir, extra=None, stdin=False):
        args = [JAVA, "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8",
                "-cp", CP, "CoreHarness", mode, str(base_dir)] + (extra or [])
        self.p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                  text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.lines = []
        self.ready = {}
        self.lock = threading.Lock()
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()
        self.wait_ready()

    def _read(self):
        for line in self.p.stdout:
            line = line.rstrip()
            with self.lock:
                self.lines.append(line)
            print("    [java] " + line)
            if line.startswith("READY"):
                for kv in line.split()[1:]:
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        self.ready[k] = v

    def wait_ready(self, timeout=20):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if "port" in self.ready:
                return True
            time.sleep(0.05)
        return False

    def wait_for(self, word, timeout=120):
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.lock:
                for line in self.lines:
                    if word in line:
                        return line
            if self.p.poll() is not None:
                time.sleep(0.2)
                return None
            time.sleep(0.1)
        return None

    def quit(self):
        try:
            if self.p.stdin:
                self.p.stdin.write("quit\n")
                self.p.stdin.flush()
        except Exception:
            pass
        try:
            self.p.wait(timeout=8)
        except Exception:
            self.p.kill()


def new_core(port, inbox):
    inbox.mkdir(parents=True, exist_ok=True)
    cfg = {"id": lc.uuid_hex(8), "name": "PY测试机", "port": port,
           "auto_accept": True, "save_dir": str(inbox)}
    core = lc.Core(cfg, queue.Queue(), inbox)
    core.start()
    time.sleep(0.3)
    return core


def wait_file(path, size, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if path.exists() and path.stat().st_size == size:
            time.sleep(0.3)
            if path.stat().st_size == size:
                return True
        time.sleep(0.2)
    return False


def py_a_dummy():
    cfg = {"id": "dummy", "name": "dummy", "port": 0, "auto_accept": True}
    c = lc.Core.__new__(lc.Core)
    c.cfg = cfg
    c.events = queue.Queue()
    c.emit = lambda *a: None
    c.log = lambda m: print("    [py] " + m)
    return c


def main():
    if TMP.exists():
        shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)

    src = TMP / "原文件-中文名.bin"
    with open(src, "wb") as f:
        chunk = os.urandom(1 << 20)
        for _ in range(12):
            f.write(chunk)
    size = src.stat().st_size
    print(f"测试文件 {src.name} {size} B  sha256={sha(src)[:16]}")

    print("\n[A] 安卓核心 → Python 端接收")
    a_inbox = TMP / "A_py收件"
    py_a = new_core(47831, a_inbox)
    try:
        j = JavaProc("send", TMP / "A_java", [str(src), "127.0.0.1", str(py_a.port), py_a.token])
        line = j.wait_for("RESULT", 180)
        j.p.wait(timeout=30)
        check("A1 Java 发送完成", line is not None and "OK" in line, line or "")
        got = a_inbox / src.name
        ok = got.exists() and got.stat().st_size == size and sha(got) == sha(src)
        check("A2 对方收到且内容一致", ok, f"{got} {got.stat().st_size if got.exists() else 'missing'}")
    finally:
        py_a.stop()

    print("\n[B] Python 端 → 安卓核心接收")
    b_dir = TMP / "B_java"
    j = JavaProc("serve", b_dir, stdin=True)
    try:
        peer = lc.Peer(id="py", name="PY测试机", host="127.0.0.1",
                       port=int(j.ready["port"]), token=j.ready["token"])
        lc.send_batch(py_a_dummy(), peer, [src], on_log=lambda m: print("    [py] " + m))
        got = b_dir / "LanBeam" / src.name
        check("B1 Java 收到文件", wait_file(got, size), str(got))
        check("B2 内容一致", got.exists() and sha(got) == sha(src))
        saved = j.wait_for("EVENT saved", 20)
        check("B3 应用层回调 onSaved", saved is not None, saved or "")
    finally:
        j.quit()

    print("\n[C] 断点续传")
    c_dir = TMP / "C_java"
    j = JavaProc("serve", c_dir, stdin=True)
    try:
        fid = lc.file_fid("", src.name, size)
        parts = c_dir / ".parts"
        parts.mkdir(parents=True, exist_ok=True)
        seed = size // 3
        with open(src, "rb") as f, open(parts / f"{fid}.part", "wb") as out:
            out.write(f.read(seed))
        import urllib.request
        url = f"http://127.0.0.1:{j.ready['port']}/status?fid={fid}"
        with urllib.request.urlopen(url, timeout=5) as r:
            offset = json.loads(r.read().decode())["offset"]
        check("C1 /status 报出 1/3 偏移", offset == seed, f"offset={offset} seed={seed}")
        peer = lc.Peer(id="py", name="PY测试机", host="127.0.0.1",
                       port=int(j.ready["port"]), token=j.ready["token"])
        lc.send_batch(py_a_dummy(), peer, [src], on_log=lambda m: print("    [py] " + m))
        got = c_dir / "LanBeam" / src.name
        check("C2 续传后文件完整", got.exists() and sha(got) == sha(src))
        check("C3 服务端记录了续传", j.wait_for("续传", 5) is not None)
    finally:
        j.quit()

    print("\n[D] 路径安全")
    d_dir = TMP / "D_java"
    j = JavaProc("serve", d_dir, stdin=True)
    try:
        body = json.dumps({"batch": "abc", "kind": "files", "root": "",
                           "files": [["../evil.txt", 5]], "dirs": [], "total": 5}).encode()
        s = socket.create_connection(("127.0.0.1", int(j.ready["port"])), timeout=5)
        req = (b"POST /offer?token=" + j.ready["token"].encode() + b" HTTP/1.1\r\nHost: x\r\n"
               b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        s.sendall(req)
        resp = s.recv(200).decode("latin1")
        s.close()
        check("D1 ../ 越界被 400 拒绝", " 400 " in resp, resp.split("\r\n")[0])
        s = socket.create_connection(("127.0.0.1", int(j.ready["port"])), timeout=5)
        s.sendall(b"GET /status?fid=x HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        resp = s.recv(200).decode("latin1")
        s.close()
        check("D2 /status 无需令牌（协议允许）", " 200 " in resp, resp.split("\r\n")[0])
    finally:
        j.quit()

    print("\n[E] UDP 发现（同机自测，仅参考）")
    e_core = new_core(47833, TMP / "E_py收件")
    try:
        j = JavaProc("discover", TMP / "E_java", ["6"])
        time.sleep(6.5)
        seen = [ln for ln in j.lines if ln.startswith("PEERS ")]
        last = seen[-1] if seen else "(none)"
        print("    Java 端看到：" + last)
        check("E1 Java 能看到 Python 广播", any("PEERS 1" in x or "PEERS 2" in x or "PEERS 3" in x for x in seen), last)
    finally:
        e_core.stop()

    print("\n==== 结果：%d 通过，%d 失败 ====" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：" + ", ".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
