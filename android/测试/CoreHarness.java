import com.moyuli.lanbeam.core.Core;
import com.moyuli.lanbeam.core.Human;
import com.moyuli.lanbeam.core.Sender;
import com.moyuli.lanbeam.core.Types;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** 桌面测试夹具：在普通 JVM 上跑安卓端的核心层，对拍 Python 端 LanBeam。 */
public final class CoreHarness {

    static final class Prefs implements Core.Prefs {
        final Map<String, String> map = new HashMap<String, String>();

        public String get(String key, String def) {
            String v = map.get(key);
            return v == null ? def : v;
        }

        public void set(String key, String value) {
            map.put(key, value);
        }
    }

    static final class Host implements Core.Host {
        final CountDownLatch saved = new CountDownLatch(1);
        final CountDownLatch ended = new CountDownLatch(1);
        volatile String summary = "";
        volatile String savedPath = "";

        public boolean askOffer(Types.OfferInfo info) {
            System.out.println("EVENT offer " + info.sender + " kind=" + info.kind + " root=" + info.root
                    + " files=" + info.files + " total=" + info.total);
            return true;
        }

        public void onLog(String msg) {
            System.out.println("LOG " + msg);
        }

        public void onPeersChanged() {
        }

        public void onProgress(String name, long sent, long total, boolean receiving) {
        }

        public void onTransferEnd(String s) {
            summary = s;
            System.out.println("EVENT end " + s);
            ended.countDown();
        }

        public void onSaved(File file, String rel) {
            savedPath = file.getAbsolutePath();
            System.out.println("EVENT saved " + rel + " => " + file.getAbsolutePath() + " size=" + file.length());
            saved.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        File dir = new File(args[1]);
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        Host host = new Host();
        Core core = new Core(dir, "安卓测试机", new Prefs(), host);
        core.start();
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            public void run() {
                core.stop();
            }
        }));
        System.out.println("READY port=" + core.port() + " token=" + core.token + " id=" + core.deviceId
                + " inbox=" + core.inbox.getAbsolutePath());

        if ("serve".equals(mode)) {
            BufferedReader r = new BufferedReader(new InputStreamReader(System.in));
            String line;
            while ((line = r.readLine()) != null) {
                if (line.trim().equals("quit")) break;
                if (line.trim().equals("peers")) {
                    List<Types.Peer> ps = core.peers();
                    for (Types.Peer p : ps) System.out.println("PEER " + p.id + " " + p.name + " " + p.host + ":" + p.port);
                    System.out.println("PEERS " + ps.size());
                }
            }
            core.stop();
            return;
        }

        if ("discover".equals(mode)) {
            int secs = Integer.parseInt(args[2]);
            long until = System.currentTimeMillis() + secs * 1000L;
            while (System.currentTimeMillis() < until) {
                Thread.sleep(1000);
                StringBuilder sb = new StringBuilder();
                for (Types.Peer p : core.peers()) sb.append(p.name).append("@").append(p.label()).append(" ");
                System.out.println("PEERS " + core.peers().size() + " " + sb);
            }
            core.stop();
            return;
        }

        if ("send".equals(mode)) {
            final File file = new File(args[2]);
            Types.Peer peer = new Types.Peer();
            peer.host = args[3];
            peer.port = Integer.parseInt(args[4]);
            peer.token = args[5];
            peer.name = "python";
            Sender.Job job = new Sender.Job();
            job.root = "";
            job.kind = "files";
            job.total = file.length();
            final String rel = file.getName();
            job.files.add(new Sender.Source() {
                public String rel() {
                    return rel;
                }

                public long size() {
                    return file.length();
                }

                public InputStream open() throws java.io.IOException {
                    return new FileInputStream(file);
                }
            });
            core.send(peer, job);
            boolean ok = host.ended.await(180, TimeUnit.SECONDS);
            System.out.println("RESULT " + (ok && host.summary.startsWith("已发送") ? "OK" : "FAIL") + " " + host.summary);
            core.stop();
            System.exit(ok && host.summary.startsWith("已发送") ? 0 : 1);
        }
    }
}
