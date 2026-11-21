package com.moyuli.lanbeam;

import android.app.Application;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import com.moyuli.lanbeam.core.Core;
import com.moyuli.lanbeam.core.Types;

import java.io.File;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** 应用级单例：持有内核、通知通道、当前界面与「等用户点接收」的闸门。 */
public class App extends Application implements Core.Host {

    public static final String CH_STATUS = "lanbeam_status";
    public static final String CH_ALERT = "lanbeam_alert";

    private Core core;
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile MainActivity ui;
    private WifiManager.MulticastLock multicastLock;

    private final Object offerLock = new Object();
    private Types.OfferInfo pendingInfo;
    private CountDownLatch pendingLatch;
    private boolean pendingResult;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannels();
        File base = getExternalFilesDir(null);
        if (base == null) base = getFilesDir();
        final SharedPreferences sp = getSharedPreferences("lanbeam", MODE_PRIVATE);
        // 平时用显示真实设备名（和 Windows 端用电脑名一致）；演示截图由发布流程打码
        String model = Build.MODEL == null ? "" : Build.MODEL.trim();
        core = new Core(base, model.isEmpty() ? "Android 手机" : model, new Core.Prefs() {
            @Override
            public String get(String key, String def) {
                return sp.getString(key, def);
            }

            @Override
            public void set(String key, String value) {
                sp.edit().putString(key, value).apply();
            }
        }, this);
    }

    public Core core() {
        return core;
    }

    public void attach(MainActivity a) {
        ui = a;
    }

    public void detach(MainActivity a) {
        if (ui == a) ui = null;
    }

    public void startBeam() {
        Intent i = new Intent(this, BeamService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i);
        else startService(i);
    }

    public synchronized void acquireMulticast() {
        if (multicastLock != null) return;
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm == null) return;
            multicastLock = wm.createMulticastLock("lanbeam");
            multicastLock.setReferenceCounted(false);
            multicastLock.acquire();
        } catch (Exception ignored) {
        }
    }

    public synchronized void releaseMulticast() {
        try {
            if (multicastLock != null && multicastLock.isHeld()) multicastLock.release();
        } catch (Exception ignored) {
        }
        multicastLock = null;
    }

    private void createChannels() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel status = new NotificationChannel(CH_STATUS, "接收服务", NotificationManager.IMPORTANCE_LOW);
        status.setDescription("传输期间保持接收在线");
        status.setShowBadge(false);
        nm.createNotificationChannel(status);
        NotificationChannel alert = new NotificationChannel(CH_ALERT, "发送请求", NotificationManager.IMPORTANCE_HIGH);
        alert.setDescription("有设备想给你发送文件");
        nm.createNotificationChannel(alert);
    }

    public Notification.Builder builder(String channel) {
        if (Build.VERSION.SDK_INT >= 26) return new Notification.Builder(this, channel);
        return new Notification.Builder(this);
    }

    public PendingIntent openIntent() {
        Intent i = new Intent(this, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getActivity(this, 1, i, flags);
    }

    public void notifyOffer(Types.OfferInfo info) {
        try {
            Notification n = builder(CH_ALERT)
                    .setSmallIcon(R.drawable.ic_stat_lanbeam)
                    .setContentTitle("有设备想发送文件")
                    .setContentText(info.sender + " · " + info.files + " 个文件 · 打开 LanBeam 处理")
                    .setContentIntent(openIntent())
                    .setAutoCancel(true)
                    .build();
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (nm != null) nm.notify(1002, n);
        } catch (Exception ignored) {
        }
    }

    // ------------------------------------------------------------ Core.Host

    @Override
    public boolean askOffer(Types.OfferInfo info) {
        if (core.autoAccept()) return true;
        CountDownLatch latch = new CountDownLatch(1);
        synchronized (offerLock) {
            pendingInfo = info;
            pendingLatch = latch;
            pendingResult = false;
        }
        main.post(new Runnable() {
            @Override
            public void run() {
                MainActivity a = ui;
                if (a != null && !a.isFinishing()) a.presentOffer();
                else notifyOffer(info);
            }
        });
        try {
            latch.await(120, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }
        boolean r;
        synchronized (offerLock) {
            r = pendingResult;
            pendingInfo = null;
            pendingLatch = null;
        }
        return r;
    }

    public Types.OfferInfo pendingOffer() {
        synchronized (offerLock) {
            return pendingInfo;
        }
    }

    public void answerOffer(boolean accept) {
        synchronized (offerLock) {
            pendingResult = accept;
            if (pendingLatch != null) pendingLatch.countDown();
        }
    }

    @Override
    public void onLog(final String msg) {
        main.post(new Runnable() {
            @Override
            public void run() {
                MainActivity a = ui;
                if (a != null) a.onLogLine();
            }
        });
    }

    @Override
    public void onPeersChanged() {
        main.post(new Runnable() {
            @Override
            public void run() {
                MainActivity a = ui;
                if (a != null) a.refreshPeers();
            }
        });
    }

    @Override
    public void onProgress(final String name, final long sent, final long total, final boolean receiving) {
        main.post(new Runnable() {
            @Override
            public void run() {
                MainActivity a = ui;
                if (a != null) a.showProgress(name, sent, total, receiving);
            }
        });
    }

    @Override
    public void onTransferEnd(final String summary) {
        main.post(new Runnable() {
            @Override
            public void run() {
                MainActivity a = ui;
                if (a != null) {
                    a.transferFinished(summary);
                    if (!summary.startsWith("已发送")) {
                        android.widget.Toast.makeText(getApplicationContext(), summary,
                                android.widget.Toast.LENGTH_LONG).show();
                    }
                }
            }
        });
    }

    @Override
    public void onSaved(final File file, final String rel) {
        main.post(new Runnable() {
            @Override
            public void run() {
                MainActivity a = ui;
                if (a != null) {
                    a.saved(rel, file);
                } else {
                    android.widget.Toast.makeText(getApplicationContext(), "已收到 " + rel,
                            android.widget.Toast.LENGTH_SHORT).show();
                }
            }
        });
    }
}
