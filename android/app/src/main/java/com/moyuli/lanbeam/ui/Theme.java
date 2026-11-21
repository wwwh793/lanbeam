package com.moyuli.lanbeam.ui;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Build;
import android.view.View;
import android.view.Window;

/** 配色与主题：数值照抄鸿蒙端 1.3.4（#0A84FF 主色、#1C1C1E 卡片、纯黑底）。 */
public final class Theme {
    private Theme() {
    }

    public static final int ACCENT = 0xFF0A84FF;

    public static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("lanbeam", Context.MODE_PRIVATE);
    }

    public static String mode(Context c) {
        return prefs(c).getString("theme_mode", "system");
    }

    public static boolean dark(Context c) {
        String m = mode(c);
        if ("dark".equals(m)) return true;
        if ("light".equals(m)) return false;
        int flags = c.getResources().getConfiguration().uiMode & android.content.res.Configuration.UI_MODE_NIGHT_MASK;
        return flags == android.content.res.Configuration.UI_MODE_NIGHT_YES;
    }

    public static int bg(boolean dark) {
        return dark ? 0xFF000000 : 0xFFF2F2F7;
    }

    public static int card(boolean dark) {
        return dark ? 0xFF1C1C1E : 0xFFFFFFFF;
    }

    public static int fg(boolean dark) {
        return dark ? 0xFFFFFFFF : 0xFF1C1C1E;
    }

    public static int muted(boolean dark) {
        return dark ? 0xFF8E8E93 : 0xFF6C6C70;
    }

    public static int soft(boolean dark) {
        return dark ? 0xFF10233B : 0xFFE8F0FF;
    }

    public static int line(boolean dark) {
        return dark ? 0xFF2C2C2E : 0xFFE5E5EA;
    }

    /** 状态栏/导航栏跟着主题走；Android 15 强制全面屏，内容靠 insets 让位。 */
    public static void applyWindow(Activity a, boolean dark) {
        Window w = a.getWindow();
        w.setStatusBarColor(Color.TRANSPARENT);
        w.setNavigationBarColor(dark ? Color.TRANSPARENT : 0xCCF2F2F7);
        View decor = w.getDecorView();
        if (Build.VERSION.SDK_INT >= 30) {
            // Android 15 强制 edge-to-edge 后，老 flag 经常不生效，改走 WindowInsetsController
            android.view.WindowInsetsController c = w.getInsetsController();
            if (c != null) {
                int mask = android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(dark ? 0 : mask, mask);
            }
        }
        int flags = decor.getSystemUiVisibility();
        if (dark) {
            flags &= ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        } else {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
            if (Build.VERSION.SDK_INT >= 26) flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        decor.setSystemUiVisibility(flags);
        if (Build.VERSION.SDK_INT >= 30) {
            w.setNavigationBarContrastEnforced(false);
        }
    }
}
