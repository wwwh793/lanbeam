package com.moyuli.lanbeam;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.moyuli.lanbeam.ui.Theme;
import com.moyuli.lanbeam.ui.Ui;

import java.util.List;

/** 全部日志（最新的在上面），可一键复制发给开发者排障。 */
public class LogsActivity extends Activity {
    private boolean dark;
    private App app;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        app = (App) getApplication();
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
        TextView title = Ui.bold(this, "日志", 20, Theme.fg(dark));
        title.setGravity(Gravity.CENTER);
        head.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        TextView copy = Ui.pill(this, "复制", dark, false);
        copy.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                StringBuilder sb = new StringBuilder();
                for (String line : app.core().logs()) sb.append(line).append('\n');
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("LanBeam 日志", sb.toString()));
                Ui.toast(LogsActivity.this, "已复制全部日志");
            }
        });
        head.addView(copy);
        root.addView(head);

        ScrollView scroll = Ui.scroll(this);
        LinearLayout col = Ui.card(this, dark);
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        clp.topMargin = Ui.dp(this, 14);
        col.setLayoutParams(clp);
        List<String> lines = app.core().logs();
        if (lines.isEmpty()) {
            col.addView(Ui.text(this, "暂无日志", 12, Theme.muted(dark)));
        } else {
            for (String line : lines) {
                TextView t = Ui.text(this, line, 10, Theme.muted(dark));
                t.setTypeface(android.graphics.Typeface.MONOSPACE);
                Ui.margin(t, 0, 3, 0, 3);
                col.addView(t);
            }
        }
        scroll.addView(col);
        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        Ui.applyInsets(root, 16, 8, 8);
        return root;
    }
}
