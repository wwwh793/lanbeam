package com.moyuli.lanbeam.core;

import java.io.File;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** 路径清洗与重名处理，规则对齐 协议说明.md 第 3 节。 */
public final class Paths {
    private Paths() {
    }

    private static final Set<String> RESERVED = new HashSet<String>();

    static {
        CollectionsAdd("CON", "PRN", "AUX", "NUL");
        for (int i = 1; i <= 9; i++) {
            CollectionsAdd("COM" + i);
            CollectionsAdd("LPT" + i);
        }
    }

    private static void CollectionsAdd(String... names) {
        for (String n : names) RESERVED.add(n);
    }

    /** 返回空串表示非法（穿越、盘符、超长），调用方应整批拒绝。 */
    public static String safeRel(String rel) {
        if (rel == null) return "";
        String s = rel.replace('\\', '/');
        String[] parts = s.split("/");
        List<String> out = new ArrayList<String>();
        for (String p : parts) {
            if (p.length() == 0 || p.equals(".")) continue;
            if (p.equals("..") || p.indexOf(':') >= 0 || p.length() > 120) return "";
            out.add(sanitizeName(p));
        }
        if (out.isEmpty()) return "";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < out.size(); i++) {
            if (i > 0) sb.append('/');
            sb.append(out.get(i));
        }
        return sb.toString();
    }

    public static String sanitizeName(String name) {
        if (name == null) name = "";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < name.length(); i++) {
            char c = name.charAt(i);
            if (c < 32) continue;
            if ("<>:\"|?*/".indexOf(c) >= 0) {
                sb.append('_');
            } else {
                sb.append(c);
            }
        }
        String s = sb.toString().trim();
        while (s.endsWith(".") || s.endsWith(" ")) s = s.substring(0, s.length() - 1);
        if (s.isEmpty()) s = "item_" + Long.toHexString(System.nanoTime());
        String upper = s.toUpperCase(Locale.ROOT);
        if (RESERVED.contains(upper)) s = "item_" + Long.toHexString(System.nanoTime());
        if (s.length() > 120) {
            int dot = s.lastIndexOf('.');
            if (dot > 0 && s.length() - dot <= 12) {
                s = s.substring(0, 120 - (s.length() - dot)) + s.substring(dot);
            } else {
                s = s.substring(0, 120);
            }
        }
        return s;
    }

    public static File uniqueFile(File dir, String name) {
        File target = new File(dir, name);
        if (!target.exists()) return target;
        String stem = name;
        String ext = "";
        int dot = name.lastIndexOf('.');
        if (dot > 0) {
            stem = name.substring(0, dot);
            ext = name.substring(dot);
        }
        for (int i = 1; i < 10000; i++) {
            File cand = new File(dir, stem + " (" + i + ")" + ext);
            if (!cand.exists()) return cand;
        }
        return new File(dir, stem + "_" + Long.toHexString(System.nanoTime()) + ext);
    }

    public static File uniqueDir(File parent, String name) {
        File target = new File(parent, sanitizeName(name));
        if (!target.exists()) return target;
        for (int i = 1; i < 10000; i++) {
            File cand = new File(parent, target.getName() + " (" + i + ")");
            if (!cand.exists()) return cand;
        }
        return new File(parent, target.getName() + "_" + Long.toHexString(System.nanoTime()));
    }

    /** 拼出 parent/rel 并确认仍在 parent 之内。 */
    public static File resolveInside(File parent, String rel) throws IllegalArgumentException {
        String safe = safeRel(rel);
        if (safe.isEmpty()) throw new IllegalArgumentException("非法路径: " + rel);
        File f = new File(parent, safe);
        try {
            String p = parent.getCanonicalPath();
            String c = f.getCanonicalPath();
            if (!c.equals(p) && !c.startsWith(p + File.separator)) {
                throw new IllegalArgumentException("越界路径: " + rel);
            }
        } catch (java.io.IOException e) {
            throw new IllegalArgumentException("路径解析失败: " + rel);
        }
        return f;
    }
}
