package com.moyuli.lanbeam.core;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 接收端 HTTP 服务（协议 v2 第 2 节），手写 HTTP/1.1：
 * 只有 /hello、/status、/offer、/upload 四个入口，Connection: close。
 */
public final class BeamServer {

    public interface Listener {
        boolean askOffer(Types.OfferInfo info);

        void onLog(String msg);

        void onProgress(String name, long done, long total);

        void onSaved(File file, String rel);
    }

    private static final int CHUNK = 64 * 1024;
    private static final int MAX_HEAD = 32 * 1024;
    private static final long MAX_OFFER = 4L * 1024 * 1024;

    private final File inbox;
    private final File parts;
    private final String token;
    private final String deviceId;
    private final String deviceName;
    private final Listener listener;

    private volatile boolean autoAccept = true;
    private volatile int port = Types.HTTP_PORT;
    private ServerSocket server;
    private Thread acceptThread;
    private volatile boolean running;
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private final Map<String, Batch> batches = new ConcurrentHashMap<String, Batch>();
    private volatile long lastProgressAt = 0;

    private static final class Batch {
        File dir;
        long total;
        long done;
        String kind;
        String root;
    }

    public BeamServer(File inbox, File parts, String deviceId, String deviceName, String token, Listener l) {
        this.inbox = inbox;
        this.parts = parts;
        this.deviceId = deviceId;
        this.deviceName = deviceName;
        this.token = token;
        this.listener = l;
    }

    public void setAutoAccept(boolean v) {
        autoAccept = v;
    }

    public int getPort() {
        return port;
    }

    public synchronized void start() {
        if (running) return;
        ServerSocket ss = null;
        int bound = 0;
        for (int candidate = Types.HTTP_PORT; candidate < Types.HTTP_PORT + 20; candidate++) {
            try {
                ss = new ServerSocket();
                ss.setReuseAddress(true);
                ss.bind(new InetSocketAddress(candidate), 32);
                bound = candidate;
                break;
            } catch (IOException e) {
                try {
                    if (ss != null) ss.close();
                } catch (Exception ignored) {
                }
                ss = null;
            }
        }
        if (ss == null) {
            listener.onLog("接收服务启动失败：端口被占用");
            return;
        }
        server = ss;
        port = bound;
        running = true;
        acceptThread = new Thread(new Runnable() {
            @Override
            public void run() {
                acceptLoop();
            }
        }, "lanbeam-http");
        acceptThread.setDaemon(true);
        acceptThread.start();
        listener.onLog("接收服务已启动，端口 " + port);
    }

    public synchronized void stop() {
        running = false;
        try {
            if (server != null) server.close();
        } catch (Exception ignored) {
        }
        server = null;
        pool.shutdownNow();
    }

    private void acceptLoop() {
        while (running) {
            try {
                final Socket s = server.accept();
                pool.execute(new Runnable() {
                    @Override
                    public void run() {
                        handle(s);
                    }
                });
            } catch (IOException e) {
                if (!running) break;
            }
        }
    }

