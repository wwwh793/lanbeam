package com.moyuli.lanbeam.core;

/** 1099511628 → "1.0 GB"。 */
public final class Human {
    private Human() {
    }

    public static String size(long n) {
        if (n < 1024) return n + " B";
        double v = n / 1024.0;
        if (v < 1024) return String.format(java.util.Locale.US, "%.1f KB", v);
        v /= 1024.0;
        if (v < 1024) return String.format(java.util.Locale.US, "%.1f MB", v);
        v /= 1024.0;
        return String.format(java.util.Locale.US, "%.2f GB", v);
    }

    public static String speed(long bytes, long ms) {
        if (ms <= 0) return "";
        double bps = bytes * 1000.0 / ms;
        return size((long) bps) + "/s";
    }

    public static String time(long ts) {
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("MM-dd HH:mm", java.util.Locale.CHINA);
        return f.format(new java.util.Date(ts));
    }

    public static String clock(long ts) {
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.CHINA);
        return f.format(new java.util.Date(ts));
    }
}
