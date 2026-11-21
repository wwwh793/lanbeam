package com.moyuli.lanbeam.core;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 极简 JSON。LanBeam 协议只需要对象/数组/字符串/数字/布尔，引第三方库反而拖累构建，
 * 所以这里手写一个够用的解析器 —— 顺带让核心层能直接在桌面 JVM 上跑测试。
 */
public final class Json {
    private Json() {
    }

    // ---------------------------------------------------------------- 解析

    public static Object parse(String text) {
        Parser p = new Parser(text);
        p.skipWs();
        Object v = p.value();
        p.skipWs();
        if (!p.eof()) throw new IllegalArgumentException("trailing data at " + p.i);
        return v;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> parseObject(String text) {
        Object v = parse(text);
        if (!(v instanceof Map)) throw new IllegalArgumentException("not an object");
        return (Map<String, Object>) v;
    }

    public static Map<String, Object> obj(Object... kv) {
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        for (int i = 0; i + 1 < kv.length; i += 2) m.put(String.valueOf(kv[i]), kv[i + 1]);
        return m;
    }

    public static String str(Map<String, Object> m, String key, String def) {
        Object v = m.get(key);
        return v == null ? def : String.valueOf(v);
    }

    public static long num(Map<String, Object> m, String key, long def) {
        Object v = m.get(key);
        if (v instanceof Number) return ((Number) v).longValue();
        if (v instanceof String) {
            try {
                return Long.parseLong((String) v);
            } catch (NumberFormatException ignored) {
            }
        }
        return def;
    }

    public static int integer(Map<String, Object> m, String key, int def) {
        return (int) num(m, key, def);
    }

    public static boolean bool(Map<String, Object> m, String key, boolean def) {
        Object v = m.get(key);
        if (v instanceof Boolean) return (Boolean) v;
        if (v instanceof Number) return ((Number) v).intValue() != 0;
        return def;
    }

    // ---------------------------------------------------------------- 输出

    public static String write(Object o) {
        StringBuilder sb = new StringBuilder(256);
        write(sb, o);
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    private static void write(StringBuilder sb, Object o) {
        if (o == null) {
            sb.append("null");
        } else if (o instanceof String) {
            quote(sb, (String) o);
        } else if (o instanceof Boolean) {
            sb.append(o.toString());
        } else if (o instanceof Double || o instanceof Float) {
            double d = ((Number) o).doubleValue();
            if (d == Math.rint(d) && Math.abs(d) < 1e15) sb.append((long) d);
            else sb.append(d);
        } else if (o instanceof Number) {
            sb.append(o.toString());
        } else if (o instanceof Map) {
            sb.append('{');
            boolean first = true;
            for (Map.Entry<String, Object> e : ((Map<String, Object>) o).entrySet()) {
                if (!first) sb.append(',');
                first = false;
                quote(sb, e.getKey());
                sb.append(':');
                write(sb, e.getValue());
            }
            sb.append('}');
        } else if (o instanceof Iterable) {
            sb.append('[');
            boolean first = true;
            for (Object v : (Iterable<Object>) o) {
                if (!first) sb.append(',');
                first = false;
                write(sb, v);
            }
            sb.append(']');
        } else {
            quote(sb, o.toString());
        }
    }

    private static void quote(StringBuilder sb, String s) {
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        sb.append('"');
    }

    private static final class Parser {
        private final String s;
        int i;

        Parser(String s) {
            this.s = s;
        }

        boolean eof() {
            return i >= s.length();
        }

        void skipWs() {
            while (i < s.length()) {
                char c = s.charAt(i);
                if (c == ' ' || c == '\n' || c == '\r' || c == '\t') i++;
                else break;
            }
        }

        Object value() {
            skipWs();
            if (eof()) throw new IllegalArgumentException("unexpected end");
            char c = s.charAt(i);
            if (c == '{') return object();
            if (c == '[') return array();
            if (c == '"') return string();
            if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
            if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
            if (s.startsWith("null", i)) { i += 4; return null; }
            return number();
        }

        Map<String, Object> object() {
            Map<String, Object> m = new LinkedHashMap<String, Object>();
            i++;
            skipWs();
            if (!eof() && s.charAt(i) == '}') { i++; return m; }
            while (true) {
                skipWs();
                String k = string();
                skipWs();
                if (eof() || s.charAt(i) != ':') throw new IllegalArgumentException("expected : at " + i);
                i++;
                m.put(k, value());
                skipWs();
                if (eof()) throw new IllegalArgumentException("unexpected end in object");
                char c = s.charAt(i++);
                if (c == '}') return m;
                if (c != ',') throw new IllegalArgumentException("expected , at " + (i - 1));
            }
        }

        List<Object> array() {
            List<Object> list = new ArrayList<Object>();
            i++;
            skipWs();
            if (!eof() && s.charAt(i) == ']') { i++; return list; }
            while (true) {
                list.add(value());
                skipWs();
                if (eof()) throw new IllegalArgumentException("unexpected end in array");
                char c = s.charAt(i++);
                if (c == ']') return list;
                if (c != ',') throw new IllegalArgumentException("expected , at " + (i - 1));
            }
        }

        String string() {
            if (eof() || s.charAt(i) != '"') throw new IllegalArgumentException("expected string at " + i);
            i++;
            StringBuilder sb = new StringBuilder();
            while (i < s.length()) {
                char c = s.charAt(i++);
                if (c == '"') return sb.toString();
                if (c == '\\') {
                    char e = s.charAt(i++);
                    switch (e) {
                        case 'n': sb.append('\n'); break;
                        case 'r': sb.append('\r'); break;
                        case 't': sb.append('\t'); break;
                        case 'b': sb.append('\b'); break;
                        case 'f': sb.append('\f'); break;
                        case 'u':
                            sb.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                            i += 4;
                            break;
                        default: sb.append(e);
                    }
                } else {
                    sb.append(c);
                }
            }
            throw new IllegalArgumentException("unterminated string");
        }

        Object number() {
            int start = i;
            while (i < s.length()) {
                char c = s.charAt(i);
                if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E') i++;
                else break;
            }
            String t = s.substring(start, i);
            if (t.isEmpty()) throw new IllegalArgumentException("unexpected char at " + start);
            if (t.indexOf('.') < 0 && t.indexOf('e') < 0 && t.indexOf('E') < 0) {
                try {
                    return Long.parseLong(t);
                } catch (NumberFormatException ignored) {
                    return Double.parseDouble(t);
                }
            }
            return Double.parseDouble(t);
        }
    }
}