    private void handle(Socket s) {
        try {
            s.setSoTimeout(180000);
            s.setTcpNoDelay(true);
            InputStream in = new BufferedInputStream(s.getInputStream(), 64 * 1024);
            OutputStream out = s.getOutputStream();
            String head = readHead(in);
            if (head == null) {
                s.close();
                return;
            }
            String[] lines = head.split("\r\n");
            String[] first = lines[0].split(" ");
            if (first.length < 2) {
                respond(out, 400, "{\"error\":\"bad request\"}");
                s.close();
                return;
            }
            String method = first[0];
            String target = first[1];
            String path = target;
            String query = "";
            int q = target.indexOf('?');
            if (q >= 0) {
                path = target.substring(0, q);
                query = target.substring(q + 1);
            }
            Map<String, String> headers = new HashMap<String, String>();
            for (int i = 1; i < lines.length; i++) {
                int c = lines[i].indexOf(':');
                if (c > 0) {
                    headers.put(lines[i].substring(0, c).trim().toLowerCase(), lines[i].substring(c + 1).trim());
                }
            }
            String expect = headers.get("expect");
            if (expect != null && expect.toLowerCase().contains("100-continue")) {
                out.write("HTTP/1.1 100 Continue\r\n\r\n".getBytes(StandardCharsets.US_ASCII));
                out.flush();
            }
            if ("/upload".equals(path) && "POST".equals(method)) {
                handleUpload(in, out, query, headers);
            } else if ("/offer".equals(path) && "POST".equals(method)) {
                handleOffer(in, out, query, headers, s);
            } else if ("/hello".equals(path) && "GET".equals(method)) {
                Map<String, Object> m = new LinkedHashMap<String, Object>();
                m.put("app", Types.APP);
                m.put("v", Types.PROTO);
                m.put("name", deviceName);
                m.put("id", deviceId);
                respond(out, 200, Json.write(m));
            } else if ("/status".equals(path) && "GET".equals(method)) {
                String fid = param(query, "fid");
                long offset = 0;
                File part = new File(parts, fid + ".part");
                if (part.exists()) offset = part.length();
                respond(out, 200, "{\"offset\":" + offset + "}");
            } else {
                respond(out, 404, "{\"error\":\"not found\"}");
            }
            out.flush();
        } catch (Exception e) {
            listener.onLog("请求处理失败：" + e.getMessage());
        } finally {
            try {
                s.close();
            } catch (Exception ignored) {
            }
        }
    }

    @SuppressWarnings("unchecked")
    private void handleOffer(InputStream in, OutputStream out, String query, Map<String, String> headers, Socket sock) throws IOException {
        if (!token.equals(param(query, "token"))) {
            respond(out, 403, "{\"error\":\"bad token\"}");
            return;
        }
        long len = parseLong(headers.get("content-length"), -1);
        if (len < 0 || len > MAX_OFFER) {
            respond(out, 400, "{\"error\":\"bad body\"}");
            return;
        }
        byte[] body = readFully(in, (int) len);
        Map<String, Object> offer;
        try {
            offer = Json.parseObject(new String(body, StandardCharsets.UTF_8));
        } catch (Exception e) {
            respond(out, 400, "{\"error\":\"bad body\"}");
            return;
        }
        String batch = Json.str(offer, "batch", "");
        String kind = Json.str(offer, "kind", "files");
        String root = Json.str(offer, "root", "");
        long total = Json.num(offer, "total", 0);
        List<Object> files = (List<Object>) offer.get("files");
        List<Object> dirs = (List<Object>) offer.get("dirs");
        if (batch.isEmpty() || (!"files".equals(kind) && !"folder".equals(kind))) {
            respond(out, 400, "{\"error\":\"bad batch\"}");
            return;
        }
        if (files == null) files = new ArrayList<Object>();
        if (dirs == null) dirs = new ArrayList<Object>();
        for (Object f : files) {
            List<Object> pair = (List<Object>) f;
            if (pair == null || pair.isEmpty()) {
                respond(out, 400, "{\"error\":\"bad files\"}");
                return;
            }
            if (Paths.safeRel(String.valueOf(pair.get(0))).isEmpty()) {
                respond(out, 400, "{\"error\":\"bad path\"}");
                return;
            }
        }
        for (Object d : dirs) {
            if (Paths.safeRel(String.valueOf(d)).isEmpty()) {
                respond(out, 400, "{\"error\":\"bad path\"}");
                return;
            }
        }

        Batch existing = batches.get(batch);
        if (existing != null) {
            respond(out, 200, "{\"ok\":true,\"dir\":" + Json.write(existing.dir.getAbsolutePath()) + ",\"repeat\":true}");
            return;
        }

        String sender = sock.getInetAddress() == null ? "" : sock.getInetAddress().getHostAddress();
        if (!autoAccept) {
            Types.OfferInfo info = new Types.OfferInfo();
            info.sender = sender;
            info.kind = kind;
            info.root = root;
            info.files = files.size();
            info.total = total;
            boolean ok = listener.askOffer(info);
            if (!ok) {
                listener.onLog("已拒收来自 " + sender + " 的请求");
                respond(out, 403, "{\"error\":\"rejected by user\"}");
                return;
            }
            listener.onLog("已接受来自 " + sender + " 的请求");
        }

        File dir;
        try {
            if ("folder".equals(kind)) {
                dir = Paths.uniqueDir(inbox, root.isEmpty() ? "未命名文件夹" : root);
            } else {
                dir = inbox;
            }
            if (!dir.exists() && !dir.mkdirs()) throw new IOException("建目录失败");
            for (Object d : dirs) {
                File sub = Paths.resolveInside(dir, String.valueOf(d));
                if (!sub.exists() && !sub.mkdirs()) throw new IOException("建目录失败");
            }
        } catch (Exception e) {
            respond(out, 500, "{\"error\":" + Json.write(String.valueOf(e.getMessage())) + "}");
            return;
        }

        Batch rec = new Batch();
        rec.dir = dir;
        rec.total = Math.max(total, 1);
        rec.done = 0;
        rec.kind = kind;
        rec.root = root;
        batches.put(batch, rec);
        listener.onLog("接收" + ("folder".equals(kind) ? "文件夹 " + root : "文件") + "："
                + files.size() + " 个，共 " + Human.size(total));
        respond(out, 200, "{\"ok\":true,\"dir\":" + Json.write(dir.getAbsolutePath()) + "}");
    }

