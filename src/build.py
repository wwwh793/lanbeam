# -*- coding: utf-8 -*-
"""一键打包：python build.py [stable|beta]

约定（见 version.py）：正式版 vX.Y.Z，beta vX.Y.(Z+1)-beta。
做四件事：切 ui_style.STYLE → 按 version.py 生成 version_info.txt →
PyInstaller 打包 → 拷到 成品/ 并打 zip（exe + 防火墙脚本 + 使用说明）。
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "成品"
PY = sys.executable

FIREWALL_BAT = "放行防火墙（管理员运行）.bat"
README_TXT = "使用说明.txt"


def set_style(style: str) -> None:
    path = HERE / "ui_style.py"
    text = path.read_text("utf-8")
    new, n = re.subn(r'^STYLE = "[^"]*"$', f'STYLE = "{style}"', text, flags=re.M)
    if n != 1:
        raise SystemExit("ui_style.py 里没找到唯一的 STYLE 行")
    path.write_text(new, "utf-8")


def load_version():
    for mod in ("version", "ui_style"):
        sys.modules.pop(mod, None)
    import version  # noqa: WPS433
    return version


def write_version_info(v) -> None:
    nums = ", ".join(str(n) for n in v.FILE_VERSION)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({nums}),
    prodvers=({nums}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', 'LanBeam'),
         StringStruct('FileDescription', 'LanBeam 局域网文件互传'),
         StringStruct('FileVersion', '{v.FILE_VERSION_STR}'),
         StringStruct('InternalName', 'LanBeam'),
         StringStruct('OriginalFilename', 'LanBeam.exe'),
         StringStruct('ProductName', 'LanBeam'),
         StringStruct('ProductVersion', '{v.FILE_VERSION_STR}')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    (HERE / "version_info.txt").write_text(text, "utf-8")


def replace_file(src: Path, dst: Path):
    """覆盖运行中的 exe：Windows 允许给正在跑的文件改名，改完再放新的。

    返回 (是否成功, 说明, 是否发现旧版正在运行)。
    """
    try:
        shutil.copy2(src, dst)
        return True, "已覆盖", False
    except PermissionError:
        pass
    old = dst.with_name(dst.name + ".old")
    try:
        if old.exists():
            old.unlink()
        dst.rename(old)
        shutil.copy2(src, dst)
        try:
            old.unlink()
        except OSError:
            pass
        return True, f"旧文件正在运行，先改名成 {old.name} 再放新的", True
    except Exception as exc:  # noqa: BLE001
        return False, f"覆盖失败：{exc}", False


def restart_app(exe: Path) -> bool:
    """杀掉正在跑的旧版，换成新的。她定的流程：打包完直接换，不用手动退托盘。"""
    for name in ("LanBeam.exe", "LanBeam-beta.exe"):
        subprocess.run(["taskkill", "/F", "/T", "/IM", name],
                       capture_output=True)
    time.sleep(0.8)
    try:
        subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[build] 启动失败：{exc}", flush=True)
        return False


def package(v) -> Path:
    exe = HERE / "dist" / "LanBeam.exe"
    if not exe.exists():
        raise SystemExit("打包失败：dist/LanBeam.exe 不存在")
    name = "LanBeam-beta.exe" if v.IS_BETA else "LanBeam.exe"
    target = OUT / name
    OUT.mkdir(parents=True, exist_ok=True)
    ok, msg, was_running = replace_file(exe, target)
    print(f"[build] {msg}", flush=True)
    if not ok:
        raise SystemExit("打包产物没放到 成品/：见上面一行")
    zip_path = OUT / f"LanBeam-{v.VERSION}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(target, name)
        for extra in (FIREWALL_BAT, README_TXT):
            src = OUT / extra
            if src.exists():
                z.write(src, extra)
    return target, zip_path, was_running


def _version_key(path: Path):
    """把 LanBeam-1.7.0.zip / LanBeam-1.7.1-beta.zip 变成长度可比的元组。"""
    name = path.stem
    if name.startswith("LanBeam-"):
        name = name[len("LanBeam-"):]
    is_beta = name.endswith("-beta")
    if is_beta:
        name = name[:-len("-beta")]
    parts = []
    for seg in name.split("."):
        parts.append(int(seg) if seg.isdigit() else 0)
    return tuple(parts), is_beta


def tidy_output(keep_stable: int = 2, keep_beta: int = 1) -> list:
    """成品目录只留有限几个包：正式版留最新的两个（当前 + 上一个防炸），
    beta 只留最新一个；顺带清掉已经没人占用的 LanBeam.exe.old。"""
    removed = []
    items = []
    for p in OUT.glob("LanBeam-*.zip"):
        try:
            items.append((_version_key(p), p))
        except Exception:
            continue
    for is_beta, keep in ((False, keep_stable), (True, keep_beta)):
        group = sorted([p for (k, b), p in items if b == is_beta],
                       key=lambda x: _version_key(x)[0], reverse=True)
        for p in group[keep:]:
            try:
                p.unlink()
                removed.append(p.name)
            except OSError:
                pass
    for old in (OUT / "LanBeam.exe.old", OUT / "LanBeam-beta.exe.old"):
        if old.exists():
            try:
                old.unlink()
                removed.append(old.name)
            except OSError:
                pass
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("style", nargs="?", default="stable", choices=("stable", "beta"))
    ap.add_argument("--keep-style", action="store_true",
                    help="打包完不把 ui_style 恢复成 stable")
    ap.add_argument("--no-restart", action="store_true",
                    help="旧版在跑也不自动换；默认是杀旧进程、开新版")
    args = ap.parse_args()

    set_style(args.style)
    v = load_version()
    write_version_info(v)
    print(f"[build] style={args.style} version={v.VERSION} "
          f"file={v.FILE_VERSION_STR}", flush=True)

    subprocess.run([PY, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "LanBeam.spec"], cwd=str(HERE), check=True)
    target, zip_path, was_running = package(v)
    size = target.stat().st_size / 1024 / 1024
    print(f"[build] exe  {target}  {size:.1f} MB", flush=True)
    print(f"[build] zip  {zip_path}", flush=True)
    for name in tidy_output():
        print(f"[build] 清理旧包 {name}", flush=True)

    if not args.keep_style:
        set_style("stable")
        print("[build] ui_style 已恢复 stable", flush=True)

    # 旧版还在托盘里跑：直接杀掉换新的（2026-11-15 她定的流程）
    if was_running and not args.no_restart:
        if restart_app(target):
            print(f"[build] 已把 {target.name} 拉起来", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
