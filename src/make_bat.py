# -*- coding: utf-8 -*-
from pathlib import Path
bat = r"""@echo off
chcp 936 >nul
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [!] 需要管理员权限：请右键本文件，选择"以管理员身份运行"。
  pause
  exit /b 1
)
echo 正在为 LanBeam 放行 Windows 防火墙（专用/公用/域 三种网络）...
netsh advfirewall firewall delete rule name="LanBeam Program" >nul 2>&1
netsh advfirewall firewall delete rule name="LanBeam Discovery" >nul 2>&1
netsh advfirewall firewall delete rule name="LanBeam TCP" >nul 2>&1
netsh advfirewall firewall add rule name="LanBeam Program" dir=in action=allow program="%~dp0LanBeam.exe" enable=yes profile=any
netsh advfirewall firewall add rule name="LanBeam TCP" dir=in action=allow protocol=TCP localport=47821 enable=yes profile=any
netsh advfirewall firewall add rule name="LanBeam Discovery" dir=in action=allow protocol=UDP localport=47820 enable=yes profile=any
echo.
echo 完成。如果对方还是"能发不能收"，在对方电脑上也运行一遍这个文件。
echo 注意：运行前请先关掉 LanBeam，运行后再打开。
pause
"""
p = Path(__file__).resolve().parent.parent / "成品" / "放行防火墙（管理员运行）.bat"
p.write_bytes(bat.replace("\n", "\r\n").encode("gbk"))
print("bat ok", p.stat().st_size)
