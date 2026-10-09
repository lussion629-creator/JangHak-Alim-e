package kr.jangak.alimi;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/** 사용자가 정한 알림 조건(키워드·지원 종류)에 맞는 새 장학, 관심 장학 마감 임박을 알린다. 조건은 이 기기에만 저장된다. */
final class Alerts {
    static final String DEFAULT_REMOTE = "https://lussion629-creator.github.io/JangHak-Alim-e/";

    private Alerts() { }

    static SharedPreferences sp(Context c) { return c.getSharedPreferences("alerts", Context.MODE_PRIVATE); }

    static void save(Context c, String json) { sp(c).edit().putString("cfg", json).apply(); }

    static String get(String base) throws Exception {
        URL u = new URL(base + "data/meta.json");
        if (!"https".equals(u.getProtocol())) throw new SecurityException("https only");
        HttpURLConnection h = (HttpURLConnection) u.openConnection();
        h.setConnectTimeout(12000); h.setReadTimeout(15000);
        try (InputStream in = h.getInputStream()) {
            ByteArrayOutputStream bo = new ByteArrayOutputStream(); byte[] b = new byte[16384]; int n, t = 0;
            while ((n = in.read(b)) > 0 && t < 2_000_000) { bo.write(b, 0, n); t += n; }
            return bo.toString("UTF-8");
        } finally { h.disconnect(); }
    }

    static void check(Context ctx) throws Exception {
        String cfgS = sp(ctx).getString("cfg", "");
        if (cfgS.isEmpty()) return;
        JSONObject cfg = new JSONObject(cfgS);
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(new NotificationChannel("alerts", "장학 알림", NotificationManager.IMPORTANCE_DEFAULT));
        PendingIntent pi = PendingIntent.getActivity(ctx, 2, new Intent(ctx, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);

        // 1) 관심 장학 마감 임박 (서버 없이도 동작)
        JSONArray fav = cfg.optJSONArray("fav"), before = cfg.optJSONArray("before");
        Set<String> sent = new HashSet<>(sp(ctx).getStringSet("sent", new HashSet<String>()));
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.KOREA).format(new Date());
        if (fav != null && before != null) {
            for (int i = 0; i < fav.length(); i++) {
                JSONObject f = fav.getJSONObject(i);
                String end = f.optString("e");
                if (end.length() != 10) continue;
                long d = (new SimpleDateFormat("yyyy-MM-dd", Locale.KOREA).parse(end).getTime() - new SimpleDateFormat("yyyy-MM-dd", Locale.KOREA).parse(today).getTime()) / 86400000L;
                for (int j = 0; j < before.length(); j++) {
                    if (d == before.optInt(j) && sent.add(f.optString("id") + "@" + end + "@" + d)) {
                        notify(ctx, nm, pi, (f.optString("id") + d).hashCode(), d == 0 ? "오늘 마감" : "마감 " + d + "일 전", f.optString("t"));
                    }
                }
            }
        }
        sp(ctx).edit().putStringSet("sent", sent).apply();

        // 2) 조건에 맞는 새 장학 (서버의 최신 목록과 비교)
        JSONArray kw = cfg.optJSONArray("kw"), cats = cfg.optJSONArray("cats");
        if ((kw == null || kw.length() == 0) && (cats == null || cats.length() == 0)) return;
        String base = cfg.optString("remote", DEFAULT_REMOTE);
        if (!base.startsWith("https://")) base = DEFAULT_REMOTE;
        if (!base.endsWith("/")) base += "/";
        JSONArray open = new JSONObject(get(base)).optJSONArray("open");
        if (open == null) return;
        Set<String> seen = new HashSet<>(sp(ctx).getStringSet("seen", new HashSet<String>()));
        boolean first = seen.isEmpty();
        int shown = 0;
        for (int i = 0; i < open.length(); i++) {
            JSONObject o = open.getJSONObject(i);
            if (!seen.add(o.optString("id")) || first) continue;
            JSONArray fo = o.optJSONArray("f");
            String school = cfg.optString("school", "");
            if (!school.isEmpty() && fo != null && fo.length() > 0 && !fo.toString().contains("\"" + school + "\"")) continue; // 내 학교 학생은 지원할 수 없는 장학
            String hay = (o.optString("t") + " " + o.optString("o")).toLowerCase(Locale.KOREA);
            boolean hit = false;
            if (kw != null) for (int k = 0; k < kw.length() && !hit; k++) { String w = kw.optString(k).trim().toLowerCase(Locale.KOREA); hit = !w.isEmpty() && hay.contains(w); }
            JSONArray s = o.optJSONArray("s");
            if (!hit && cats != null && s != null) for (int k = 0; k < cats.length() && !hit; k++) for (int m = 0; m < s.length() && !hit; m++) hit = cats.optString(k).equals(s.optString(m));
            if (hit && shown < 5) { notify(ctx, nm, pi, o.optString("id").hashCode(), "새 장학 · 알림 조건에 맞음", o.optString("t")); shown++; }
        }
        sp(ctx).edit().putStringSet("seen", seen).apply();
    }

    private static void notify(Context ctx, NotificationManager nm, PendingIntent pi, int id, String title, String text) {
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(ctx, "alerts") : new Notification.Builder(ctx);
        b.setSmallIcon(android.R.drawable.ic_popup_reminder).setContentTitle(title).setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text)).setAutoCancel(true).setContentIntent(pi);
        nm.notify(id, b.build());
    }
}
