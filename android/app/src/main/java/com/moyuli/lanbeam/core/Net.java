package com.moyuli.lanbeam.core;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** 网卡与广播地址。安卓和桌面 JVM 通用，不碰平台 API。 */
public final class Net {
    private Net() {
    }

    /** 255.255.255.255 + 每张网卡各自的子网广播地址（安卓上虚拟网卡少，但规则一样）。 */
    public static List<String> broadcastAddresses() {
        List<String> out = new ArrayList<String>();
        out.add("255.255.255.255");
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    InetAddress b = ia.getBroadcast();
                    if (b == null) continue;
                    String host = b.getHostAddress();
                    if (host != null && !out.contains(host)) out.add(host);
                }
            }
        } catch (Exception ignored) {
        }
        return out;
    }

    /** 第一个非回环 IPv4，用于界面展示和兜底广播。 */
    public static String localIpv4() {
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    InetAddress a = ia.getAddress();
                    if (a instanceof Inet4Address) return a.getHostAddress();
                }
            }
        } catch (Exception ignored) {
        }
        return "";
    }
}
