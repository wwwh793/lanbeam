package com.moyuli.lanbeam.ui;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;

/** iOS 风格胶囊开关（54×30 dp），跟鸿蒙端视觉一致。 */
public class Toggle extends View {
    public interface OnChange {
        void onChanged(boolean checked);
    }

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private boolean checked;
    private float anim;
    private ValueAnimator va;
    private OnChange onChange;
    private boolean dark = true;

    public Toggle(Context c) {
        super(c);
        setLayoutParams(new android.widget.LinearLayout.LayoutParams(Ui.dp(c, 52), Ui.dp(c, 30)));
    }

    public Toggle(Context c, AttributeSet a) {
        super(c, a);
    }

    public void setDark(boolean d) {
        dark = d;
        invalidate();
    }

    public boolean isChecked() {
        return checked;
    }

    public void setOnChange(OnChange l) {
        onChange = l;
    }

    public void setChecked(boolean v) {
        setChecked(v, false);
    }

    public void setChecked(boolean v, boolean animate) {
        if (checked == v && anim == (v ? 1f : 0f)) return;
        checked = v;
        if (animate) {
            if (va != null) va.cancel();
            va = ValueAnimator.ofFloat(anim, v ? 1f : 0f);
            va.setDuration(160);
            va.addUpdateListener(new ValueAnimator.AnimatorUpdateListener() {
                @Override
                public void onAnimationUpdate(ValueAnimator a) {
                    anim = (float) a.getAnimatedValue();
                    invalidate();
                }
            });
            va.start();
        } else {
            anim = v ? 1f : 0f;
            invalidate();
        }
    }

    @Override
    protected void onDraw(Canvas canvas) {
        float w = getWidth();
        float h = getHeight();
        float r = h / 2f;
        rect.set(0, 0, w, h);
        paint.setColor(checked ? Theme.ACCENT : (dark ? 0xFF3A3A3C : 0xFFD1D1D6));
        canvas.drawRoundRect(rect, r, r, paint);
        float pad = Ui.dp(getContext(), 2);
        float thumbR = r - pad;
        float cx = pad + thumbR + anim * (w - 2 * pad - 2 * thumbR);
        paint.setColor(0xFFFFFFFF);
        canvas.drawCircle(cx, h / 2f, thumbR, paint);
        paint.setColor(0x1A000000);
        canvas.drawCircle(cx, h / 2f + Ui.dp(getContext(), 1), thumbR, paint);
        paint.setColor(0xFFFFFFFF);
        canvas.drawCircle(cx, h / 2f, thumbR - Ui.dp(getContext(), 1), paint);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getAction() == MotionEvent.ACTION_UP) {
            performClick();
            checked = !checked;
            setChecked(checked, true);
            if (onChange != null) onChange.onChanged(checked);
        }
        return true;
    }

    @Override
    public boolean performClick() {
        super.performClick();
        return true;
    }
}
