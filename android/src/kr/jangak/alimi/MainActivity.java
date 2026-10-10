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
        try { HyinJob.schedule(this); } catch (Exception ignored) { }
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

    /** 전에 로그인한 적이 있고 하루가 지났으면, 남아 있는 포털 로그인으로 조용히 장학 정보를 다시 읽어 본다 (포털마다 차례로). */
    private void silentHyin(final android.widget.FrameLayout root) {
        if (hidden != null) return;
        for (final Portal p : Portal.ALL) {
            java.io.File f = p.file(this);
            if (!f.exists() && !"on".equals(Cred.state(this, p.key))) continue;
            if (f.exists() && System.currentTimeMillis() - f.lastModified() < 20L * 60 * 60 * 1000) continue;
            setState(p, "checking");
            hidden = new WebView(this);
            root.addView(hidden, new android.widget.FrameLayout.LayoutParams(1, 1));
            hidden.setAlpha(0f);
            final HyinClient c = new HyinClient(this, hidden, true, p, new HyinClient.Listener() {
                @Override public void onProgress(String t) { }
                @Override public void onLoginNeeded() { setState(p, "login"); next(); }
                @Override public void onDone(int n) { setState(p, "ok"); updated(p); next(); }
                @Override public void onFail(String t) { if (!"notfound".equals(st(p))) setState(p, "fail"); next(); }
                private void next() { dropHidden(); web.postDelayed(new Runnable() { @Override public void run() { silentHyin(root); } }, 1500); }
            });
            c.start();
            final WebView mine = hidden;
            web.postDelayed(new Runnable() { @Override public void run() { if (hidden == mine) { setState(p, "login"); dropHidden(); } } }, 120000);
            return;
        }
    }

    private void updated(Portal p) {
        web.evaluateJavascript(p == Portal.HYIN ? "window.__hyinUpdated&&window.__hyinUpdated()" : "window.__portalUpdated&&window.__portalUpdated('" + p.key + "')", null);
    }

    private String st(Portal p) { return getSharedPreferences(p.prefs(), MODE_PRIVATE).getString("state", ""); }

    private void setState(Portal p, String s) { getSharedPreferences(p.prefs(), MODE_PRIVATE).edit().putString("state", s).apply(); }

    private void showLoginDialog() { showLoginDialog(Portal.HYIN); }

    private void showLoginDialog(final Portal pt) {
        final android.widget.LinearLayout box = new android.widget.LinearLayout(this);
        box.setOrientation(android.widget.LinearLayout.VERTICAL);
        int p = Math.round(20 * getResources().getDisplayMetrics().density);
        box.setPadding(p, p / 2, p, 0);
        final android.widget.EditText id = new android.widget.EditText(this);
        id.setHint(pt == Portal.HYIN ? "포털 아이디" : "학번"); id.setSingleLine(true);
        id.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        final android.widget.EditText pw = new android.widget.EditText(this);
        pw.setHint("비밀번호"); pw.setSingleLine(true);
        pw.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        android.widget.TextView note = new android.widget.TextView(this);
        note.setText("아이디·비밀번호는 이 휴대폰의 안전한 저장소에 암호화해 두고, " + pt.name + " 로그인 칸에만 넣습니다. 서버로 보내지 않습니다. 로그인이 한 번 실패하면 계정이 잠기지 않도록 자동 로그인을 멈춥니다.");
        note.setTextSize(13);
        box.addView(id); box.addView(pw); box.addView(note);
        new android.app.AlertDialog.Builder(this).setTitle(pt.name + " 자동 로그인").setView(box)
            .setPositiveButton("저장", new android.content.DialogInterface.OnClickListener() { @Override public void onClick(android.content.DialogInterface d, int w) {
                String i = id.getText().toString().trim(), s = pw.getText().toString();
                if (i.isEmpty() || s.isEmpty()) return;
                try { Cred.save(MainActivity.this, pt.key, i, s); } catch (Exception e) { return; }
                pw.setText("");
                updated(pt);
                // 바로 한 번 확인 (기존 세션이 끝났으면 자동 로그인)
                java.io.File f = pt.file(MainActivity.this);
                if (f.exists()) f.setLastModified(0);
                silentHyin((android.widget.FrameLayout) web.getParent());
            } })
            .setNegativeButton("취소", null).show();
    }

    private void setState(String s) { setState(Portal.HYIN, s); }

    private void dropHidden() {
        final WebView h = hidden; hidden = null;
        if (h != null) web.post(new Runnable() { @Override public void run() { try { ((android.view.ViewGroup) h.getParent()).removeView(h); h.removeJavascriptInterface(HyinClient.NATIVE); h.destroy(); } catch (Exception ignored) { } } });
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_PORTAL && res == RESULT_OK) {
            Portal p = Portal.of(data == null ? null : data.getStringExtra("key"));
            if (p == null) p = Portal.HYIN;
            setState(p, "ok");
            if ("failed".equals(Cred.state(this, p.key))) Cred.setState(this, p.key, "on");
            updated(p);
        }
    }

    @Override
    public void onConfigurationChanged(android.content.res.Configuration c) {
        super.onConfigurationChanged(c);
        if (web != null) web.evaluateJavascript("window.__sysTheme&&window.__sysTheme()", null);
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

        /** 휴대폰이 어두운 화면(다크 모드)인지. */
        @JavascriptInterface
        public boolean isDark() {
            return (getResources().getConfiguration().uiMode & android.content.res.Configuration.UI_MODE_NIGHT_MASK) == android.content.res.Configuration.UI_MODE_NIGHT_YES;
        }

        /** 페이지 밝기에 맞춰 상단 상태 표시줄 색을 바꾼다. */
        @JavascriptInterface
        public void setDark(final boolean dark) {
            runOnUiThread(new Runnable() { @Override public void run() {
                getWindow().setStatusBarColor(Color.parseColor(dark ? "#0e1216" : "#0d5c6e"));
                if (Build.VERSION.SDK_INT >= 29) web.getSettings().setForceDark(WebSettings.FORCE_DARK_OFF);
            } });
        }

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

        /** 알림 조건 저장(이 기기에만) 후 바로 한 번 확인한다. */
        @JavascriptInterface
        public void setAlerts(String json) {
            try { new JSONObject(json); } catch (Exception e) { return; }
            Alerts.save(MainActivity.this, json);
            new Thread(new Runnable() { @Override public void run() { try { Alerts.check(MainActivity.this); } catch (Exception ignored) { } } }).start();
        }

        /** 자동 로그인: 아이디·비밀번호를 앱의 입력 창(웹 페이지가 아님)에서 받아 암호화해 저장한다. */
        @JavascriptInterface
        public void autoLoginSetup() {
            runOnUiThread(new Runnable() { @Override public void run() { showLoginDialog(); } });
        }

        @JavascriptInterface
        public String autoLoginState() { return Cred.state(MainActivity.this); }

        @JavascriptInterface
        public void autoLoginOff() { Cred.clear(MainActivity.this); }

        /** 한양 포털 로그인 화면을 연다 (학생이 직접 로그인). */
        @JavascriptInterface
        public void openPortal() {
            runOnUiThread(new Runnable() { @Override public void run() { startActivityForResult(new Intent(MainActivity.this, PortalActivity.class), REQ_PORTAL); } });
        }

        // ---- 학교 포털 공통 (key: hyin = 한양 포털, kcloud = 강원대 K-Cloud) ----
        @JavascriptInterface
        public void portalOpen(final String key) {
            final Portal p = Portal.of(key); if (p == null) return;
            runOnUiThread(new Runnable() { @Override public void run() { startActivityForResult(new Intent(MainActivity.this, PortalActivity.class).putExtra("key", p.key), REQ_PORTAL); } });
        }

        @JavascriptInterface
        public String portalData(String key) {
            Portal p = Portal.of(key); if (p == null) return "";
            try { java.io.File f = p.file(MainActivity.this); return f.exists() ? HyinClient.read(f) : ""; } catch (Exception e) { return ""; }
        }

        @JavascriptInterface
        public String portalState(String key) { Portal p = Portal.of(key); return p == null ? "" : st(p); }

        @JavascriptInterface
        public void portalClear(String key) {
            final Portal p = Portal.of(key); if (p == null) return;
            try { p.file(MainActivity.this).delete(); } catch (Exception ignored) { }
            setState(p, "");
            runOnUiThread(new Runnable() { @Override public void run() {
                // 그 포털 주소의 쿠키만 지운다
                android.webkit.CookieManager cm = android.webkit.CookieManager.getInstance();
                String ck = cm.getCookie("https://" + p.mainHost + "/");
                if (ck != null) for (String c : ck.split(";")) { String n = c.split("=")[0].trim(); if (!n.isEmpty()) cm.setCookie("https://" + p.mainHost + "/", n + "=; Max-Age=0"); }
                cm.flush();
            } });
        }

        @JavascriptInterface
        public void portalLoginSetup(String key) {
            final Portal p = Portal.of(key); if (p == null) return;
            runOnUiThread(new Runnable() { @Override public void run() { showLoginDialog(p); } });
        }

        @JavascriptInterface
        public String portalLoginState(String key) { Portal p = Portal.of(key); return p == null ? "off" : Cred.state(MainActivity.this, p.key); }

        @JavascriptInterface
        public void portalLoginOff(String key) { Portal p = Portal.of(key); if (p != null) Cred.clear(MainActivity.this, p.key); }

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
