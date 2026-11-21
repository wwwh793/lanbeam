package com.moyuli.lanbeam.core;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 发送端（协议 v2 第 2、4 节）：先 /hello，再 /offer，逐个文件 /status → /upload。 */
public final class Sender {
    private Sender() {
    }

    public interface Source {
        /** 批次内的相对路径，用 / 分隔。 */
        String rel();

        long size();

        /** 打开全文；续传时由发送方跳过 offset 字节。 */
        InputStream open() throws IOException;
    }

    public static final class Job {
        public String root = "";
        public String kind = "files";
        public final List<Source> files = new ArrayList<Source>();
        public final List<String> dirs = new ArrayList<String>();
        public long total = 0;
    }

    public interface Progress {
        void onProgress(String name, long sent, long total);

        void onLog(String msg);
    }

    public static final class Cancel {
        private volatile boolean cancelled;

        public void cancel() {
            cancelled = true;
        }

        public boolean isCancelled() {
            return cancelled;
        }
    }

    public static String fid(String root, String rel, long size) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] d = md.digest((root + "/" + rel + "|" + size).getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 8; i++) sb.append(String.format("%02x", d[i]));
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static void send(Types.Peer peer, Job job, Progress p, Cancel cancel) throws IOException {
        String hello = httpText("GET", peer.host, peer.port, "/hello", null, null, 4000);
        if (!hello.contains("LanBeam")) {
            throw new IOException("对方端口不是 LanBeam（" + peer.host + ":" + peer.port + "）");
        }
        String batch = randomHex(16);
        Map<String, Object> offer = new LinkedHashMap<String, Object>();
        offer.put("batch", batch);
        offer.put("kind", job.kind);
        offer.put("root", job.root);
        List<Object> files = new ArrayList<Object>();
        for (Source s : job.files) {
            List<Object> pair = new ArrayList<Object>();
            pair.add(s.rel());
            pair.add(s.size());
            files.add(pair);
        }
        offer.put("files", files);
        offer.put("dirs", new ArrayList<Object>(job.dirs));
        offer.put("total", job.total);
        String q = "?token=" + URLEncoder.encode(peer.token, "UTF-8");
        String body = Json.write(offer);
        String resp = httpText("POST", peer.host, peer.port, "/offer" + q, body, "application/json", 8000);
        if (resp == null) throw new IOException("对方拒绝了这次发送");

        long done = 0;
        for (Source s : job.files) {
            if (cancel.isCancelled()) throw new IOException("已取消");
            String f = fid(job.root, s.rel(), s.size());
            long offset = 0;
            try {
                String st = httpText("GET", peer.host, peer.port, "/status?fid=" + URLEncoder.encode(f, "UTF-8"), null, null, 4000);
                Map<String, Object> m = Json.parseObject(st);
                offset = Json.num(m, "offset", 0);
            } catch (Exception ignored) {
                offset = 0;
            }
            if (offset > s.size()) offset = 0;
            if (offset == s.size() && s.size() > 0) {
                p.onLog("已在对方：" + s.rel());
                done += s.size();
                p.onProgress(s.rel(), done, job.total);
                continue;
            }
            if (offset > 0) p.onLog("续传 " + s.rel() + "，从 " + Human.size(offset) + " 开始");
            final long base = done;
            final long start = offset;
            try {
                upload(peer, batch, f, s, offset, new Progress() {
                    @Override
                    public void onProgress(String name, long sent, long total) {
                        p.onProgress(name, base + sent, job.total);
                    }

                    @Override
                    public void onLog(String msg) {
                        p.onLog(msg);
                    }
                }, cancel);
            } catch (ResumeMismatch e) {
                p.onLog("续传偏移对不上，从头重发 " + s.rel());
                upload(peer, batch, f, s, 0, new Progress() {
                    @Override
                    public void onProgress(String name, long sent, long total) {
                        p.onProgress(name, base + sent, job.total);
                    }

                    @Override
                    public void onLog(String msg) {
                        p.onLog(msg);
                    }
                }, cancel);
            }
            done += s.size();
            p.onProgress(s.rel(), done, job.total);
        }
    }

    private static final class ResumeMismatch extends IOException {
        ResumeMismatch() {
            super("resume mismatch");
        }
    }

    private static void upload(Types.Peer peer, String batch, String fid, Source src, long offset,
                               Progress p, Cancel cancel) throws IOException {
        Socket sock = new Socket();
        sock.setTcpNoDelay(true);
        try {
            sock.connect(new InetSocketAddress(peer.host, peer.port), 6000);
        } catch (IOException e) {
            sock.close();
            throw new IOException("连不上对方：" + e.getMessage());
        }
        try {
            try {
                sock.setSendBufferSize(1024 * 1024);
            } catch (Exception ignored) {
            }
            OutputStream out = sock.getOutputStream();
            long length = src.size() - offset;
            String head = "POST /upload?token=" + URLEncoder.encode(peer.token, "UTF-8")
                    + "&batch=" + URLEncoder.encode(batch, "UTF-8")
                    + "&fid=" + URLEncoder.encode(fid, "UTF-8")
                    + "&path=" + URLEncoder.encode(src.rel(), "UTF-8")
                    + "&size=" + src.size()
                    + " HTTP/1.1\r\nHost: " + peer.host
                    + "\r\nContent-Length: " + length
                    + "\r\nX-Offset: " + offset
                    + "\r\nConnection: close\r\n\r\n";
            out.write(head.getBytes(StandardCharsets.UTF_8));

            InputStream in = src.open();
            try {
                skipFully(in, offset);
                byte[] buf = new byte[256 * 1024];
                long sent = offset;
                long last = 0;
                while (sent < src.size()) {
                    if (cancel.isCancelled()) throw new IOException("已取消");
                    int n = in.read(buf);
                    if (n < 0) break;
                    out.write(buf, 0, n);
                    sent += n;
                    long now = System.currentTimeMillis();
                    if (now - last > 120) {
                        last = now;
                        p.onProgress(src.rel(), sent, src.size());
                    }
                }
                out.flush();
                if (sent != src.size()) throw new IOException("读取中断：" + sent + "/" + src.size());
            } finally {
                try {
                    in.close();
                } catch (Exception ignored) {
                }
            }

            sock.setSoTimeout(120000);
            BufferedReader r = new BufferedReader(new InputStreamReader(sock.getInputStream(), StandardCharsets.ISO_8859_1));
            String status = r.readLine();
            if (status == null) throw new IOException("对方没有响应");
            String rest = r.readLine();
            StringBuilder sb = new StringBuilder();
            int guard = 0;
            while (rest != null && !rest.isEmpty() && guard++ < 50) {
                sb.append(rest).append(' ');
                rest = r.readLine();
            }
            if (status.contains(" 409")) throw new ResumeMismatch();
            if (!status.contains(" 200")) {
                throw new IOException("上传失败：" + status + " " + sb);
            }
        } finally {
            try {
                sock.close();
            } catch (Exception ignored) {
            }
        }
    }

    private static void skipFully(InputStream in, long n) throws IOException {
        long left = n;
        byte[] buf = new byte[8192];
        while (left > 0) {
            long skipped = in.skip(left);
            if (skipped > 0) {
                left -= skipped;
                continue;
            }
            int r = in.read(buf, 0, (int) Math.min(buf.length, left));
            if (r < 0) throw new IOException("文件比预期短");
            left -= r;
        }
    }

    private static String httpText(String method, String host, int port, String path, String body,
                                   String contentType, int timeoutMs) throws IOException {
        HttpURLConnection c = null;
        try {
            URL url = new URL("http://" + host + ":" + port + path);
            c = (HttpURLConnection) url.openConnection();
            c.setRequestMethod(method);
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(Math.max(timeoutMs, 8000));
            c.setUseCaches(false);
            c.setRequestProperty("Connection", "close");
            if (body != null) {
                byte[] b = body.getBytes(StandardCharsets.UTF_8);
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", contentType == null ? "application/json" : contentType);
                c.setFixedLengthStreamingMode(b.length);
                OutputStream o = c.getOutputStream();
                o.write(b);
                o.close();
            }
            int code = c.getResponseCode();
            InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
            StringBuilder sb = new StringBuilder();
            if (in != null) {
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0) sb.append(new String(buf, 0, n, StandardCharsets.UTF_8));
                in.close();
            }
            if ("/offer".equals(path) && code == 403) return null;
            if (code >= 400) throw new IOException("HTTP " + code + " " + sb);
            return sb.toString();
        } finally {
            if (c != null) c.disconnect();
        }
    }

    public static String randomHex(int bytes) {
        java.util.Random r = new java.util.Random();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < bytes * 2; i++) sb.append("0123456789abcdef".charAt(r.nextInt(16)));
        return sb.toString();
    }
}
