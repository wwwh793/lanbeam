package com.moyuli.lanbeam;

import android.app.Activity;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.moyuli.lanbeam.core.Human;
import com.moyuli.lanbeam.ui.Theme;
import com.moyuli.lanbeam.ui.Ui;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;

/** 收件箱：收到的文件都在这里，可打开、导出、删除（对齐鸿蒙 1.3.4 的手机端做法）。 */
public class InboxActivity extends Activity {
    private App app;
    private boolean dark;
    private LinearLayout list;
    private TextView empty;
    private TextView count;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        app = (App) getApplication();
        dark = Theme.dark(this);
        Theme.applyWindow(this, dark);
        setContentView(build());
        refresh();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
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
        LinearLayout mid = Ui.column(this);
        TextView title = Ui.bold(this, "收件箱", 20, Theme.fg(dark));
        title.setGravity(Gravity.CENTER);
        mid.addView(title);
        count = Ui.text(this, "", 11, Theme.muted(dark));
        count.setGravity(Gravity.CENTER);
        mid.addView(count);
        head.addView(mid, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        TextView export = Ui.pill(this, "全部导出", dark, false);
        export.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                exportAll();
            }
        });
        head.addView(export);
        root.addView(head);

        ScrollView scroll = Ui.scroll(this);
        list = Ui.column(this);
        scroll.addView(list);
        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        empty = Ui.text(this, "还没有收到文件\n另一台设备选「发送文件」，选到你就会出现在这里", 12, Theme.muted(dark));
        empty.setGravity(Gravity.CENTER);
        empty.setPadding(0, Ui.dp(this, 60), 0, 0);

        Ui.applyInsets(root, 16, 8, 8);
        return root;
    }

    private void refresh() {
        File inbox = app.core().inbox;
        File[] kids = inbox.listFiles();
        List<File> files = new ArrayList<File>();
        if (kids != null) files.addAll(Arrays.asList(kids));
        final List<File> listFiles = files;
        java.util.Collections.sort(listFiles, new Comparator<File>() {
            @Override
            public int compare(File a, File b) {
                return Long.compare(b.lastModified(), a.lastModified());
            }
        });
        list.removeAllViews();
        count.setText(listFiles.size() + " 项 · " + Human.size(dirSize(listFiles)));
        if (listFiles.isEmpty()) list.addView(empty);
        for (final File f : listFiles) {
            LinearLayout row = Ui.row(this);
            row.setBackground(Ui.round(Theme.card(dark), Ui.dp(this, 14)));
            row.setPadding(Ui.dp(this, 16), Ui.dp(this, 12), Ui.dp(this, 16), Ui.dp(this, 12));
            row.setClickable(true);
            row.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    Files.open(InboxActivity.this, app.core().inbox, f);
                }
            });
            row.setOnLongClickListener(new View.OnLongClickListener() {
                @Override
                public boolean onLongClick(View v) {
                    confirmDelete(f);
                    return true;
                }
            });
            LinearLayout col = Ui.column(this);
            TextView name = Ui.bold(this, f.isDirectory() ? "📁 " + f.getName() : f.getName(), 14, Theme.fg(dark));
            name.setSingleLine(true);
            name.setEllipsize(TextUtils.TruncateAt.MIDDLE);
            col.addView(name);
            String sub = f.isDirectory() ? "文件夹 · " + Human.size(dirSize(Arrays.asList(f)))
                    : Human.size(f.length()) + " · " + Human.time(f.lastModified());
            TextView st = Ui.text(this, sub, 11, Theme.muted(dark));
            Ui.margin(st, 0, 3, 0, 0);
            col.addView(st);
            row.addView(col, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            TextView ex = Ui.text(this, "导出", 12, Theme.ACCENT);
            ex.setPadding(Ui.dp(this, 8), Ui.dp(this, 6), 0, Ui.dp(this, 6));
            ex.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    exportOne(f);
                }
            });
            row.addView(ex);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.bottomMargin = Ui.dp(this, 8);
            list.addView(row, lp);
        }
    }

    private long dirSize(List<File> files) {
        long n = 0;
        for (File f : files) n += sizeOf(f);
        return n;
    }

    private long sizeOf(File f) {
        if (f.isFile()) return f.length();
        long n = 0;
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) n += sizeOf(k);
        return n;
    }

    private void confirmDelete(final File f) {
        Ui.confirm(this, dark, "删除这个文件？", f.getName() + "\n删除后不可恢复。", "删除", "取消", new Consumer<Boolean>() {
            @Override
            public void accept(Boolean ok) {
                if (ok && deleteRec(f)) {
                    Ui.toast(InboxActivity.this, "已删除");
                    refresh();
                }
            }
        });
    }

    private boolean deleteRec(File f) {
        if (f.isDirectory()) {
            File[] kids = f.listFiles();
            if (kids != null) for (File k : kids) deleteRec(k);
        }
        return f.delete();
    }

    private void exportOne(final File f) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    final int n = Exports.export(InboxActivity.this, f);
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Ui.toast(InboxActivity.this, "已导出 " + n + " 个文件到 下载/LanBeam");
                        }
                    });
                } catch (final Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Ui.toast(InboxActivity.this, "导出失败：" + e.getMessage());
                        }
                    });
                }
            }
        }, "lanbeam-export").start();
    }

    private void exportAll() {
        Ui.toast(this, "正在导出…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    File[] kids = app.core().inbox.listFiles();
                    int n = 0;
                    if (kids != null) for (File f : kids) n += Exports.export(InboxActivity.this, f);
                    final int count = n;
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Ui.toast(InboxActivity.this, "已导出 " + count + " 个文件到 下载/LanBeam");
                        }
                    });
                } catch (final Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Ui.toast(InboxActivity.this, "导出失败：" + e.getMessage());
                        }
                    });
                }
            }
        }, "lanbeam-export").start();
    }
}
