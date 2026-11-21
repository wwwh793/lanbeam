package com.moyuli.lanbeam;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;

import com.moyuli.lanbeam.core.Sender;
import com.moyuli.lanbeam.core.Types;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/** 把系统选择器给的 URI 变成发送清单：文件走 /upload，文件夹递归展开。 */
public final class SendPlan {
    private SendPlan() {
    }

    public static Sender.Job fromUris(Context c, List<Uri> uris) throws IOException {
        Sender.Job job = new Sender.Job();
        job.kind = "files";
        job.root = "";
        for (Uri u : uris) {
            String name = displayName(c, u);
            long size = sizeOf(c, u);
            if (size <= 0) throw new IOException("读不到文件大小（可能是空文件）：" + name);
            job.files.add(new UriSource(c, u, name, size));
            job.total += size;
        }
        if (job.files.isEmpty()) throw new IOException("没有选中文件");
        return job;
    }

    public static Sender.Job fromTree(Context c, Uri tree) throws IOException {
        Sender.Job job = new Sender.Job();
        job.kind = "folder";
        // 树的 DISPLAY_NAME 往往是 "primary:Download/xxx" 这种 id，得拿 document URI 再查一次
        String docId = DocumentsContract.getTreeDocumentId(tree);
        Uri docUri = DocumentsContract.buildDocumentUriUsingTree(tree, docId);
        String root = displayName(c, docUri);
        if (root == null || root.isEmpty() || root.indexOf(':') >= 0 || root.indexOf('/') >= 0) {
            String id = docId;
            int colon = id.lastIndexOf(':');
            if (colon >= 0) id = id.substring(colon + 1);
            int slash = id.lastIndexOf('/');
            root = slash >= 0 ? id.substring(slash + 1) : id;
        }
        if (root == null || root.isEmpty()) root = "文件夹";
        job.root = root;
        walk(c, tree, docId, "", job);
        if (job.files.isEmpty()) throw new IOException("这个文件夹里没有可发送的文件");
        return job;
    }

    private static void walk(Context c, Uri tree, String docId, String prefix, Sender.Job job) throws IOException {
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId);
        ContentResolver cr = c.getContentResolver();
        Cursor cur = null;
        try {
            cur = cr.query(children, new String[]{
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                    DocumentsContract.Document.COLUMN_MIME_TYPE,
                    DocumentsContract.Document.COLUMN_SIZE
            }, null, null, null);
            if (cur == null) throw new IOException("读不到文件夹内容");
            while (cur.moveToNext()) {
                String id = cur.getString(0);
                String name = cur.getString(1);
                String mime = cur.getString(2);
                long size = cur.isNull(3) ? -1 : cur.getLong(3);
                String rel = prefix.isEmpty() ? name : prefix + "/" + name;
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mime)) {
                    job.dirs.add(rel);
                    walk(c, tree, id, rel, job);
                } else {
                    Uri u = DocumentsContract.buildDocumentUriUsingTree(tree, id);
                    if (size <= 0) size = sizeOf(c, u);
                    if (size <= 0) continue;
                    job.files.add(new UriSource(c, u, rel, size));
                    job.total += size;
                }
            }
        } finally {
            if (cur != null) cur.close();
        }
    }

    public static String displayName(Context c, Uri u) {
        Cursor cur = null;
        try {
            cur = c.getContentResolver().query(u, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null);
            if (cur != null && cur.moveToFirst()) {
                String s = cur.getString(0);
                if (s != null && !s.isEmpty()) return s;
            }
        } catch (Exception ignored) {
        } finally {
            if (cur != null) cur.close();
        }
        String path = u.getLastPathSegment();
        return path == null ? "file" : path;
    }

    public static long sizeOf(Context c, Uri u) {
        Cursor cur = null;
        try {
            cur = c.getContentResolver().query(u, new String[]{OpenableColumns.SIZE}, null, null, null);
            if (cur != null && cur.moveToFirst() && !cur.isNull(0)) {
                long s = cur.getLong(0);
                if (s > 0) return s;
            }
        } catch (Exception ignored) {
        } finally {
            if (cur != null) cur.close();
        }
        try {
            android.content.res.AssetFileDescriptor fd = c.getContentResolver().openAssetFileDescriptor(u, "r");
            if (fd != null) {
                long len = fd.getLength();
                fd.close();
                if (len > 0) return len;
            }
        } catch (Exception ignored) {
        }
        return 0;
    }

    public static final class UriSource implements Sender.Source {
        private final Context ctx;
        private final Uri uri;
        private final String rel;
        private final long size;

        UriSource(Context c, Uri u, String rel, long size) {
            this.ctx = c;
            this.uri = u;
            this.rel = rel;
            this.size = size;
        }

        @Override
        public String rel() {
            return rel;
        }

        @Override
        public long size() {
            return size;
        }

        @Override
        public InputStream open() throws IOException {
            InputStream in = ctx.getContentResolver().openInputStream(uri);
            if (in == null) throw new IOException("打不开文件：" + rel);
            return in;
        }
    }
}
