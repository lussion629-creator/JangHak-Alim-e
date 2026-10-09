package kr.jangak.alimi;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.res.AssetManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

/** 웹앱(assets/www)을 https://app.jangak.local/ 주소로 띄우는 WebView 셸. 외부 링크는 브라우저로 연다. */
public class MainActivity extends Activity {
    static final String HOST = "app.jangak.local";
    static final String ORIGIN = "https://" + HOST + "/";
    private WebView web;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.parseColor("#0d5c6e"));
        web = new WebView(this);
        android.widget.FrameLayout root = new android.widget.FrameLayout(this);
        root.addView(web, new android.widget.FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setSupportMultipleWindows(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setGeolocationEnabled(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setSaveFormData(false);
        s.setTextZoom(100);
        web.addJavascriptInterface(new Bridge(), "AndroidBridge");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (HOST.equals(u.getHost()) && "https".equals(u.getScheme())) return false;
                // 외부 링크는 http/https 만 기본 브라우저로 연다 (intent:, file:, javascript: 등 차단)
                String sc = u.getScheme();
                if ("http".equals(sc) || "https".equals(sc)) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, u).addCategory(Intent.CATEGORY_BROWSABLE)); } catch (Exception ignored) { }
                }
                return true;
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (!HOST.equals(u.getHost())) return null;
                String path = u.getPath();
                if (path == null || path.equals("/") || path.isEmpty()) path = "/index.html";
                if (path.contains("..")) return new WebResourceResponse("text/plain", "utf-8", 403, "Forbidden", new HashMap<String, String>(), null);
                try {
                    AssetManager am = getAssets();
                    InputStream in = am.open("www" + path);
                    Map<String, String> h = new HashMap<>();
                    h.put("Access-Control-Allow-Origin", "*");
                    h.put("Cache-Control", "no-cache");
                    return new WebResourceResponse(mime(path), "utf-8", 200, "OK", h, in);
                } catch (Exception e) {
                    return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", new HashMap<String, String>(), null);
                }
            }
        });
        if (saved != null) web.restoreState(saved); else web.loadUrl(ORIGIN + "index.html");
        try { WorkJob.schedule(this); } catch (Exception ignored) { }
        silentHyin(root);
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != 0) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        }
    }

    static String mime(String p) {
        if (p.endsWith(".html")) return "text/html";
        if (p.endsWith(".json")) return "application/json";
        if (p.endsWith(".js")) return "application/javascript";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".webmanifest")) return "application/manifest+json";
        return "application/octet-stream";
    }

    static final int REQ_PORTAL = 41;
    private WebView hidden;

    /** 전에 로그인한 적이 있고 하루가 지났으면, 남아 있는 포털 로그인으로 조용히 장학캘린더를 다시 읽어 본다. */
    private void silentHyin(final android.widget.FrameLayout root) {
        java.io.File f = HyinClient.file(this);
        if (!f.exists() || System.currentTimeMillis() - f.lastModified() < 20L * 60 * 60 * 1000) return;
        getSharedPreferences("hyin", MODE_PRIVATE).edit().putString("state", "checking").apply();
        hidden = new WebView(this);
        root.addView(hidden, new android.widget.FrameLayout.LayoutParams(1, 1));
        hidden.setAlpha(0f);
        final HyinClient c = new HyinClient(this, hidden, true, new HyinClient.Listener() {
            @Override public void onProgress(String t) { }
            @Override public void onLoginNeeded() { setState("login"); dropHidden(); }
            @Override public void onDone(int n) { setState("ok"); dropHidden(); web.evaluateJavascript("window.__hyinUpdated&&window.__hyinUpdated()", null); }
            @Override public void onFail(String t) { setState("fail"); dropHidden(); }
        });
        c.start();
        web.postDelayed(new Runnable() { @Override public void run() { if (hidden != null) { setState("login"); dropHidden(); } } }, 120000);
    }

    private void setState(String s) { getSharedPreferences("hyin", MODE_PRIVATE).edit().putString("state", s).apply(); }

    private void dropHidden() {
        final WebView h = hidden; hidden = null;
        if (h != null) web.post(new Runnable() { @Override public void run() { try { ((android.view.ViewGroup) h.getParent()).removeView(h); h.removeJavascriptInterface("HyinBridge"); h.destroy(); } catch (Exception ignored) { } } });
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_PORTAL && res == RESULT_OK) { setState("ok"); web.evaluateJavascript("window.__hyinUpdated&&window.__hyinUpdated()", null); }
    }

    @Override protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }

    @Override
    public void onBackPressed() {
        web.evaluateJavascript("window.__back&&window.__back()", new android.webkit.ValueCallback<String>() {
            @Override public void onReceiveValue(String r) {
                if (!"true".equals(r)) { if (web.canGoBack()) web.goBack(); else finish(); }
            }
        });
    }

    /** 페이지가 호출: 관심 장학금 중 마감 임박 항목을 알림으로 띄운다. */
    class Bridge {
        @JavascriptInterface
        public void notifyDeadlines(String json) {
            try {
                JSONArray arr = new JSONArray(json);
                NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
                if (Build.VERSION.SDK_INT >= 26) {
                    nm.createNotificationChannel(new NotificationChannel("deadline", "장학 마감 알림", NotificationManager.IMPORTANCE_DEFAULT));
                }
                PendingIntent pi = PendingIntent.getActivity(MainActivity.this, 0, new Intent(MainActivity.this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
                for (int i = 0; i < arr.length() && i < 5; i++) {
                    JSONObject o = arr.getJSONObject(i);
                    Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(MainActivity.this, "deadline") : new Notification.Builder(MainActivity.this);
                    b.setSmallIcon(android.R.drawable.ic_popup_reminder)
                     .setContentTitle(o.optString("label") + " · " + o.optString("title"))
                     .setContentText(o.optString("org"))
                     .setAutoCancel(true).setContentIntent(pi);
                    nm.notify(o.optString("id").hashCode(), b.build());
                }
            } catch (Exception ignored) { }
        }

        @JavascriptInterface
        public String platform() { return "android"; }

        /** 한양대 공개 공지 페이지를 휴대폰에서 직접 받아 페이지로 돌려준다 (근로장학 모집 확인용, 한양대 공지 주소만). */
        @JavascriptInterface
        public void fetchHanyang(final String url, final String cb) {
            if (!HyWork.allowed(url) || !cb.matches("[A-Za-z0-9_]{1,40}")) return;
            new Thread(new Runnable() {
                @Override public void run() {
                    String body;
                    try { body = JSONObject.quote(HyWork.fetch(url)); } catch (Exception e) { body = "null"; }
                    final String js = "window.__hyCb&&window.__hyCb('" + cb + "'," + body + ")";
                    web.post(new Runnable() { @Override public void run() { web.evaluateJavascript(js, null); } });
                }
            }).start();
        }

        /** 한양 포털 로그인 화면을 연다 (학생이 직접 로그인). */
        @JavascriptInterface
        public void openPortal() {
            runOnUiThread(new Runnable() { @Override public void run() { startActivityForResult(new Intent(MainActivity.this, PortalActivity.class), REQ_PORTAL); } });
        }

        /** 이 기기에 저장된 장학캘린더 자료 (없으면 빈 문자열). */
        @JavascriptInterface
        public String hyinData() {
            try {
                java.io.File f = HyinClient.file(MainActivity.this);
                if (!f.exists()) return "";
                byte[] b = new byte[(int) Math.min(f.length(), 6_000_000)];
                try (java.io.FileInputStream in = new java.io.FileInputStream(f)) { int off = 0, n; while (off < b.length && (n = in.read(b, off, b.length - off)) > 0) off += n; }
                return new String(b, "UTF-8");
            } catch (Exception e) { return ""; }
        }

        @JavascriptInterface
        public String hyinState() { return getSharedPreferences("hyin", MODE_PRIVATE).getString("state", ""); }

        /** 장학캘린더 자료와 포털 로그인 기록을 이 기기에서 지운다. */
        @JavascriptInterface
        public void hyinClear() {
            try { HyinClient.file(MainActivity.this).delete(); } catch (Exception ignored) { }
            setState("");
            runOnUiThread(new Runnable() { @Override public void run() { android.webkit.CookieManager.getInstance().removeAllCookies(null); } });
        }

        /** 앱에서 본 근로 모집 글 번호를 알림 작업과 공유해, 이미 본 글로 다시 알리지 않게 한다. */
        @JavascriptInterface
        public void markWorkSeen(String json) {
            try {
                JSONArray arr = new JSONArray(json);
                android.content.SharedPreferences sp = getSharedPreferences("hywork", MODE_PRIVATE);
                java.util.Set<String> seen = new java.util.HashSet<>(sp.getStringSet("seen", new java.util.HashSet<String>()));
                for (int i = 0; i < arr.length(); i++) seen.add(arr.getString(i));
                sp.edit().putStringSet("seen", seen).apply();
            } catch (Exception ignored) { }
        }
    }
}
