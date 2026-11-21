package com.moyuli.lanbeam;

import android.app.Activity;
import android.app.Dialog;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.moyuli.lanbeam.core.Core;
import com.moyuli.lanbeam.core.Human;
import com.moyuli.lanbeam.core.Sender;
import com.moyuli.lanbeam.core.Types;
import com.moyuli.lanbeam.ui.ProgressView;
import com.moyuli.lanbeam.ui.Theme;
import com.moyuli.lanbeam.ui.Ui;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/** 主界面：附近设备 + 三个发送入口 + 当前传输。布局照鸿蒙端 1.3.4。 */
public class MainActivity extends Activity {

    private static final int REQ_FILES = 101;
    private static final int REQ_FOLDER = 102;
    private static final int REQ_ALBUM = 103;
    private static final int REQ_NOTIF = 104;

    private App app;
    private Core core;
    private boolean dark;
    private final Handler ui = new Handler(Looper.getMainLooper());

    private LinearLayout root;
    private LinearLayout peerList;
    private TextView countText;
    private LinearLayout transferCard;
    private TextView transferTitle;
    private TextView transferSub;
    private TextView cancelBtn;
    private ProgressView progress;

    private String selectedId = "";
    private String lastSig = "";
    private Dialog offerDialog;

    private long lastTick = 0;
    private long lastBytes = 0;
    private long speed = 0;
    private Runnable hideTransfer;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        app = (App) getApplication();
        core = app.core();
        dark = Theme.dark(this);
        Theme.applyWindow(this, dark);
        setContentView(build());
        app.attach(this);
        app.startBeam();
        askNotification();
        ui.post(ticker);
    }

    private Runnable ticker = new Runnable() {
        @Override
        public void run() {
            refreshPeers();
            if (core.port() > 0) {
                // 端口偶尔会因占用变化，通知栏文案以 Settings 为准即可，这里不反复改
            }
            ui.postDelayed(this, 800);
        }
    };

    private View build() {
        root = Ui.column(this);
        root.setBackgroundColor(Theme.bg(dark));

        TextView inbox = Ui.pill(this, "收件箱", dark, false);
        inbox.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startActivity(new Intent(MainActivity.this, InboxActivity.class));
            }
        });
        TextView settings = Ui.pill(this, "设置", dark, false);
        settings.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startActivity(new Intent(MainActivity.this, SettingsActivity.class));
            }
        });
        LinearLayout head = Ui.header(this, dark, "LanBeam", "安卓端 · 局域网互传", inbox, settings);
        root.addView(head);

        LinearLayout section = Ui.row(this);
        TextView label = Ui.bold(this, "附近设备", 16, Theme.fg(dark));
        section.addView(label, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        countText = Ui.text(this, "正在启动…", 12, Theme.muted(dark));
        section.addView(countText);
        Ui.margin(section, 0, 26, 0, 10);
        root.addView(section);

        ScrollView scroll = Ui.scroll(this);
        peerList = Ui.column(this);
        scroll.addView(peerList, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f);
        root.addView(scroll, slp);

        transferCard = Ui.card(this, dark);
        transferCard.setVisibility(View.GONE);
        LinearLayout tHead = Ui.row(this);
        transferTitle = Ui.bold(this, "", 14, Theme.fg(dark));
        transferTitle.setSingleLine(true);
        transferTitle.setEllipsize(TextUtils.TruncateAt.MIDDLE);
        tHead.addView(transferTitle, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        cancelBtn = Ui.text(this, "取消", 12, Theme.ACCENT);
        cancelBtn.setPadding(Ui.dp(this, 8), Ui.dp(this, 4), 0, Ui.dp(this, 4));
        cancelBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (core.isSending()) core.cancelSend();
                Ui.toast(MainActivity.this, "已取消发送");
                hideTransferNow();
            }
        });
        tHead.addView(cancelBtn);
        transferCard.addView(tHead);

        progress = new ProgressView(this);
        LinearLayout.LayoutParams plp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 8));
        plp.topMargin = Ui.dp(this, 10);
        transferCard.addView(progress, plp);

        transferSub = Ui.text(this, "", 11, Theme.muted(dark));
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tlp.topMargin = Ui.dp(this, 8);
        transferCard.addView(transferSub, tlp);

        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        clp.topMargin = Ui.dp(this, 10);
        root.addView(transferCard, clp);

        TextView folderBtn = Ui.button(this, "选择文件夹发送…", false, dark);
        folderBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                pickFolder();
            }
        });
        TextView fileBtn = Ui.button(this, "选择文件发送…", true, dark);
        fileBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                pickFiles();
            }
        });
        TextView albumBtn = Ui.button(this, "从相册发送…", false, dark);
        albumBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                pickAlbum();
            }
        });
        for (TextView btn : new TextView[]{folderBtn, fileBtn, albumBtn}) {
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 48));
            lp.topMargin = Ui.dp(this, 8);
            root.addView(btn, lp);
        }

        TextView hint = Ui.text(this, "收到的文件保存在应用内「收件箱」，可一键导出到「下载/LanBeam」", 10, Theme.muted(dark));
        hint.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams hlp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        hlp.topMargin = Ui.dp(this, 10);
        hlp.bottomMargin = Ui.dp(this, 6);
        root.addView(hint, hlp);

        Ui.applyInsets(root, 16, 8, 8);
        return root;
    }

    // ------------------------------------------------------------ 设备列表

    public void refreshPeers() {
        if (peerList == null) return;
        List<Types.Peer> list = core.peers();
        StringBuilder sig = new StringBuilder();
        for (Types.Peer p : list) sig.append(p.id).append('|').append(p.name).append('|').append(p.label()).append(';');
        sig.append('#').append(selectedId);
        if (sig.toString().equals(lastSig)) return;
        lastSig = sig.toString();

        countText.setText(list.isEmpty() ? "0 台" : list.size() + " 台");
        peerList.removeAllViews();
        if (list.isEmpty()) {
            TextView empty = Ui.text(this, "还没有发现设备\n确认另一台设备已打开 LanBeam，并且连的是同一个 Wi-Fi", 12, Theme.muted(dark));
            empty.setGravity(Gravity.CENTER);
            empty.setPadding(0, Ui.dp(this, 40), 0, 0);
            peerList.addView(empty);
            return;
        }
        if (!selectedId.isEmpty()) {
            boolean found = false;
            for (Types.Peer p : list) if (p.id.equals(selectedId)) found = true;
            if (!found) selectedId = "";
        }
        for (final Types.Peer p : list) {
            boolean sel = p.id.equals(selectedId);
            LinearLayout card = Ui.row(this);
            card.setBackground(sel
                    ? Ui.roundStroke(Theme.soft(dark), Theme.ACCENT, Ui.dp(this, 14), Ui.dp(this, 1.2f))
                    : Ui.round(Theme.card(dark), Ui.dp(this, 14)));
            card.setPadding(Ui.dp(this, 16), Ui.dp(this, 12), Ui.dp(this, 16), Ui.dp(this, 12));
            card.setClickable(true);
            card.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    selectedId = p.id.equals(selectedId) ? "" : p.id;
                    refreshPeersForced();
                }
            });
            LinearLayout col = Ui.column(this);
            col.addView(Ui.bold(this, p.name, 15, Theme.fg(dark)));
            TextView sub = Ui.text(this, p.label(), 11, Theme.muted(dark));
            Ui.margin(sub, 0, 2, 0, 0);
            col.addView(sub);
            card.addView(col, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            TextView state = Ui.text(this, sel ? "已选中" : "", 12, Theme.ACCENT);
            card.addView(state);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.bottomMargin = Ui.dp(this, 8);
            peerList.addView(card, lp);
        }
    }

    private void refreshPeersForced() {
        lastSig = "";
        refreshPeers();
    }

    private Types.Peer selectedPeer() {
        for (Types.Peer p : core.peers()) if (p.id.equals(selectedId)) return p;
        return null;
    }

    private boolean ensurePeer() {
        if (selectedPeer() != null) return true;
        Ui.toast(this, "先在「附近设备」里点一台设备");
        return false;
    }

    // ------------------------------------------------------------ 发文件

    private void pickFiles() {
        if (!ensurePeer()) return;
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        try {
            startActivityForResult(i, REQ_FILES);
        } catch (Exception e) {
            Ui.toast(this, "没有可用的文件选择器");
        }
    }

    private void pickFolder() {
        if (!ensurePeer()) return;
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try {
            startActivityForResult(i, REQ_FOLDER);
        } catch (Exception e) {
            Ui.toast(this, "没有可用的文件夹选择器");
        }
    }

    private void pickAlbum() {
        if (!ensurePeer()) return;
        Intent i;
        if (Build.VERSION.SDK_INT >= 33) {
            i = new Intent(MediaStore.ACTION_PICK_IMAGES);
            i.setType("image/*");
            i.putExtra(MediaStore.EXTRA_PICK_IMAGES_MAX, 20);
        } else {
            i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType("image/*");
            i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        }
        try {
            startActivityForResult(i, REQ_ALBUM);
        } catch (Exception e) {
            Ui.toast(this, "没有可用的相册选择器");
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (res != RESULT_OK || data == null) return;
        if (req == REQ_FOLDER) {
            final Uri tree = data.getData();
            if (tree == null) return;
            try {
                getContentResolver().takePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } catch (Exception ignored) {
            }
            prepareAndSend(new java.util.concurrent.Callable<Sender.Job>() {
                @Override
                public Sender.Job call() throws Exception {
                    return SendPlan.fromTree(MainActivity.this, tree);
                }
            }, "正在整理文件夹…");
            return;
        }
        if (req == REQ_FILES || req == REQ_ALBUM) {
            final List<Uri> uris = new ArrayList<Uri>();
            ClipData cd = data.getClipData();
            if (cd != null) {
                for (int i = 0; i < cd.getItemCount(); i++) {
                    Uri u = cd.getItemAt(i).getUri();
                    if (u != null) uris.add(u);
                }
            } else if (data.getData() != null) {
                uris.add(data.getData());
            }
            if (uris.isEmpty()) return;
            for (Uri u : uris) {
                try {
                    getContentResolver().takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION);
                } catch (Exception ignored) {
                }
            }
            prepareAndSend(new java.util.concurrent.Callable<Sender.Job>() {
                @Override
                public Sender.Job call() throws Exception {
                    return SendPlan.fromUris(MainActivity.this, uris);
                }
            }, "正在读取文件…");
        }
    }

    private void prepareAndSend(final java.util.concurrent.Callable<Sender.Job> builder, final String hint) {
        Ui.toast(this, hint);
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    final Sender.Job job = builder.call();
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            startSend(job);
                        }
                    });
                } catch (final Exception e) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            Ui.toast(MainActivity.this, "准备发送失败：" + (e.getMessage() == null ? e.toString() : e.getMessage()));
                        }
                    });
                }
            }
        }, "lanbeam-prepare").start();
    }

    private void startSend(Sender.Job job) {
        Types.Peer p = selectedPeer();
        if (p == null) {
            Ui.toast(this, "目标设备已经离线了，重新点一台");
            return;
        }
        lastBytes = 0;
        lastTick = System.currentTimeMillis();
        speed = 0;
        transferCard.setVisibility(View.VISIBLE);
        if (hideTransfer != null) ui.removeCallbacks(hideTransfer);
        transferTitle.setText("准备发送 · " + ("folder".equals(job.kind) ? job.root : job.files.size() + " 个文件"));
        transferSub.setText(Human.size(job.total) + " · 等待对方确认");
        progress.setIndeterminate(true);
        cancelBtn.setVisibility(View.VISIBLE);
        core.send(p, job);
    }

    public void showProgress(String name, long sent, long total, boolean receiving) {
        if (transferCard == null) return;
        if (transferCard.getVisibility() != View.VISIBLE) transferCard.setVisibility(View.VISIBLE);
        if (hideTransfer != null) ui.removeCallbacks(hideTransfer);
        long now = System.currentTimeMillis();
        if (lastTick > 0 && now - lastTick > 400) {
            speed = (sent - lastBytes) * 1000 / Math.max(1, now - lastTick);
            lastTick = now;
            lastBytes = sent;
        } else if (lastTick == 0) {
            lastTick = now;
            lastBytes = sent;
        }
        progress.setIndeterminate(false);
        progress.setProgress(total > 0 ? sent / (float) total : 0f);
        transferTitle.setText((receiving ? "正在接收 · " : "正在发送 · ") + name);
        String sub = Human.size(sent) + " / " + Human.size(total);
        if (speed > 0) sub += " · " + Human.size(speed) + "/s";
        transferSub.setText(sub);
    }

    public void transferFinished(String summary) {
        if (transferCard == null) return;
        transferCard.setVisibility(View.VISIBLE);
        progress.setIndeterminate(false);
        progress.setProgress(1f);
        transferTitle.setText(summary.startsWith("已发送") || summary.startsWith("已接收") ? "已完成" : "已结束");
        transferSub.setText(summary);
        cancelBtn.setVisibility(View.GONE);
        hideTransfer = new Runnable() {
            @Override
            public void run() {
                hideTransferNow();
            }
        };
        ui.postDelayed(hideTransfer, 5000);
    }

    private void hideTransferNow() {
        if (transferCard != null) transferCard.setVisibility(View.GONE);
    }

    public void saved(String rel, java.io.File file) {
        Ui.toast(this, "已收到 " + rel);
        // 接收没有单独的"批次结束"事件，收到一个就收掉卡片，5 秒后自动隐藏
        transferFinished("已接收 " + rel);
    }

    public void onLogLine() {
        // 主界面不显示日志，设置页里有
    }

    // ------------------------------------------------------------ 接收确认

    public void presentOffer() {
        Types.OfferInfo info = app.pendingOffer();
        if (info == null || offerDialog != null || isFinishing()) return;
        String msg = "来自 " + info.sender + "\n"
                + ("folder".equals(info.kind) ? "文件夹：" + info.root : "文件") + "\n"
                + info.files + " 个文件 · " + Human.size(info.total) + "\n\n"
                + "文件只保存到本机收件箱，不上传。";
        offerDialog = Ui.confirm(this, dark, "收到发送请求", msg, "接收", "拒收", new Consumer<Boolean>() {
            @Override
            public void accept(Boolean ok) {
                app.answerOffer(ok);
                offerDialog = null;
            }
        });
        ui.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (offerDialog != null) {
                    offerDialog.dismiss();
                    offerDialog = null;
                    app.answerOffer(false);
                }
            }
        }, 115000);
    }

    // ------------------------------------------------------------ 生命周期

    @Override
    protected void onResume() {
        super.onResume();
        boolean d = Theme.dark(this);
        if (d != dark) {
            recreate();
            return;
        }
        app.attach(this);
        core.setBackground(false);
        if (!core.isRunning()) app.startBeam();
        refreshPeersForced();
        presentOffer();
        if (core.discoveryAgeMs() > 30000) core.restartDiscovery();
    }

    @Override
    protected void onPause() {
        super.onPause();
        core.setBackground(true);
        app.detach(this);
    }

    @Override
    protected void onDestroy() {
        ui.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private void askNotification() {
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, REQ_NOTIF);
            }
        }
    }
}
