package com.moyuli.lanbeam.core;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

/**
 * UDP 广播发现（协议 v2 第 1 节）。
 *
 * 行为对齐鸿蒙端 1.3.4：
 *  - 每 2 秒广播一次（后台 5 秒），启动时 0/250/700ms 补发三发；
 *  - 收到对方广播立刻单播回执（带 ack=1），回执不引发回执；
 *  - 掉线时间按对方广播节奏自适应：3 × 平均间隔，钳 8–30 秒。
 */
public final class Discovery {

    public interface Sink {
        void onPeersChanged();

        void onLog(String msg);
    }

    private final String deviceId;
    private final String deviceName;
    private final String token;
    private final Sink sink;
    private volatile int httpPort = Types.HTTP_PORT;

    private DatagramSocket socket;
    private Thread rxThread;
    private ScheduledExecutorService timer;
    private volatile boolean running;
    private volatile boolean background;
    private volatile int boundPort = Types.DISCOVERY_PORT;
    private volatile long lastPacketAt = 0;

    private final Map<String, Types.Peer> peers = new ConcurrentHashMap<String, Types.Peer>();
    private final Map<String, Long> lastReply = new ConcurrentHashMap<String, Long>();
    private final Map<String, Long> lastAckSeen = new ConcurrentHashMap<String, Long>();

    public Discovery(String deviceId, String deviceName, String token, Sink sink) {
        this.deviceId = deviceId;
        this.deviceName = deviceName;
        this.token = token;
        this.sink = sink;
    }

    public void setHttpPort(int port) {
        this.httpPort = port;
    }

    public int getBoundPort() {
        return boundPort;
    }

    public synchronized void start() {
        if (running) return;
        try {
            DatagramSocket s = new DatagramSocket(null);
            s.setReuseAddress(true);
            s.setBroadcast(true);
            try {
                s.bind(new InetSocketAddress(Types.DISCOVERY_PORT));
            } catch (SocketException busy) {
                // 同机另一个实例/别的程序占了 47820：退到临时端口，靠 beacon 的 rport 让对面回执
                try {
                    s.close();
                } catch (Exception ignored) {
                }
                s = new DatagramSocket(null);
                s.setReuseAddress(true);
                s.setBroadcast(true);
                s.bind(new InetSocketAddress(0));
            }
            socket = s;
            boundPort = s.getLocalPort();
        } catch (Exception e) {
            sink.onLog("发现通道启动失败：" + e.getMessage());
            return;
        }
        running = true;
        rxThread = new Thread(this::receiveLoop, "lanbeam-udp");
        rxThread.setDaemon(true);
        rxThread.start();

        timer = Executors.newSingleThreadScheduledExecutor(new ThreadFactory() {
            @Override
            public Thread newThread(Runnable r) {
                Thread t = new Thread(r, "lanbeam-beacon");
                t.setDaemon(true);
                return t;
            }
        });
        timer.scheduleAtFixedRate(new Runnable() {
            @Override
            public void run() {
                tick();
            }
        }, 0, 2000, TimeUnit.MILLISECONDS);
        timer.schedule(new Runnable() {
            @Override
            public void run() {
                beacon(false);
            }
        }, 250, TimeUnit.MILLISECONDS);
        timer.schedule(new Runnable() {
            @Override
            public void run() {
                beacon(false);
            }
        }, 700, TimeUnit.MILLISECONDS);
        sink.onLog("发现通道已启动，端口 " + boundPort);
    }

    public synchronized void stop() {
        running = false;
        if (timer != null) {
            timer.shutdownNow();
            timer = null;
        }
        if (socket != null) {
            try {
                socket.close();
            } catch (Exception ignored) {
            }
            socket = null;
        }
        peers.clear();
    }

    /** 长时间后台后 UDP 回调可能卡死，回到前台重建一次最省事。 */
    public synchronized void restart() {
        stop();
        start();
        sink.onPeersChanged();
    }

    public void setBackground(boolean bg) {
        if (background == bg) return;
        background = bg;
        ScheduledExecutorService t = timer;
        if (t != null && !t.isShutdown()) {
            try {
                // 简单起见：整体重启定时器，周期跟着前后台走
                t.shutdownNow();
            } catch (Exception ignored) {
            }
            timer = null;
            synchronized (this) {
                if (!running) return;
            }
            timer = Executors.newSingleThreadScheduledExecutor(new ThreadFactory() {
                @Override
                public Thread newThread(Runnable r) {
                    Thread th = new Thread(r, "lanbeam-beacon");
                    th.setDaemon(true);
                    return th;
                }
            });
            long period = bg ? 5000 : 2000;
            timer.scheduleAtFixedRate(new Runnable() {
                @Override
                public void run() {
                    tick();
                }
            }, period, period, TimeUnit.MILLISECONDS);
        }
    }

    public List<Types.Peer> snapshot() {
        long now = System.currentTimeMillis();
        List<Types.Peer> out = new ArrayList<Types.Peer>();
        for (Types.Peer p : peers.values()) {
            if (now - p.lastSeen <= ttlOf(p)) out.add(p);
        }
        // 按名字排：按 lastSeen 排会让列表随着心跳不停换位，手指点下去容易点错设备
        Collections.sort(out, new Comparator<Types.Peer>() {
            @Override
            public int compare(Types.Peer a, Types.Peer b) {
                int c = a.name.compareToIgnoreCase(b.name);
                return c != 0 ? c : a.id.compareTo(b.id);
            }
        });
        return out;
    }

