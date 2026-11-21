package com.moyuli.lanbeam;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.moyuli.lanbeam.core.Core;
import com.moyuli.lanbeam.core.Human;
import com.moyuli.lanbeam.ui.Theme;
import com.moyuli.lanbeam.ui.Toggle;
import com.moyuli.lanbeam.ui.Ui;

/** 设置页：自动接收 / 保存位置 / 本机信息 / 隐私 / 界面样式 / 日志 / 关于。 */
public class SettingsActivity extends Activity {
    private App app;
    private Core core;
    private boolean dark;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        app = (App) getApplication();
        core = app.core();
        dark = Theme.dark(this);
        Theme.applyWindow(this, dark);
        setContentView(build());
    }

    private View build() {
        LinearLayout root = Ui.column(this);
        root.setBackgroundColor(Theme.bg(dark));

        LinearLayout head = Ui.row(this);
        TextView back = Ui.pill(this, "返回", dark, false);
        back.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                finish();
            }
        });
        head.addView(back);
        TextView title = Ui.bold(this, "设置", 20, Theme.fg(dark));
        title.setGravity(Gravity.CENTER);
        head.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        head.addView(new View(this), new LinearLayout.LayoutParams(Ui.dp(this, 52), 1));
        root.addView(head);

        ScrollView scroll = Ui.scroll(this);
        LinearLayout col = Ui.column(this);
        scroll.addView(col);
        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        // 自动接收
        LinearLayout auto = Ui.card(this, dark);
        LinearLayout autoRow = Ui.row(this);
        LinearLayout autoCol = Ui.column(this);
        autoCol.addView(Ui.bold(this, "自动接收", 15, Theme.fg(dark)));
        final TextView autoSub = Ui.text(this, core.autoAccept() ? "开启：收到请求直接保存" : "关闭：收到请求先弹窗确认", 11, Theme.muted(dark));
        Ui.margin(autoSub, 0, 3, 0, 0);
        autoCol.addView(autoSub);
        autoRow.addView(autoCol, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        final Toggle t = new Toggle(this);
        t.setDark(dark);
        t.setChecked(core.autoAccept(), false);
        t.setOnChange(new Toggle.OnChange() {
            @Override
            public void onChanged(boolean checked) {
                core.setAutoAccept(checked);
                autoSub.setText(checked ? "开启：收到请求直接保存" : "关闭：收到请求先弹窗确认");
            }
        });
        autoRow.addView(t);
        auto.addView(autoRow);
        addCard(col, auto);

        // 保存位置
        LinearLayout save = Ui.card(this, dark);
        save.addView(Ui.bold(this, "保存位置", 15, Theme.fg(dark)));
        TextView path = Ui.text(this, core.inbox.getAbsolutePath(), 11, Theme.muted(dark));
        LinearLayout.LayoutParams pathLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        pathLp.topMargin = Ui.dp(this, 4);
        pathLp.bottomMargin = Ui.dp(this, 10);
        save.addView(path, pathLp);
        LinearLayout btns = Ui.row(this);
        TextView open = Ui.pill(this, "打开收件箱", dark, false);
        open.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startActivity(new Intent(SettingsActivity.this, InboxActivity.class));
            }
        });
        TextView export = Ui.pill(this, "全部导出到「下载」", dark, false);
        export.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                exportAll();
            }
        });
        btns.addView(open);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        blp.leftMargin = Ui.dp(this, 8);
        btns.addView(export, blp);
        save.addView(btns);
        addCard(col, save);

        // 本机信息
        LinearLayout me = Ui.card(this, dark);
        me.addView(Ui.bold(this, "本机", 15, Theme.fg(dark)));
        me.addView(kv("设备名称", core.deviceName));
        me.addView(kv("地址", com.moyuli.lanbeam.core.Net.localIpv4() + ":" + core.port() + " · 发现端口 " + core.discoveryPort()));
        me.addView(kv("令牌", core.token + "（每次启动随机生成）"));
        addCard(col, me);

        // 后台保活
        LinearLayout keep = Ui.card(this, dark);
        keep.addView(Ui.bold(this, "后台保活", 15, Theme.fg(dark)));
        TextView keepText = Ui.text(this, "ColorOS 会在大约 2 分钟后冻结后台应用，这时收不到电脑发来的文件。"
                + "到系统设置 → 电池 → 应用耗电管理里把 LanBeam 设为「允许后台运行 / 不限制」最稳；"
                + "应用打开时不受影响。", 11, Theme.muted(dark));
        LinearLayout.LayoutParams keepLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        keepLp.topMargin = Ui.dp(this, 6);
        keepLp.bottomMargin = Ui.dp(this, 10);
        keep.addView(keepText, keepLp);
        TextView keepBtn = Ui.pill(this, "打开系统设置", dark, false);
        keepBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                try {
                    startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            Uri.parse("package:" + getPackageName())));
                } catch (Exception e) {
                    Ui.toast(SettingsActivity.this, "打不开系统设置");
                }
            }
        });
        keep.addView(keepBtn);
        addCard(col, keep);

        // 界面样式
        LinearLayout theme = Ui.card(this, dark);
        theme.addView(Ui.bold(this, "界面样式", 15, Theme.fg(dark)));
        int sys = getResources().getConfiguration().uiMode & android.content.res.Configuration.UI_MODE_NIGHT_MASK;
        TextView cur = Ui.text(this, "当前系统：" + (sys == android.content.res.Configuration.UI_MODE_NIGHT_YES ? "深色" : "浅色"), 11, Theme.muted(dark));
        Ui.margin(cur, 0, 3, 0, 10);
        theme.addView(cur);
        LinearLayout chips = Ui.row(this);
        String[] names = {"浅色", "深色", "跟随系统"};
        String[] values = {"light", "dark", "system"};
        String mode = Theme.mode(this);
        for (int i = 0; i < names.length; i++) {
            final String value = values[i];
            boolean on = value.equals(mode);
            TextView chip = Ui.bold(this, names[i], 12, on ? 0xFFFFFFFF : Theme.ACCENT);
            chip.setPadding(Ui.dp(this, 14), Ui.dp(this, 7), Ui.dp(this, 14), Ui.dp(this, 7));
            chip.setBackground(Ui.round(on ? Theme.ACCENT : Theme.soft(dark), Ui.dp(this, 16)));
            chip.setClickable(true);
            chip.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    Theme.prefs(SettingsActivity.this).edit().putString("theme_mode", value).apply();
                    recreate();
                }
            });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            if (i > 0) lp.leftMargin = Ui.dp(this, 8);
            chips.addView(chip, lp);
        }
        theme.addView(chips);
        addCard(col, theme);

        // 日志
        LinearLayout logs = Ui.card(this, dark);
        logs.addView(Ui.bold(this, "日志", 15, Theme.fg(dark)));
        TextView sum = Ui.text(this, "设备 " + core.peers().size() + " 台 · 接收端口 " + core.port() + " · 令牌 " + core.token, 11, Theme.muted(dark));
        Ui.margin(sum, 0, 4, 0, 8);
        logs.addView(sum);
        LinearLayout lrow = Ui.row(this);
        lrow.setClickable(true);
        lrow.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startActivity(new Intent(SettingsActivity.this, LogsActivity.class));
            }
        });
        lrow.addView(Ui.text(this, "查看全部日志", 12, Theme.ACCENT),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        lrow.addView(Ui.text(this, "›", 14, Theme.ACCENT));
        logs.addView(lrow);
        java.util.List<String> lines = core.logs();
        for (int i = 0; i < Math.min(3, lines.size()); i++) {
            TextView l = Ui.text(this, lines.get(i), 10, Theme.muted(dark));
            Ui.margin(l, 0, 4, 0, 0);
            logs.addView(l);
        }
        addCard(col, logs);

        // 关于
        LinearLayout about = Ui.card(this, dark);
        about.addView(Ui.bold(this, "关于", 15, Theme.fg(dark)));
        about.addView(kv("版本", "LanBeam " + Texts.VERSION + " · 安卓端"));
        about.addView(kv("协议", "局域网文件互传 · 协议 v2 · com.moyuli.lanbeam"));
        about.addView(kv("隐私", "不收集个人信息 · 文件只在两台设备间直传"));
        LinearLayout site = Ui.row(this);
        site.setClickable(true);
        site.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Texts.PROJECT_URL)));
                } catch (Exception e) {
                    Ui.toast(SettingsActivity.this, "没有浏览器");
                }
            }
        });
        site.addView(Ui.text(this, "项目主页", 13, Theme.fg(dark)),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        site.addView(Ui.text(this, "在浏览器打开 ›", 12, Theme.ACCENT));
        Ui.margin(site, 0, 10, 0, 0);
        about.addView(site);
        addCard(col, about);

        View bottom = new View(this);
        col.addView(bottom, new LinearLayout.LayoutParams(1, Ui.dp(this, 24)));

        Ui.applyInsets(root, 16, 8, 8);
        return root;
    }

    private TextView kv(String key, String value) {
        TextView v = Ui.text(this, key + "：" + value, 11, Theme.muted(dark));
        Ui.margin(v, 0, 6, 0, 0);
        return v;
    }

    private void addCard(LinearLayout col, LinearLayout card) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = Ui.dp(this, 12);
        col.addView(card, lp);
    }

    private void exportAll() {
        Ui.toast(this, "正在导出…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                int n = 0;
                try {
                    java.io.File[] kids = core.inbox.listFiles();
                    if (kids != null) for (java.io.File f : kids) n += Exports.export(SettingsActivity.this, f);
                } catch (Exception e) {
                    final String msg = e.getMessage();
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Ui.toast(SettingsActivity.this, "导出失败：" + msg);
                        }
                    });
                    return;
                }
                final int count = n;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        Ui.toast(SettingsActivity.this, "已导出 " + count + " 个文件到 下载/LanBeam");
                    }
                });
            }
        }, "lanbeam-export").start();
    }
}
