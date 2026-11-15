# -*- coding: utf-8 -*-
"""界面截图自检：python shot.py

在真实 Tk 里把主界面/设置页按深色、浅色各拍一张，再拍进度条的
"传输中" 和 "准备中" 两个状态，输出到 素材/v<版本>-*.png。
改完界面跑一遍，肉眼过一下圆角、对齐、配色。
"""

import ctypes
import queue
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHOT_DIR = ROOT / "素材"
sys.path.insert(0, str(HERE))

import lanbeam_core as lc  # noqa: E402
import lanbeam_ui as ui  # noqa: E402
from PIL import ImageGrab  # noqa: E402

TAG = "v" + ui.VERSION.split("-")[0].replace(".", "")


def main() -> int:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    u = ctypes.windll.user32

    cfg = lc.load_config()
    cfg["theme"] = "dark"
    core = lc.Core(cfg, queue.Queue())
    core.start()
    app = ui.App(core)

    def pump(sec: float) -> None:
        end = time.time() + sec
        while time.time() < end:
            app.update()
            app._poll()
            time.sleep(0.02)

    def shot(name: str) -> None:
        pump(0.8)
        hwnd = u.GetParent(app.winfo_id())
        rect = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        img = ImageGrab.grab(
            bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
        path = SHOT_DIR / f"{TAG}-{name}.png"
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        img.save(str(path))
        print("shot", path.name, img.size, flush=True)

    try:
        pump(2.0)
        shot("main-dark")

        app.open_settings()
        shot("settings-dark")

        app.close_settings()
        app.set_theme("light")
        shot("main-light")

        app.open_settings()
        shot("settings-light")

        app.close_settings()
        app.set_theme("dark")
        pump(0.4)
        app.prog.set(0.42)
        app.title_lbl.configure(text="发送 我的照片")
        app.detail_lbl.configure(text="12.4 MB / 29.5 MB · 38.2 MB/s")
        app.percent_lbl.configure(text="42%")
        shot("progress")

        # 右键菜单/命令行递进来的待发送
        app.prog.set(0.0)
        app.prog.busy(False)
        app.title_lbl.configure(text="空闲")
        app.detail_lbl.configure(text="等待发送或接收")
        app.percent_lbl.configure(text="")
        app.pending = [HERE / "lanbeam.py", HERE / "lanbeam_ui.py"]
        app._update_pending_ui()
        app._refresh_target_label()
        shot("pending")
        app.pending = []
        app._update_pending_ui()
        app._refresh_target_label()

        app.prog.busy(True)
        app.title_lbl.configure(text="准备发送…")
        app.detail_lbl.configure(text="正在和对方握手")
        app.percent_lbl.configure(text="0%")
        shot("busy")
    finally:
        app.destroy()
        core.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
