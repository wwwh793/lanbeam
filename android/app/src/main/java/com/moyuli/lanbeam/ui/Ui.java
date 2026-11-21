package com.moyuli.lanbeam.ui;

import android.app.Activity;
import android.app.Dialog;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.function.Consumer;

/** 用代码搭界面（不引 AndroidX）：圆角卡片、胶囊按钮、对话框都在这里。 */
public final class Ui {
    private Ui() {
    }

    public static int dp(Context c, float v) {
        return Math.round(v * c.getResources().getDisplayMetrics().density);
    }

    public static LinearLayout column(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    public static LinearLayout row(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    public static TextView text(Context c, CharSequence s, float sp, int color) {
        TextView v = new TextView(c);
        v.setText(s);
        v.setTextSize(sp);
        v.setTextColor(color);
        // 显式指定 sans：部分国产 ROM 的默认字体族会落到衬线，中文会变成宋体
        v.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        v.setLineSpacing(dp(c, 2), 1f);
        return v;
    }

    public static TextView bold(Context c, CharSequence s, float sp, int color) {
        TextView v = text(c, s, sp, color);
        v.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        return v;
    }

    public static GradientDrawable round(int color, float radiusPx) {
        GradientDrawable d = new GradientDrawable();
        d.setShape(GradientDrawable.RECTANGLE);
        d.setColor(color);
        d.setCornerRadius(radiusPx);
        return d;
    }

    public static GradientDrawable roundStroke(int fill, int stroke, float radiusPx, int widthPx) {
        GradientDrawable d = round(fill, radiusPx);
        d.setStroke(widthPx, stroke);
        return d;
    }

    public static LinearLayout card(Context c, boolean dark) {
        LinearLayout l = column(c);
        l.setBackground(round(Theme.card(dark), dp(c, 16)));
        int p = dp(c, 16);
        l.setPadding(p, dp(c, 14), p, dp(c, 14));
        return l;
    }

    public static TextView pill(Context c, String s, boolean dark, boolean accent) {
        TextView v = bold(c, s, 12, accent ? Color.WHITE : Theme.ACCENT);
        v.setGravity(Gravity.CENTER);
        v.setPadding(dp(c, 14), dp(c, 7), dp(c, 14), dp(c, 7));
        v.setBackground(round(accent ? Theme.ACCENT : Theme.soft(dark), dp(c, 16)));
        v.setClickable(true);
        v.setFocusable(true);
        return v;
    }

    public static TextView button(Context c, String s, boolean primary, boolean dark) {
        TextView v = bold(c, s, 15, primary ? Color.WHITE : Theme.ACCENT);
        v.setGravity(Gravity.CENTER);
        v.setBackground(round(primary ? Theme.ACCENT : Theme.soft(dark), dp(c, 12)));
        v.setClickable(true);
        v.setFocusable(true);
        return v;
    }

    public static void margin(View v, int l, int t, int r, int b) {
        ViewGroup.LayoutParams lp = v.getLayoutParams();
        if (!(lp instanceof ViewGroup.MarginLayoutParams)) return;
        ViewGroup.MarginLayoutParams m = (ViewGroup.MarginLayoutParams) lp;
        m.setMargins(dp(v.getContext(), l), dp(v.getContext(), t), dp(v.getContext(), r), dp(v.getContext(), b));
        v.setLayoutParams(m);
    }

    public static void gap(View v, int dpSize) {
        Context c = v.getContext();
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(c, dpSize);
        v.setLayoutParams(lp);
    }

    /** 顶栏：左边标题列 + 右边胶囊按钮。 */
    public static LinearLayout header(Context c, boolean dark, String title, String subtitle, View... right) {
        LinearLayout h = row(c);
        LinearLayout col = column(c);
        col.addView(bold(c, title, 28, Theme.fg(dark)));
        if (!TextUtils.isEmpty(subtitle)) {
            TextView sub = text(c, subtitle, 12, Theme.muted(dark));
            margin(sub, 0, 2, 0, 0);
            col.addView(sub);
        }
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        h.addView(col, clp);
        for (View v : right) {
            LinearLayout.LayoutParams rlp = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            rlp.leftMargin = dp(c, 8);
            h.addView(v, rlp);
        }
        return h;
    }

    /** 让内容避开状态栏/导航栏（Android 15 强制 edge-to-edge）。 */
    public static void applyInsets(final View root, final int horizontalDp, final int topDp, final int bottomDp) {
        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                int top;
                int bottom;
                if (android.os.Build.VERSION.SDK_INT >= 30) {
                    android.graphics.Insets i = insets.getInsets(WindowInsets.Type.systemBars());
                    top = i.top;
                    bottom = i.bottom;
                } else {
                    top = insets.getSystemWindowInsetTop();
                    bottom = insets.getSystemWindowInsetBottom();
                }
                v.setPadding(dp(v.getContext(), horizontalDp), top + dp(v.getContext(), topDp),
                        dp(v.getContext(), horizontalDp), bottom + dp(v.getContext(), bottomDp));
                return insets;
            }
        });
        root.requestApplyInsets();
    }

    public static ScrollView scroll(Context c) {
        ScrollView s = new ScrollView(c);
        s.setFillViewport(true);
        s.setVerticalScrollBarEnabled(false);
        return s;
    }

    /** 自绘对话框：标题 + 正文 + 两个按钮，颜色跟主题走。 */
    public static Dialog confirm(Activity a, boolean dark, String title, CharSequence message,
                                 String positive, String negative, final Consumer<Boolean> cb) {
        final Dialog d = new Dialog(a);
        d.requestWindowFeature(Window.FEATURE_NO_TITLE);
        LinearLayout box = column(a);
        box.setBackground(round(dark ? 0xFF1C1C1E : Color.WHITE, dp(a, 18)));
        int p = dp(a, 20);
        box.setPadding(p, p, p, dp(a, 12));
        box.addView(bold(a, title, 17, Theme.fg(dark)));
        TextView body = text(a, message, 13, Theme.fg(dark));
        margin(body, 0, 10, 0, 0);
        box.addView(body);
        LinearLayout buttons = row(a);
        buttons.setGravity(Gravity.END);
        margin(buttons, 0, 18, 0, 0);
        TextView no = bold(a, negative, 14, Theme.muted(dark));
        no.setPadding(dp(a, 14), dp(a, 10), dp(a, 14), dp(a, 10));
        no.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                d.dismiss();
                cb.accept(false);
            }
        });
        TextView yes = bold(a, positive, 14, Theme.ACCENT);
        yes.setPadding(dp(a, 14), dp(a, 10), dp(a, 14), dp(a, 10));
        yes.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                d.dismiss();
                cb.accept(true);
            }
        });
        buttons.addView(no);
        buttons.addView(yes);
        box.addView(buttons);
        d.setContentView(box);
        Window w = d.getWindow();
        if (w != null) {
            w.setBackgroundDrawableResource(android.R.color.transparent);
            w.setLayout(dp(a, 300), ViewGroup.LayoutParams.WRAP_CONTENT);
        }
        d.setCancelable(false);
        d.show();
        return d;
    }

    public static void toast(Context c, String s) {
        android.widget.Toast.makeText(c, s, android.widget.Toast.LENGTH_SHORT).show();
    }
}
