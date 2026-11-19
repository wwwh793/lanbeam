# -*- coding: utf-8 -*-
"""LanBeam 传输内核：与界面无关，便于以后原样移植到鸿蒙（ArkTS 只替换 UI 层）。"""

import hashlib
import http.client
import json
import logging
import os
import queue
import secrets
import shutil
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from version import VERSION  # 版本号唯一来源，规则见 version.py

APP_NAME = "LanBeam"
DISCOVERY_PORT = 47820
DEFAULT_HTTP_PORT = 47821
CHUNK = 1 << 20
PEER_TTL = 30          # 掉线判定上限（后台广播稀疏时）
PEER_TTL_MIN = 8       # 掉线判定下限（前台广播 2 秒时，杀进程约 8 秒消失）
BEACON_INTERVAL = 2.0
INBOX_NAME = "LanBeam"


# ------------------------------------------------------------------ 路径与配置

def _localappdata() -> Path:
    p = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    d = Path(p) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _appdata() -> Path:
    p = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    d = Path(p) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def downloads_dir() -> Path:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
        p = Path(os.path.expandvars(str(val)))
        if p.is_dir():
            return p
    except Exception:
        pass
    p = Path.home() / "Downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_logging() -> logging.Logger:
    log = logging.getLogger("lanbeam")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    path = _localappdata() / "lanbeam.log"
    try:
        if path.exists() and path.stat().st_size > 1_000_000:
            path.replace(path.with_suffix(".old.log"))
    except Exception:
        pass
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    return log


LOG = setup_logging()


def uuid_hex(n=8) -> str:
    return secrets.token_hex(n)


def default_name() -> str:
    return (os.environ.get("COMPUTERNAME") or "Windows").strip() or "Windows"


def load_config() -> dict:
    path = _appdata() / "config.json"
    cfg = {}
    try:
        cfg = json.loads(path.read_text("utf-8"))
    except Exception:
        pass
    cfg.setdefault("id", uuid_hex())
    cfg.setdefault("name", default_name())
    cfg.setdefault("port", DEFAULT_HTTP_PORT)
    cfg.setdefault("auto_accept", False)
    cfg.setdefault("trusted", {})
    cfg.setdefault("keep_awake", True)
    return cfg


