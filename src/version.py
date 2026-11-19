# -*- coding: utf-8 -*-
"""版本号唯一来源。

规则（2026-11-15 定，长期有效）：
  正式版 = BASE                      例如 1.6.4
  beta 版 = BASE 的补丁号 +1 + "-beta"  例如 1.6.5-beta
也就是说 beta 永远比正式版领先一个 0.0.x，看号就知道谁在前。

改版本只改下面的 BASE 一处；version_info.txt 由 build.py 依据这里生成。
"""

from ui_style import STYLE as _STYLE


BASE = (1, 7, 2)


def _fmt(parts) -> str:
    return ".".join(str(int(p)) for p in parts)


IS_BETA = _STYLE == "beta"

STABLE_VERSION = _fmt(BASE)
BETA_VERSION = _fmt((BASE[0], BASE[1], BASE[2] + 1)) + "-beta"

if IS_BETA:
    VERSION = BETA_VERSION
    CURRENT = (BASE[0], BASE[1], BASE[2] + 1)
else:
    VERSION = STABLE_VERSION
    CURRENT = BASE

FILE_VERSION = tuple(CURRENT) + (0,)
FILE_VERSION_STR = ".".join(str(n) for n in FILE_VERSION)
