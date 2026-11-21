package com.moyuli.lanbeam;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** 把收件箱里的文件复制到系统「下载/LanBeam」；Android 10+ 走 MediaStore，不需要存储权限。 */
public final class Exports {
    private Exports() {
    }

    public static int export(Context c, File f) throws IOException {
        if (f.isDirectory()) {
            int n = 0;
            File[] kids = f.listFiles();
            if (kids == null) return 0;
            for (File k : kids) n += export(c, k);
            return n;
        }
        Uri uri = insert(c, f);
        OutputStream out = null;
        InputStream in = null;
        try {
            out = c.getContentResolver().openOutputStream(uri);
            if (out == null) throw new IOException("无法写入下载目录");
            in = new FileInputStream(f);
            byte[] buf = new byte[64 * 1024];
            int read;
            while ((read = in.read(buf)) > 0) out.write(buf, 0, read);
        } finally {
            if (in != null) try {
                in.close();
            } catch (IOException ignored) {
            }
            if (out != null) try {
                out.close();
            } catch (IOException ignored) {
            }
        }
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues done = new ContentValues();
            done.put(MediaStore.MediaColumns.IS_PENDING, 0);
            c.getContentResolver().update(uri, done, null, null);
        }
        return 1;
    }

    private static Uri insert(Context c, File f) throws IOException {
        String name = f.getName();
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues v = new ContentValues();
            v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
            v.put(MediaStore.MediaColumns.MIME_TYPE, Files.mime(name));
            v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/LanBeam");
            v.put(MediaStore.MediaColumns.IS_PENDING, 1);
            ContentResolver cr = c.getContentResolver();
            Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
            if (uri == null) throw new IOException("建不了下载文件");
            return uri;
        }
        File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "LanBeam");
        if (!dir.exists() && !dir.mkdirs()) throw new IOException("建不了下载目录");
        File out = new File(dir, name);
        int i = 1;
        while (out.exists()) {
            out = new File(dir, name + " (" + i++ + ")");
        }
        FileOutputStream fos = new FileOutputStream(out);
        FileInputStream fis = new FileInputStream(f);
        try {
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = fis.read(buf)) > 0) fos.write(buf, 0, n);
        } finally {
            try {
                fis.close();
            } catch (IOException ignored) {
            }
            try {
                fos.close();
            } catch (IOException ignored) {
            }
        }
        return Uri.fromFile(out);
    }
}
