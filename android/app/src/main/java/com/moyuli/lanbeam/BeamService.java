package com.moyuli.lanbeam;

import android.app.Notification;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/** 前台服务：让接收服务和设备发现在退到后台后还活着（通知栏常驻一条状态）。 */
public class BeamService extends Service {
    private static final int ID = 1001;

    @Override
    public void onCreate() {
        super.onCreate();
        App app = (App) getApplication();
        app.acquireMulticast();
        app.core().start();
        startForegroundCompat(app);
    }

    private void startForegroundCompat(App app) {
        Notification n = app.builder(App.CH_STATUS)
                .setSmallIcon(R.drawable.ic_stat_lanbeam)
                .setContentTitle("LanBeam 正在接收")
                .setContentText("端口 " + app.core().port() + " · 令牌 " + app.core().token)
                .setOngoing(true)
                .setContentIntent(app.openIntent())
                .build();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(ID, n);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        try {
            ((App) getApplication()).core().stop();
            ((App) getApplication()).releaseMulticast();
        } catch (Exception ignored) {
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
