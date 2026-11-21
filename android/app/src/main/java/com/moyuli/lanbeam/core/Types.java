package com.moyuli.lanbeam.core;

/** 协议常量与共享数据结构。 */
public final class Types {
    private Types() {
    }

    public static final String APP = "LanBeam";
    public static final int PROTO = 2;
    public static final int DISCOVERY_PORT = 47820;
    public static final int HTTP_PORT = 47821;

    /** 长后台时鸿蒙/安卓都可能把广播拉长，掉线判定按对方节奏自适应（3 倍间隔，钳 8–30 秒）。 */
    public static final long TTL_MIN_MS = 8000;
    public static final long TTL_MAX_MS = 30000;

    public static final class Peer {
        public String id = "";
        public String name = "";
        public String host = "";
        public int port = HTTP_PORT;
        public String token = "";
        public volatile long lastSeen = 0;
        public volatile long gapMs = 2000;
        public String label() {
            return host + ":" + port;
        }
    }

    public static final class OfferInfo {
        public String sender = "";
        public String kind = "files";
        public String root = "";
        public int files = 0;
        public long total = 0;
    }
}
