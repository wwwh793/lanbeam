package com.moyuli.lanbeam;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import com.moyuli.lanbeam.core.Paths;

import java.io.File;
import java.io.FileNotFoundException;

/** 只读地把收件箱里的文件暴露成 content://，供系统查看器/分享使用。 */
public class InboxProvider extends ContentProvider {
    public static final String AUTHORITY = "com.moyuli.lanbeam.inbox";

    public static Uri uriFor(String rel) {
        return Uri.parse("content://" + AUTHORITY + "/f?p=" + Uri.encode(rel));
    }

    private File base() {
        File b = getContext() == null ? null : getContext().getExternalFilesDir(null);
        if (b == null && getContext() != null) b = getContext().getFilesDir();
        return new File(b, "LanBeam");
    }

    private File resolve(Uri uri) throws FileNotFoundException {
        String rel = uri.getQueryParameter("p");
        if (rel == null || rel.isEmpty()) throw new FileNotFoundException("空路径");
        try {
            File f = Paths.resolveInside(base(), rel);
            if (!f.exists()) throw new FileNotFoundException(rel);
            return f;
        } catch (IllegalArgumentException e) {
            throw new FileNotFoundException(rel);
        }
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        return ParcelFileDescriptor.open(resolve(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        try {
            return Files.mime(resolve(uri).getName());
        } catch (Exception e) {
            return "application/octet-stream";
        }
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        try {
            File f = resolve(uri);
            String[] cols = projection != null ? projection
                    : new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
            MatrixCursor c = new MatrixCursor(cols, 1);
            Object[] row = new Object[cols.length];
            for (int i = 0; i < cols.length; i++) {
                if (OpenableColumns.DISPLAY_NAME.equals(cols[i])) row[i] = f.getName();
                else if (OpenableColumns.SIZE.equals(cols[i])) row[i] = f.length();
                else row[i] = null;
            }
            c.addRow(row);
            return c;
        } catch (Exception e) {
            return null;
        }
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        try {
            File f = resolve(uri);
            return f.delete() ? 1 : 0;
        } catch (Exception e) {
            return 0;
        }
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        return 0;
    }
}
