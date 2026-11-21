package com.moyuli.lanbeam.core;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** 内核：把发现、接收服务、发送串起来；不依赖任何安卓 API，桌面也能跑。 */
public final class Core implements Discovery.Sink, BeamServer.Listener {

    public interface Host {
        /** 收到发送请求，阻塞等用户决定。 */
        boolean askOffer(Types.OfferInfo info);

        void onLog(String msg);

        void onPeersChanged();

        void onProgress(String name, long sent, long total, boolean receiving);

        void onTransferEnd(String summary);

        void onSaved(File file, String rel);
    }

    public interface Prefs {
        String get(String key, String def);

        void set(String key, String value);
    }

    public final String deviceName;
    public final String deviceId;
    public final String token;
    public final File inbox;
    public final File parts;

    private final Prefs prefs;
    private final Host host;
    private Discovery discovery;
    private BeamServer server;
    private final LinkedList<String> logs = new LinkedList<String>();
    private final ExecutorService sender = Executors.newSingleThreadExecutor();
    private volatile boolean sending;
    private volatile Sender.Cancel cancel;
    private volatile String lastSavedName = "";
    private volatile String lastSummary = "";

    public Core(File baseDir, String deviceName, Prefs prefs, Host host) {
        this.deviceName = deviceName;
        this.prefs = prefs;
        this.host = host;
        this.inbox = new File(baseDir, "LanBeam");
        this.parts = new File(baseDir, ".parts");
        String id = prefs.get("device_id", "");
        if (id == null || id.length() < 8) {
            id = randomHex(8);
            prefs.set("device_id", id);
        }
        this.deviceId = id;
        this.token = String.format(Locale.US, "%06d", new Random().nextInt(1000000));
        if (!inbox.exists()) //noinspection ResultOfMethodCallIgnored
            inbox.mkdirs();
        if (!parts.exists()) //noinspection ResultOfMethodCallIgnored
            parts.mkdirs();
    }

    public synchronized void start() {
        if (server != null) return;
        server = new BeamServer(inbox, parts, deviceId, deviceName, token, this);
        server.setAutoAccept(autoAccept());
        server.start();
        discovery = new Discovery(deviceId, deviceName, token, this);
        discovery.setHttpPort(server.getPort());
        discovery.start();
        log("LanBeam 已启动 · " + deviceName + " · 令牌 " + token);
    }

    public synchronized void stop() {
        if (discovery != null) discovery.stop();
        if (server != null) server.stop();
        discovery = null;
        server = null;
    }

    public void restartDiscovery() {
        if (discovery != null) discovery.restart();
    }

    public void setBackground(boolean bg) {
        if (discovery != null) discovery.setBackground(bg);
    }

    public List<Types.Peer> peers() {
        return discovery == null ? new ArrayList<Types.Peer>() : discovery.snapshot();
    }

    public int port() {
        return server == null ? 0 : server.getPort();
    }

    public int discoveryPort() {
        return discovery == null ? 0 : discovery.getBoundPort();
    }

    public boolean autoAccept() {
        return "1".equals(prefs.get("auto_accept", "1"));
    }

    public void setAutoAccept(boolean v) {
        prefs.set("auto_accept", v ? "1" : "0");
        if (server != null) server.setAutoAccept(v);
        log(v ? "已开启自动接收" : "已关闭自动接收，收到请求会先确认");
    }

    public boolean isSending() {
        return sending;
    }

    public boolean isRunning() {
        return server != null;
    }

    public long discoveryAgeMs() {
        return discovery == null ? Long.MAX_VALUE : discovery.lastPacketAgeMs();
    }

    public void cancelSend() {
        Sender.Cancel c = cancel;
        if (c != null) c.cancel();
    }

    public String lastSavedName() {
        return lastSavedName;
    }

    public String lastSummary() {
        return lastSummary;
    }

    public List<String> logs() {
        synchronized (logs) {
            return new ArrayList<String>(logs);
        }
    }

    public void log(String msg) {
        String line = Human.clock(System.currentTimeMillis()) + " " + msg;
        synchronized (logs) {
            logs.addFirst(line);
            while (logs.size() > 400) logs.removeLast();
        }
        host.onLog(msg);
    }

    public void send(final Types.Peer peer, final Sender.Job job) {
        if (sending) {
            log("上一批还没发完，请稍候");
            return;
        }
        sending = true;
        final Sender.Cancel token = new Sender.Cancel();
        cancel = token;
        sender.execute(new Runnable() {
            @Override
            public void run() {
                long t0 = System.currentTimeMillis();
                try {
                    log("开始发送到 " + peer.name + "：" + job.files.size() + " 个文件，" + Human.size(job.total));
                    Sender.send(peer, job, new Sender.Progress() {
                        @Override
                        public void onProgress(String name, long sent, long total) {
                            host.onProgress(name, sent, total, false);
                        }

                        @Override
                        public void onLog(String msg) {
                            log(msg);
                        }
                    }, token);
                    String summary = "已发送 " + job.files.size() + " 个文件，" + Human.size(job.total)
                            + "，用时 " + ((System.currentTimeMillis() - t0) / 1000) + " 秒";
                    lastSummary = summary;
                    log(summary);
                    host.onTransferEnd(summary);
                } catch (Exception e) {
                    String msg = "发送失败：" + (e.getMessage() == null ? e.toString() : e.getMessage());
                    lastSummary = msg;
                    log(msg);
                    host.onTransferEnd(msg);
                } finally {
                    sending = false;
                }
            }
        });
    }

    // ---------------------------------------------------- Discovery.Sink

    @Override
    public void onPeersChanged() {
        host.onPeersChanged();
    }

    @Override
    public void onLog(String msg) {
        log(msg);
    }

    // ---------------------------------------------------- BeamServer.Listener

    @Override
    public boolean askOffer(Types.OfferInfo info) {
        return host.askOffer(info);
    }

    @Override
    public void onProgress(String name, long done, long total) {
        host.onProgress(name, done, total, true);
    }

    @Override
    public void onSaved(File file, String rel) {
        lastSavedName = rel;
        host.onSaved(file, rel);
    }

    public static String randomHex(int bytes) {
        Random r = new Random();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < bytes * 2; i++) sb.append("0123456789abcdef".charAt(r.nextInt(16)));
        return sb.toString();
    }

    public static void closeQuietly(java.io.Closeable c) {
        try {
            if (c != null) c.close();
        } catch (IOException ignored) {
        }
    }
}