    private void handleUpload(InputStream in, OutputStream out, String query, Map<String, String> headers) throws IOException {
        String batchId = param(query, "batch");
        String fid = param(query, "fid");
        String rel = param(query, "path");
        long size = parseLong(param(query, "size"), 0);
        long offset = parseLong(headers.get("x-offset"), 0);
        long length = parseLong(headers.get("content-length"), -1);
        if (!token.equals(param(query, "token"))) {
            drain(in, length);
            respond(out, 403, "{\"error\":\"bad token\"}");
            return;
        }
        Batch rec = batches.get(batchId);
        if (rec == null) {
            drain(in, length);
            respond(out, 409, "{\"error\":\"unknown batch\"}");
            return;
        }
        String safe = Paths.safeRel(rel);
        if (safe.isEmpty()) {
            drain(in, length);
            respond(out, 400, "{\"error\":\"bad path\"}");
            return;
        }
        if (size <= 0 || fid.isEmpty() || offset < 0 || size - offset != length) {
            drain(in, length);
            respond(out, 400, "{\"error\":\"bad size\"}");
            return;
        }
        File part = new File(parts, fid + ".part");
        if (offset > 0) {
            if (!part.exists() || part.length() != offset) {
                drain(in, length);
                respond(out, 409, "{\"error\":\"resume mismatch\"}");
                return;
            }
        } else if (part.exists() && part.length() == size) {
            // 上次已经收完整但没来得及改名：直接丢弃重收
            //noinspection ResultOfMethodCallIgnored
            part.delete();
        }

        if (offset > 0) listener.onLog("续传 " + rel + "：从 " + Human.size(offset) + " 继续");
        RandomAccessFile raf = null;
        try {
            raf = new RandomAccessFile(part, "rw");
            raf.seek(offset);
            byte[] buf = new byte[CHUNK];
            long left = length;
            long written = offset;
            long lastReport = 0;
            while (left > 0) {
                int want = (int) Math.min(buf.length, left);
                int n = in.read(buf, 0, want);
                if (n < 0) throw new IOException("连接中断");
                raf.write(buf, 0, n);
                left -= n;
                written += n;
                rec.done += n;
                long now = System.currentTimeMillis();
                if (now - lastReport > 120) {
                    lastReport = now;
                    listener.onProgress(rel, rec.done, rec.total);
                }
            }
            raf.setLength(size);
        } catch (Exception e) {
            if (raf != null) {
                try {
                    raf.close();
                } catch (Exception ignored) {
                }
            }
            listener.onLog("接收失败 " + rel + "：" + e.getMessage());
            respond(out, 500, "{\"error\":\"write failed\"}");
            return;
        }
        try {
            raf.close();
        } catch (Exception ignored) {
        }
        if (part.length() != size) {
            respond(out, 500, "{\"error\":\"size mismatch\"}");
            return;
        }

        File dest;
        try {
            dest = Paths.resolveInside(rec.dir, safe);
            File parent = dest.getParentFile();
            if (parent != null && !parent.exists() && !parent.mkdirs()) throw new IOException("建目录失败");
            dest = Paths.uniqueFile(parent == null ? rec.dir : parent, dest.getName());
            if (!part.renameTo(dest)) {
                copy(part, dest);
                //noinspection ResultOfMethodCallIgnored
                part.delete();
            }
        } catch (Exception e) {
            listener.onLog("保存失败 " + rel + "：" + e.getMessage());
            respond(out, 500, "{\"error\":\"save failed\"}");
            return;
        }
        listener.onLog("已接收 " + rel + "（" + Human.size(size) + "）");
        listener.onSaved(dest, rel);
        listener.onProgress(rel, rec.done, rec.total);
        respond(out, 200, "{\"ok\":true,\"path\":" + Json.write(dest.getAbsolutePath()) + "}");
    }

