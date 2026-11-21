package com.moyuli.lanbeam;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.webkit.MimeTypeMap;

/** 收件箱文件的打开方式：自建 content:// 提供者 + 系统查看器。 */
public final class Files {
    private Files() {
    }

    public static String mime(String name) {
        int dot = name.lastIndexOf('.');
        if (dot > 0) {
            String ext = name.substring(dot + 1).toLowerCase();
            String m = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
            if (m != null) return m;
        }
        return "application/octet-stream";
    }

    /** 相对收件箱的路径，例如 "我的照片/a.jpg"。 */
    public static String relOf(java.io.File inbox, java.io.File f) {
        try {
            if (!f.getCanonicalPath().startsWith(inbox.getCanonicalPath())) return f.getName();
            String s = f.getCanonicalPath().substring(inbox.getCanonicalPath().length());
            while (s.startsWith(java.io.File.separator)) s = s.substring(1);
            return s.replace(java.io.File.separatorChar, '/');
        } catch (Exception e) {
            return f.getName();
        }
    }

    public static void open(Context c, java.io.File inbox, java.io.File f) {
        if (f.isDirectory()) {
            android.widget.Toast.makeText(c, "这是文件夹，可以整包导出到「下载」", android.widget.Toast.LENGTH_SHORT).show();
            return;
        }
        Uri u = InboxProvider.uriFor(relOf(inbox, f));
        Intent i = new Intent(Intent.ACTION_VIEW);
        i.setDataAndType(u, mime(f.getName()));
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            c.startActivity(i);
        } catch (Exception e) {
            android.widget.Toast.makeText(c, "没有能打开这种文件的应用", android.widget.Toast.LENGTH_SHORT).show();
        }
    }
}