    private long ttlOf(Types.Peer p) {
        long t = p.gapMs * 3;
        if (t < Types.TTL_MIN_MS) t = Types.TTL_MIN_MS;
        if (t > Types.TTL_MAX_MS) t = Types.TTL_MAX_MS;
        return t;
    }

    private void tick() {
        try {
            beacon(false);
            long now = System.currentTimeMillis();
            boolean changed = false;
            for (Map.Entry<String, Types.Peer> e : peers.entrySet()) {
                Types.Peer p = e.getValue();
                if (now - p.lastSeen > ttlOf(p)) {
                    peers.remove(e.getKey());
                    lastAckSeen.remove(e.getKey());
                    changed = true;
                    sink.onLog("设备离线：" + p.name);
                }
            }
            if (changed) sink.onPeersChanged();
        } catch (Exception ignored) {
        }
    }

    private void beacon(boolean ack) {
        DatagramSocket s = socket;
        if (s == null || !running) return;
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        m.put("app", Types.APP);
        m.put("v", Types.PROTO);
        m.put("id", deviceId);
        m.put("name", deviceName);
        m.put("port", httpPort);
        m.put("token", token);
        m.put("rport", boundPort);
        if (ack) m.put("ack", 1);
        byte[] data = Json.write(m).getBytes(StandardCharsets.UTF_8);
        for (String target : Net.broadcastAddresses()) {
            try {
                s.send(new DatagramPacket(data, data.length, InetAddress.getByName(target), Types.DISCOVERY_PORT));
            } catch (Exception ignored) {
            }
        }
    }

    private void receiveLoop() {
        byte[] buf = new byte[4096];
        while (running) {
            DatagramSocket s = socket;
            if (s == null) break;
            try {
                DatagramPacket pkt = new DatagramPacket(buf, buf.length);
                s.receive(pkt);
                lastPacketAt = System.currentTimeMillis();
                handle(pkt);
            } catch (SocketException e) {
                if (!running) break;
            } catch (Exception ignored) {
            }
        }
    }

    private void handle(DatagramPacket pkt) {
        try {
            String text = new String(pkt.getData(), pkt.getOffset(), pkt.getLength(), StandardCharsets.UTF_8);
            Map<String, Object> m = Json.parseObject(text);
            if (!Types.APP.equals(Json.str(m, "app", ""))) return;
            String id = Json.str(m, "id", "");
            if (id.isEmpty() || id.equals(deviceId)) return;
            String host = pkt.getAddress().getHostAddress();
            long now = System.currentTimeMillis();

            Types.Peer peer = peers.get(id);
            if (peer == null) {
                // 同一地址换了 id（对方重启）：顶掉旧条目，列表里永远只有一行
                int newPort = Json.integer(m, "port", Types.HTTP_PORT);
                List<String> stale = new ArrayList<String>();
                for (Map.Entry<String, Types.Peer> e : peers.entrySet()) {
                    Types.Peer old = e.getValue();
                    if (!e.getKey().equals(id) && host.equals(old.host) && old.port == newPort) {
                        stale.add(e.getKey());
                        sink.onLog("设备重启，替换旧条目：" + old.name);
                    }
                }
                for (String k : stale) {
                    peers.remove(k);
                    lastAckSeen.remove(k);
                }
                peer = new Types.Peer();
                peer.id = id;
                peer.name = Json.str(m, "name", "未知设备");
                peer.host = host;
                peer.port = Json.integer(m, "port", Types.HTTP_PORT);
                peer.token = Json.str(m, "token", "");
                peer.lastSeen = now;
                peer.gapMs = 2000;
                peers.put(id, peer);
                sink.onLog("发现 " + peer.name + "（" + peer.label() + "）");
            } else {
                long gap = now - peer.lastSeen;
                if (gap > 200 && gap < 120000) {
                    peer.gapMs = (long) (peer.gapMs * 0.6 + gap * 0.4);
                    if (peer.gapMs < 500) peer.gapMs = 500;
                    if (peer.gapMs > 60000) peer.gapMs = 60000;
                }
                peer.name = Json.str(m, "name", peer.name);
                peer.port = Json.integer(m, "port", peer.port);
                peer.token = Json.str(m, "token", peer.token);
                peer.lastSeen = now;
            }
            sink.onPeersChanged();

            int ack = Json.integer(m, "ack", 0);
            Long before = lastAckSeen.get(id);
            if (ack != 1 && (before == null || now - before > 2000)) {
                lastAckSeen.put(id, now);
                reply(host, Json.integer(m, "rport", Types.DISCOVERY_PORT));
            }
        } catch (Exception ignored) {
        }
    }

    private void reply(final String host, final int port) {
        final DatagramSocket s = socket;
        if (s == null) return;
        long now = System.currentTimeMillis();
        Long last = lastReply.get(host);
        if (last != null && now - last < 200) return;
        lastReply.put(host, now);
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        m.put("app", Types.APP);
        m.put("v", Types.PROTO);
        m.put("id", deviceId);
        m.put("name", deviceName);
        m.put("port", httpPort);
        m.put("token", token);
        m.put("rport", boundPort);
        m.put("ack", 1);
        byte[] data = Json.write(m).getBytes(StandardCharsets.UTF_8);
        try {
            s.send(new DatagramPacket(data, data.length, InetAddress.getByName(host), port));
        } catch (Exception ignored) {
        }
    }

    public long lastPacketAgeMs() {
        long t = lastPacketAt;
        return t == 0 ? Long.MAX_VALUE : System.currentTimeMillis() - t;
    }
}
