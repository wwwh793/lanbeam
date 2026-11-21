package com.moyuli.lanbeam.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.View;

/** 胶囊进度条（替代系统 ProgressBar，颜色可控）。 */
public class ProgressView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private float progress;
    private boolean dark = true;
    private boolean indeterminate;

    public ProgressView(Context c) {
        super(c);
        setLayoutParams(new android.widget.LinearLayout.LayoutParams(
                android.view.ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(c, 8)));
    }

    public void setDark(boolean d) {
        dark = d;
        invalidate();
    }

    public void setIndeterminate(boolean v) {
        indeterminate = v;
        invalidate();
    }

    public void setProgress(float v) {
        progress = Math.max(0f, Math.min(1f, v));
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        float w = getWidth();
        float h = getHeight();
        float r = h / 2f;
        rect.set(0, 0, w, h);
        paint.setColor(dark ? 0xFF2C2C2E : 0xFFE5E5EA);
        canvas.drawRoundRect(rect, r, r, paint);
        if (indeterminate) {
            paint.setColor(Theme.ACCENT);
            float bw = w * 0.25f;
            float x = (System.currentTimeMillis() % 1400) / 1400f * (w + bw) - bw;
            rect.set(Math.max(0, x), 0, Math.min(w, x + bw), h);
            canvas.drawRoundRect(rect, r, r, paint);
            postInvalidateOnAnimation();
            return;
        }
        if (progress > 0) {
            paint.setColor(Theme.ACCENT);
            rect.set(0, 0, Math.max(h, w * progress), h);
            canvas.drawRoundRect(rect, r, r, paint);
        }
    }
}