def save_config(cfg: dict) -> None:
    try:
        (_appdata() / "config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        LOG.exception("save config failed")


def human(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def safe_segment(name: str) -> str:
    name = (name or "file").replace("\\", "_").replace("/", "_")
    name = "".join(c for c in name if ord(c) >= 32 and c not in '<>:"|?*')
    name = name.strip().rstrip(". ")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
        f"LPT{i}" for i in range(1, 10)}
    if not name or name.upper() in reserved:
        name = f"item_{secrets.token_hex(3)}"
    return name[:120]


def safe_relpath(rel: str) -> Path:
    """把对方给的相对路径洗成安全的本地路径，拒绝穿越。"""
    rel = (rel or "").replace("\\", "/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts:
        raise ValueError("空路径")
    for p in parts:
        if p == ".." or len(p) > 120 or ":" in p:
            raise ValueError(f"非法路径: {rel}")
    return Path(*[safe_segment(p) for p in parts])


def unique_path(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for i in range(1, 10000):
        cand = folder / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
    return folder / f"{stem}_{secrets.token_hex(3)}{suffix}"


def unique_dir(folder: Path, name: str) -> Path:
    target = folder / safe_segment(name)
    if not target.exists():
        return target
    for i in range(1, 10000):
        cand = folder / f"{target.name} ({i})"
        if not cand.exists():
            return cand
    return folder / f"{target.name}_{secrets.token_hex(3)}"


def file_fid(root: str, rel: str, size: int) -> str:
    raw = f"{root}/{rel}|{size}".encode("utf-8", "surrogateescape")
    return hashlib.sha256(raw).hexdigest()[:16]


def local_ips() -> set:
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    return {ip for ip in ips if not ip.startswith("127.")}


def ipv4_interfaces() -> list:
    """当前网卡的 [(ip, mask)]，走 iphlpapi 的 GetIpAddrTable，不依赖第三方库。

    Windows 上只靠 255.255.255.255 会被"跃点最低"的网卡接走——这台机器上是
    VMware 虚拟网卡（35 < WLAN 45），广播根本到不了真实局域网。所以必须按网卡
    算出各自子网广播地址，并绑着源地址发。
    """
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class ROW(ctypes.Structure):
            _fields_ = [("dwAddr", wintypes.DWORD), ("dwIndex", wintypes.DWORD),
                        ("dwMask", wintypes.DWORD), ("dwBCastAddr", wintypes.DWORD),
                        ("dwReasmSize", wintypes.DWORD),
                        ("unused1", ctypes.c_ushort), ("wType", ctypes.c_ushort)]

        size = wintypes.ULONG(0)
        ctypes.windll.iphlpapi.GetIpAddrTable(None, ctypes.byref(size), 0)
        if size.value < 8:
            return []
        buf = ctypes.create_string_buffer(size.value)
        if ctypes.windll.iphlpapi.GetIpAddrTable(buf, ctypes.byref(size), 0) != 0:
            return []
        count = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
        rows = ctypes.cast(ctypes.addressof(buf) + 4, ctypes.POINTER(ROW))
        out = []
        for i in range(count):
            row = rows[i]
            ip = socket.inet_ntoa(struct.pack("<L", row.dwAddr))
            mask = socket.inet_ntoa(struct.pack("<L", row.dwMask))
            if ip.startswith("127.") or ip == "0.0.0.0":
                continue
            out.append((ip, mask))
        return out
    except Exception:
        return []


def broadcast_addr(ip: str, mask: str) -> str:
    ip_i = struct.unpack("!I", socket.inet_aton(ip))[0]
    mask_i = struct.unpack("!I", socket.inet_aton(mask))[0]
    return socket.inet_ntoa(struct.pack("!I", ip_i | (~mask_i & 0xFFFFFFFF)))


def broadcast_targets() -> list:
    """每张网卡的真实子网广播地址（按掩码算，不是按 /24 猜）。"""
    targets = {"255.255.255.255"}
    rows = ipv4_interfaces()
    if rows:
        for ip, mask in rows:
            try:
                targets.add(broadcast_addr(ip, mask))
            except OSError:
                continue
    else:
        for ip in local_ips():
            parts = ip.split(".")
            if len(parts) == 4:
                targets.add(".".join(parts[:3] + ["255"]))
    return sorted(targets)


# ------------------------------------------------------------------ 发现

@dataclass
class Peer:
    id: str
    name: str
    host: str
    port: int
    token: str = ""
    last_seen: float = field(default_factory=time.time)
    # 对方广播的平均间隔：前台约 2 秒，息屏后台会被系统拉长到 10 秒以上。
    # 掉线时间按它算（见 snapshot），否则后台的平板会在列表里反复闪现。
    interval: float = 2.0

    @property
    def label(self) -> str:
        return f"{self.name}  ({self.host}:{self.port})"


class Discovery:
    def __init__(self, core):
        self.core = core
        self.peers = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.sock = None
        self.tx = {}
        self.port = DISCOVERY_PORT
        self.shared_port = False
        self.rx_count = 0
        self.rx_seen = {}
        self.last_rx = 0.0
        self._last_reply = {}

    def start(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                s.bind(("", DISCOVERY_PORT))
                self.port = DISCOVERY_PORT
            except OSError:
                # 端口被别的实例占用：改用临时端口，靠单播回执互相发现
                s.bind(("", 0))
                self.port = s.getsockname()[1]
                self.shared_port = True
                LOG.warning("discovery port busy, fallback to %s", self.port)
            s.settimeout(1.0)
            self.sock = s
        except Exception:
            LOG.exception("discovery socket failed")
            return
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._beacon, daemon=True).start()

    def restart(self) -> int:
        self.stop.set()
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass
        self._close_tx()
        self.stop = threading.Event()
        self.sock = None
        self.start()
        return self.port

    def _tx_socket(self, ip: str):
        """绑在指定网卡上的发送 socket：源地址定死了，广播才会从这张网卡出去。"""
        s = self.tx.get(ip)
        if s is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((ip, 0))
            self.tx[ip] = s
        return s

    def _close_tx(self):
        for s in self.tx.values():
            try:
                s.close()
            except Exception:
                pass
        self.tx.clear()

    def _broadcast(self, payload):
        rows = ipv4_interfaces()
        if not rows:
            for addr in broadcast_targets():
                try:
                    self.sock.sendto(payload, (addr, DISCOVERY_PORT))
                except Exception:
                    pass
            return
        for ip, mask in rows:
            try:
                subnet = broadcast_addr(ip, mask)
            except OSError:
                continue
            for dst in (subnet, "255.255.255.255"):
                try:
                    self._tx_socket(ip).sendto(payload, (dst, DISCOVERY_PORT))
                except Exception:
                    try:
                        self._tx_socket(ip).close()
                    except Exception:
                        pass
                    self.tx.pop(ip, None)

    def _payload(self, ack: bool = False) -> bytes:
        msg = {"app": APP_NAME, "v": 2, "id": self.core.peer_id,
               "name": self.core.name, "port": self.core.port,
               "rport": self.port,
               "token": self.core.token}
        # ack=1 表示"这是对收到广播的即时回执"，收到回执不再回执，避免两边互相刷屏
        if ack:
            msg["ack"] = 1
        return json.dumps(msg, ensure_ascii=False).encode("utf-8")

    def kick(self):
        """点「刷新」时立刻催一轮：广播一次，对方收到会立刻单播回执。"""
        try:
            self._broadcast(self._payload())
        except Exception:
            LOG.exception("kick failed")

    def _beacon(self):
        while not self.stop.is_set():
            try:
                self._broadcast(self._payload())
            except Exception:
                LOG.exception("beacon failed")
            self.stop.wait(BEACON_INTERVAL)

    def _listen(self):
        while not self.stop.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                break
            try:
                obj = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if obj.get("app") != APP_NAME or obj.get("id") == self.core.peer_id:
                continue
            try:
                peer = Peer(id=str(obj.get("id")), name=str(obj.get("name") or "未知设备"),
                            host=addr[0], port=int(obj.get("port") or 0),
                            token=str(obj.get("token") or ""))
            except Exception:
                continue
            if not peer.port:
                continue
            now = time.time()
            with self.lock:
                # 同一台设备重启后 id 会变：地址一样就把旧条目顶掉，别在界面上留两行
                for key in [k for k, p in self.peers.items()
                            if k != peer.id and p.host == peer.host and p.port == peer.port]:
                    LOG.info("设备重启，替换旧条目：%s (%s:%s)", peer.name, peer.host, peer.port)
                    del self.peers[key]
                old = self.peers.get(peer.id)
                if old is not None:
                    gap = now - old.last_seen
                    if 0.2 < gap < 60:
                        peer.interval = max(1.0, min(30.0, 0.7 * old.interval + 0.3 * gap))
                    else:
                        peer.interval = old.interval
                else:
                    LOG.info("发现 %s (%s:%s)", peer.name, peer.host, peer.port)
                peer.last_seen = now
                self.peers[peer.id] = peer
                self.rx_count += 1
                self.rx_seen[addr[0]] = peer.name
                self.last_rx = time.time()
            # 收到对方广播就立刻单播回一条：不用等我们下一个 2 秒周期，发现瞬间完成
            if not obj.get("ack"):
                now = time.time()
                if now - self._last_reply.get(addr[0], 0) >= 0.2:
                    self._last_reply[addr[0]] = now
                    try:
                        rport = int(obj.get("rport") or DISCOVERY_PORT)
                        self.sock.sendto(self._payload(ack=True),
                                         (addr[0], rport or DISCOVERY_PORT))
                    except Exception:
                        pass

    def _ttl(self, peer: Peer) -> float:
        """按对方自己的广播节奏算掉线时间：前台 2 秒 → 8 秒判死；后台 12 秒 → 30 秒判死。
        这样前台用着的时候杀进程几秒就消失，后台挂着的平板又不会一闪一闪。"""
        return max(PEER_TTL_MIN, min(PEER_TTL, peer.interval * 3.0))

    def snapshot(self) -> list:
        now = time.time()
        with self.lock:
            for k in [k for k, p in self.peers.items() if now - p.last_seen > self._ttl(p)]:
                gone = self.peers[k]
                LOG.info("设备离线 %s (%s:%s)", gone.name, gone.host, gone.port)
                del self.peers[k]
            return sorted(self.peers.values(), key=lambda p: p.name.lower())

    def remember(self, peer: Peer):
        with self.lock:
            self.peers[peer.id] = peer


# ------------------------------------------------------------------ 内核

class AppHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


class Core:
    def __init__(self, cfg, events: queue.Queue, inbox: Path = None):
        self.cfg = cfg
        self.events = events
        self.downloads = downloads_dir()
        saved_dir = cfg.get("save_dir")
        if inbox:
            self.inbox = Path(inbox)
        elif saved_dir:
            self.inbox = Path(saved_dir)
        else:
            self.inbox = self.downloads / INBOX_NAME
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.parts = self.inbox / ".parts"
        self.parts.mkdir(parents=True, exist_ok=True)
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(self.parts), 2)
        except Exception:
            pass
        self.peer_id = cfg["id"]
        self.name = cfg["name"]
        self.token = secrets.token_hex(3).upper()
        port = cfg.get("port", DEFAULT_HTTP_PORT)
        self.port = int(port) if port is not None else DEFAULT_HTTP_PORT
        self.server = None
        self.discovery = Discovery(self)
        self.batches = {}
        self.batch_lock = threading.Lock()
        self.send_lock = threading.Lock()

    def peer_name_for(self, host: str) -> str:
        for p in self.discovery.snapshot():
            if p.host == host:
                return p.name
        return host

    def emit(self, *ev):
        self.events.put(ev)

    def log(self, msg: str):
        LOG.info(msg)
        self.emit("log", msg)

    def ask_offer(self, sender: str, kind: str, root: str, nfiles: int,
                  total: int) -> bool:
        if self.cfg.get("auto_accept"):
            return True
        if sender in (self.cfg.get("trusted") or {}):
            return True
        ev = threading.Event()
        box = {}
        self.emit("offer", (sender, kind, root, nfiles, total), ev, box)
        ev.wait(300)
        return bool(box.get("ok"))

    def set_inbox(self, path) -> None:
        self.inbox = Path(path)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.parts = self.inbox / ".parts"
        self.parts.mkdir(parents=True, exist_ok=True)
        self.cfg["save_dir"] = str(self.inbox)
        save_config(self.cfg)

    def start(self):
        self._start_server()
        self.discovery.start()
        if self.discovery.shared_port:
            self.emit("log", f"发现端口 47820 被占用，已切换到备用端口 {self.discovery.port}")
        else:
            self.emit("log", f"发现端口 {self.discovery.port} 就绪")

    def _start_server(self):
        for attempt in range(4):
            port = self.port if attempt == 0 else 0
            try:
                httpd = AppHTTPServer(("0.0.0.0", port), Handler)
                httpd.core = self
                self.port = httpd.server_address[1]
                self.server = httpd
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                LOG.info("listening on %s", self.port)
                return
            except OSError:
                LOG.warning("port busy, retry")
        raise RuntimeError("无法监听端口")

    def stop(self):
        self.discovery.stop.set()
        if self.server:
            self.server.shutdown()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"{APP_NAME}/{VERSION}"
    disable_nagle_algorithm = True
    timeout = 300

    def log_message(self, fmt, *args):
        pass

    @property
    def core(self) -> Core:
        return self.server.core

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _authed(self, q) -> bool:
        return secrets.compare_digest((q.get("token") or [""])[0], self.core.token)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/hello":
            return self._json({"app": APP_NAME, "v": 2, "name": self.core.name,
                               "id": self.core.peer_id})
        if u.path == "/status":
            fid = (q.get("fid") or [""])[0]
            part = self.core.parts / f"{fid}.part"
            return self._json({"offset": part.stat().st_size if part.exists() else 0})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/offer":
            return self._offer(u)
        if u.path == "/upload":
            return self._upload(u)
        return self._json({"error": "not found"}, 404)

    # -- 批次协商 ------------------------------------------------------
    def _offer(self, u):
        q = parse_qs(u.query)
        if not self._authed(q):
            return self._json({"error": "bad token"}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8"))
            batch = str(body["batch"])
            kind = body.get("kind") or "files"
            root = str(body.get("root") or "")
            files = body.get("files") or []
            dirs = body.get("dirs") or []
            total = int(body.get("total") or 0)
            if kind not in ("files", "folder") or not batch:
                raise ValueError("bad batch")
            for rel in [f[0] for f in files] + list(dirs):
                safe_relpath(rel)
        except Exception as e:
            return self._json({"error": f"bad offer: {e}"}, 400)

        core = self.core
        with core.batch_lock:
            rec = core.batches.get(batch)
        if rec:
            return self._json({"ok": True, "dir": str(rec["dir"]), "repeat": True})

        sender = self.client_address[0]
        if not core.ask_offer(sender, kind, root, len(files), total):
            core.log(f"已拒绝来自 {sender} 的 {root or '文件'}")
            return self._json({"error": "rejected"}, 403)

        try:
            if kind == "folder":
                target = unique_dir(core.inbox, root or "未命名文件夹")
            else:
                target = core.inbox
            target.mkdir(parents=True, exist_ok=True)
            for rel in dirs:
                (target / safe_relpath(rel)).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

        with core.batch_lock:
            core.batches[batch] = {"kind": kind, "root": root, "dir": target,
                                   "sender": sender, "total": max(total, 1),
                                   "done": 0, "files": {f[0]: f[1] for f in files},
                                   "finished": set()}
        core.log(f"接收 {kind == 'folder' and root or '文件'}：{len(files)} 个文件，"
                 f"{human(total)}，来自 {sender}")
        return self._json({"ok": True, "dir": str(target)})

    # -- 收文件 --------------------------------------------------------
    def _upload(self, u):
        q = parse_qs(u.query)
        core = self.core
        if not self._authed(q):
            return self._json({"error": "bad token"}, 403)
        try:
            batch = (q.get("batch") or [""])[0]
            fid = (q.get("fid") or [""])[0]
            rel = unquote((q.get("path") or [""])[0])
            size = int((q.get("size") or ["0"])[0])
            offset = int(self.headers.get("X-Offset") or 0)
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            return self._json({"error": "bad request"}, 400)

        with core.batch_lock:
            rec = core.batches.get(batch)
        if not rec:
            return self._json({"error": "unknown batch"}, 409)
        try:
            dest_rel = safe_relpath(rel)
        except Exception as e:
            return self._json({"error": str(e)}, 400)

        if size <= 0 or not fid or offset < 0 or size - offset != length:
            return self._json({"error": "bad size"}, 400)

        part = core.parts / f"{fid}.part"
        if offset > 0 and (not part.exists() or part.stat().st_size != offset):
            return self._json({"error": "resume mismatch"}, 409)
        if offset == 0 and part.exists() and part.stat().st_size == size:
            part.unlink(missing_ok=True)

        try:
            f = open(part, "wb") if offset == 0 else open(part, "r+b")
            if offset:
                f.seek(offset)
                f.truncate()
            with f:
                remaining = length
                started = time.time()
                last = 0.0
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK, remaining))
                    if not chunk:
                        raise IOError("客户端中断")
                    f.write(chunk)
                    remaining -= len(chunk)
                    now = time.time()
                    if now - last > 0.15:
                        last = now
                        done = rec["done"] + (size - remaining)
                        speed = (size - remaining) / max(now - started, 0.001)
                        core.emit("progress", done / rec["total"],
                                  f"接收 {rel}", f"{human(speed)}/s · "
                                  f"{done * 100 // max(rec['total'], 1)}%")
            if part.stat().st_size != size:
                raise IOError("大小不符")
        except Exception as e:
            core.log(f"接收失败 {rel}: {e}")
            return self._json({"error": str(e)}, 500)

        try:
            dest = rec["dir"] / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest = unique_path(dest.parent, dest.name)
            shutil.move(str(part), str(dest))
        except Exception as e:
            core.log(f"保存失败 {dest_rel}: {e}")
            return self._json({"error": str(e)}, 500)

        with core.batch_lock:
            if rel not in rec["finished"]:
                rec["finished"].add(rel)
                rec["done"] += size
        core.emit("progress", min(1.0, rec["done"] / rec["total"]),
                  f"接收 {rel}", f"{rec['done'] * 100 // max(rec['total'], 1)}%")
        core.log(f"已接收 {dest}")
        core.emit("done", str(dest))
        return self._json({"ok": True, "path": str(dest)})


# ------------------------------------------------------------------ 发送

def _offer(core, peer: Peer, batch: dict) -> dict:
    qs = urlencode({"token": peer.token})
    body = json.dumps(batch, ensure_ascii=False).encode("utf-8")
    conn = http.client.HTTPConnection(peer.host, peer.port, timeout=30)
    try:
        conn.request("POST", f"/offer?{qs}", body=body,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8") or "{}")
        if resp.status != 200:
            raise IOError(data.get("error") or f"HTTP {resp.status}")
        return data
    finally:
        conn.close()


def _hello(host, port, timeout=4.0) -> dict:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", "/hello")
        data = json.loads(conn.getresponse().read().decode("utf-8") or "{}")
        if data.get("app") != APP_NAME:
            raise IOError("对方端口被别的程序占用了")
        return data
    finally:
        conn.close()


def _status(host, port, fid, timeout=8) -> int:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", f"/status?fid={fid}")
        data = json.loads(conn.getresponse().read().decode("utf-8") or "{}")
        return int(data.get("offset") or 0)
    finally:
        conn.close()


def build_manifest(paths) -> dict:
    """把选中的文件/文件夹整理成一次发送的清单。"""
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("没有选中任何东西")
    dirs = []
    files = []
    if len(paths) == 1 and paths[0].is_dir():
        root = paths[0].name
        kind = "folder"
        for dirpath, dirnames, filenames in os.walk(paths[0]):
            base = Path(dirpath)
            rel_base = base.relative_to(paths[0]).as_posix()
            if rel_base == ".":
                rel_base = ""
            for d in dirnames:
                rel = f"{rel_base}/{d}" if rel_base else d
                dirs.append(rel)
            for fn in filenames:
                p = base / fn
                rel = f"{rel_base}/{fn}" if rel_base else fn
                files.append((rel, p))
    else:
        kind = "files"
        root = ""
        for p in paths:
            if p.is_dir():
                raise ValueError("一次只能发一个文件夹，或者多个文件")
            files.append((p.name, p))
    total = sum(p.stat().st_size for _, p in files)
    batch_id = uuid.uuid4().hex
    return {
        "batch": batch_id,
        "kind": kind,
        "root": root,
        "files": [[rel, p.stat().st_size] for rel, p in files],
        "dirs": dirs,
        "total": total,
        "_local": files,
    }


class TransferCancelled(IOError):
    pass


class TransferControl:
    """发送线程的暂停/取消开关，UI 只改标志位。"""

    def __init__(self):
        self.cancelled = False
        self.paused = False
        self._lock = threading.Lock()

    def cancel(self):
        with self._lock:
            self.cancelled = True
            self.paused = False

    def set_paused(self, on: bool):
        with self._lock:
            if not self.cancelled:
                self.paused = bool(on)

    def checkpoint(self):
        if self.cancelled:
            raise TransferCancelled("已取消")
        while True:
            with self._lock:
                paused = self.paused and not self.cancelled
            if not paused:
                break
            time.sleep(0.1)
        if self.cancelled:
            raise TransferCancelled("已取消")


def send_batch(core, peer: Peer, paths, on_progress=None, on_log=None,
               control: TransferControl = None) -> int:
    """发送一批文件/一个文件夹，返回成功发送的字节数。"""
    manifest = build_manifest(paths)
    files = manifest.pop("_local")
    root = manifest["root"]

    try:
        _hello(peer.host, peer.port)
    except ConnectionRefusedError:
        raise IOError(f"{peer.name} 上没有程序在监听 {peer.port} 端口，对方可能刚关掉 LanBeam。")
    except (socket.timeout, TimeoutError):
        raise IOError(
            f"连不上 {peer.name}（{peer.host}:{peer.port}）：对方没响应。\n"
            "最常见的原因是对面电脑的 Windows 防火墙拦了入站连接。\n"
            "让对方右键「放行防火墙（管理员运行）.bat」→ 以管理员身份运行，再试一次。")
    except OSError as e:
        raise IOError(f"连不上 {peer.name}（{peer.host}:{peer.port}）：{e}")

    try:
        _offer(core, peer, manifest)
    except IOError as e:
        raise IOError(f"对方没有接受这次发送：{e}")

    total = max(manifest["total"], 1)
    done_before = 0
    sent_all = 0
    for rel, path in files:
        size = path.stat().st_size
        fid = file_fid(root, rel, size)
        try:
            offset = _status(peer.host, peer.port, fid)
        except Exception:
            offset = 0
        if offset >= size:
            offset = 0
        qs = urlencode({"token": peer.token, "batch": manifest["batch"],
                        "fid": fid, "path": rel, "size": size})
        conn = http.client.HTTPConnection(peer.host, peer.port, timeout=120)
        conn.putrequest("POST", f"/upload?{qs}")
        conn.putheader("Content-Length", str(size - offset))
        conn.putheader("X-Offset", str(offset))
        conn.putheader("Connection", "close")
        conn.endheaders()
        sent = offset
        started = time.time()
        last = 0.0
        buf = bytearray(CHUNK)
        view = memoryview(buf)
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                while sent < size:
                    if control is not None:
                        control.checkpoint()
                    n = f.readinto(buf)
                    if not n:
                        break
                    conn.send(view[:n])
                    sent += n
                    now = time.time()
                    if on_progress and now - last > 0.12:
                        last = now
                        overall = (done_before + sent) / total
                        speed = (sent - offset) / max(now - started, 0.001)
                        on_progress(overall, f"{root or '文件'} · {rel}",
                                    f"{human(speed)}/s · {overall * 100:.0f}%")
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", "replace")
        finally:
            conn.close()
        if resp.status != 200:
            raise IOError(f"传输被拒绝：HTTP {resp.status} {body}")
        done_before += size
        sent_all += size
        if on_log:
            on_log(f"已发送 {rel}")

    if on_progress:
        on_progress(1.0, root or "文件", "完成")
    return sent_all
