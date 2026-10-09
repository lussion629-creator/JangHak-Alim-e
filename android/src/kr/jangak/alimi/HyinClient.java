package kr.jangak.alimi;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

/**
 * 한양 포털(HY-in) 장학캘린더 읽기.
 * 학생이 직접 로그인한 포털 세션으로 조회만 한다. 비밀번호·입력칸은 읽지 않고, 결과는 이 기기 안(앱 전용 저장소)에만 둔다.
 */
final class HyinClient {
    interface Listener {
        void onProgress(String text);
        void onLoginNeeded();
        void onDone(int count);
        void onFail(String text);
    }

    static final String START = "https://portal.hanyang.ac.kr/port.do";
    private final Context ctx;
    private final WebView web;
    private final Listener ln;
    private final boolean silent;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private volatile String host = "";
    private boolean finished;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    HyinClient(Context ctx, WebView web, boolean silent, Listener ln) {
        this.ctx = ctx; this.web = web; this.silent = silent; this.ln = ln;
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setSaveFormData(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);
        web.addJavascriptInterface(new Bridge(), "HyinBridge");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                String sc = u.getScheme() == null ? "" : u.getScheme();
                if ("https".equals(sc) && isHanyang(u.getHost())) return false;
                if (silent) return true;
                // 2차 인증 앱 호출(intent:) 이나 외부 주소는 휴대폰의 앱·브라우저로 연다
                try {
                    Intent it = "intent".equals(sc) ? Intent.parseUri(u.toString(), Intent.URI_INTENT_SCHEME) : new Intent(Intent.ACTION_VIEW, u);
                    it.addCategory(Intent.CATEGORY_BROWSABLE); it.setComponent(null); it.setSelector(null);
                    ctx.startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                } catch (Exception ignored) { }
                return true;
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                Uri u = Uri.parse(url);
                host = u.getHost() == null ? "" : u.getHost();
                CookieManager.getInstance().flush();
                if (finished) return;
                boolean portal = "portal.hanyang.ac.kr".equals(host);
                boolean login = url.contains("lgin") || url.contains("/sso/") || url.contains("login");
                if (portal && !login) {
                    ln.onProgress("로그인 확인됨 · 장학캘린더를 불러오는 중…");
                    v.evaluateJavascript(script(), null);
                } else if (silent) {
                    finish();
                    ln.onLoginNeeded();
                } else {
                    ln.onProgress("한양 포털에 로그인해 주세요. 비밀번호는 앱에 저장되지 않습니다.");
                }
            }
        });
    }

    static boolean isHanyang(String h) {
        return h != null && (h.equals("hanyang.ac.kr") || h.endsWith(".hanyang.ac.kr"));
    }

    void start() { web.loadUrl(START); }

    private void finish() {
        finished = true;
        ui.post(new Runnable() { @Override public void run() { try { web.stopLoading(); } catch (Exception ignored) { } } });
    }

    private String script() {
        try (InputStream in = ctx.getAssets().open("www/tools/hyin-app.js")) {
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] b = new byte[8192]; int n;
            while ((n = in.read(b)) > 0) bo.write(b, 0, n);
            return "window.__hyinKnown=" + knownKeys() + ";\n" + bo.toString("UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    /** 전에 불러온 공고(본문 포함) 번호. 이번에는 이 공고들의 본문을 다시 읽지 않는다. */
    private String knownKeys() {
        try {
            org.json.JSONArray out = new org.json.JSONArray();
            org.json.JSONArray rs = new org.json.JSONObject(read(file(ctx))).getJSONArray("records");
            for (int i = 0; i < rs.length(); i++) {
                org.json.JSONObject r = rs.getJSONObject(i);
                if (r.has("detail")) out.put(key(r));
            }
            return out.toString();
        } catch (Exception e) {
            return "[]";
        }
    }

    static String key(org.json.JSONObject r) {
        return r.optString("year") + "|" + r.optString("term") + "|" + r.optString("cd") + "|" + r.opt("seq") + "|" + r.optString("campus");
    }

    static String read(File f) throws Exception {
        byte[] b = new byte[(int) Math.min(f.length(), 6_000_000)];
        try (java.io.FileInputStream in = new java.io.FileInputStream(f)) { int off = 0, n; while (off < b.length && (n = in.read(b, off, b.length - off)) > 0) off += n; }
        return new String(b, "UTF-8");
    }

    static File file(Context c) { return new File(c.getFilesDir(), "hyin_calendar.json"); }

    class Bridge {
        private boolean ok() { return "portal.hanyang.ac.kr".equals(host) && !finished; }

        @JavascriptInterface
        public void progress(final String t) {
            if (!ok()) return;
            ui.post(new Runnable() { @Override public void run() { ln.onProgress(t == null ? "" : t.substring(0, Math.min(120, t.length()))); } });
        }

        @JavascriptInterface
        public void done(String json) {
            if (!ok() || json == null || json.length() > 6_000_000) return;
            int count = 0;
            try {
                org.json.JSONObject o = new org.json.JSONObject(json);
                org.json.JSONArray rs = o.getJSONArray("records");
                count = rs.length();
                // 본문을 다시 읽지 않은 공고는 전에 저장한 본문을 이어 붙인다
                try {
                    java.util.HashMap<String, Object> old = new java.util.HashMap<>();
                    org.json.JSONArray prev = new org.json.JSONObject(read(file(ctx))).getJSONArray("records");
                    for (int i = 0; i < prev.length(); i++) { org.json.JSONObject r = prev.getJSONObject(i); if (r.has("detail")) old.put(key(r), r.get("detail")); }
                    for (int i = 0; i < rs.length(); i++) { org.json.JSONObject r = rs.getJSONObject(i); if (!r.has("detail") && old.containsKey(key(r))) r.put("detail", old.get(key(r))); }
                } catch (Exception ignored) { }
                o.put("savedAt", System.currentTimeMillis());
                try (FileOutputStream out = new FileOutputStream(file(ctx))) { out.write(o.toString().getBytes(StandardCharsets.UTF_8)); }
            } catch (Exception e) {
                final String msg = "불러온 자료를 저장하지 못했어요.";
                ui.post(new Runnable() { @Override public void run() { ln.onFail(msg); } });
                return;
            }
            finish();
            final int c = count;
            ui.post(new Runnable() { @Override public void run() { ln.onDone(c); } });
        }

        @JavascriptInterface
        public void fail(final String t) {
            if (!ok()) return;
            if ("LOGIN".equals(t)) {
                if (silent) { finish(); ui.post(new Runnable() { @Override public void run() { ln.onLoginNeeded(); } }); }
                else ui.post(new Runnable() { @Override public void run() { ln.onProgress("한양 포털에 로그인해 주세요. 로그인하면 자동으로 불러옵니다."); } });
                return;
            }
            ui.post(new Runnable() { @Override public void run() { ln.onFail(t == null ? "" : t); } });
        }
    }
}