    private void copy(File src, File dst) throws IOException {
        InputStream in = new FileInputStream(src);
        OutputStream out = new FileOutputStream(dst);
        byte[] buf = new byte[CHUNK];
        try {
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        } finally {
            try {
                in.close();
            } catch (Exception ignored) {
            }
            try {
                out.close();
            } catch (Exception ignored) {
            }
        }
    }

    private static void drain(InputStream in, long n) {
        if (n <= 0) return;
        byte[] buf = new byte[8192];
        try {
            long left = n;
            while (left > 0) {
                int r = in.read(buf, 0, (int) Math.min(buf.length, left));
                if (r < 0) break;
                left -= r;
            }
        } catch (Exception ignored) {
        }
    }

    private static byte[] readFully(InputStream in, int len) throws IOException {
        byte[] data = new byte[len];
        int off = 0;
        while (off < len) {
            int n = in.read(data, off, len - off);
            if (n < 0) throw new IOException("连接中断");
            off += n;
        }
        return data;
    }

    private static String readHead(InputStream in) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream(1024);
        int state = 0;
        while (bos.size() < MAX_HEAD) {
            int b = in.read();
            if (b < 0) return null;
            bos.write(b);
            if ((state == 0 || state == 2) && b == '\r') state++;
            else if ((state == 1 || state == 3) && b == '\n') state++;
            else state = 0;
            if (state == 4) {
                String s = new String(bos.toByteArray(), StandardCharsets.ISO_8859_1);
                return s.substring(0, s.length() - 4);
            }
        }
        return null;
    }

    private static long parseLong(String s, long def) {
        if (s == null) return def;
        try {
            return Long.parseLong(s.trim());
        } catch (Exception e) {
            return def;
        }
    }

    private static String param(String query, String key) {
        if (query == null || query.isEmpty()) return "";
        String[] parts = query.split("&");
        for (String p : parts) {
            int eq = p.indexOf('=');
            if (eq < 0) continue;
            if (!p.substring(0, eq).equals(key)) continue;
            try {
                return URLDecoder.decode(p.substring(eq + 1), "UTF-8");
            } catch (Exception e) {
                return p.substring(eq + 1);
            }
        }
        return "";
    }

    private static void respond(OutputStream out, int code, String body) throws IOException {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        String head = "HTTP/1.1 " + code + " " + reason(code)
                + "\r\nContent-Type: application/json; charset=utf-8"
                + "\r\nContent-Length: " + b.length
                + "\r\nConnection: close\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.US_ASCII));
        out.write(b);
        out.flush();
    }

    private static String reason(int code) {
        switch (code) {
            case 200: return "OK";
            case 400: return "Bad Request";
            case 403: return "Forbidden";
            case 404: return "Not Found";
            case 409: return "Conflict";
            case 500: return "Internal Server Error";
            default: return "Status";
        }
    }
}
