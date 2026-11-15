# -*- coding: utf-8 -*-
"""验证 UDP 广播确实发出去了：先占住发现端口，再启动 LanBeam，听 8 秒。"""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.bind(("", 47820))
s.settimeout(1.5)

exe = Path(__file__).with_name("lanbeam.py")
p = subprocess.Popen([sys.executable, str(exe), "--serve", "--port", "47899"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
seen = {}
end = time.time() + 8
while time.time() < end:
    try:
        data, addr = s.recvfrom(4096)
    except socket.timeout:
        continue
    try:
        o = json.loads(data.decode("utf-8"))
    except Exception:
        continue
    if o.get("app") == "LanBeam":
        seen[o["id"]] = (addr[0], o.get("name"), o.get("port"), o.get("token"))
p.terminate()
print("beacons:", seen)
print("RESULT:", "PASS" if seen else "FAIL")
sys.exit(0 if seen else 1)
