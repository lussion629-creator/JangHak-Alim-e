package kr.jangak.alimi;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** 학생이 직접 학교 포털(한양 포털·강원대 K-Cloud)에 로그인하는 화면. 로그인되면 장학 정보를 읽어 앱에 저장하고 닫힌다. */
public class PortalActivity extends Activity implements HyinClient.Listener {
    private TextView status;
    private Portal portal;
    private WebView web;
    private HyinClient client;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.parseColor("#0d5c6e"));
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackgroundColor(Color.parseColor("#0d5c6e"));
        int p = dp(10);
        bar.setPadding(p, p, p, p);
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        Portal pt = Portal.of(this, getIntent().getStringExtra("key"));
        if (pt == null) pt = Portal.HYIN;
        portal = pt;
        status.setText(pt.name + "에 로그인해 주세요. 비밀번호는 앱에 저장되지 않습니다.");
        bar.addView(status, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button close = new Button(this);
        close.setText("닫기");
        close.setOnClickListener(new android.view.View.OnClickListener() { @Override public void onClick(android.view.View v) { setResult(RESULT_CANCELED); finish(); } });
        bar.addView(close);
        root.addView(bar);
        if (pt.custom) {
            // 학생이 고른 학교 포털: 장학 화면을 열고 '이 화면 저장'을 누르면 그 화면을 기억해 두고 읽는다
            status.setText(pt.saved.isEmpty() ? "로그인한 뒤 장학 공지나 장학 신청 화면을 열고 「이 화면 저장」을 눌러 주세요. 비밀번호는 앱에 저장되지 않습니다." : "저장한 장학 화면을 여는 중이에요.");
            LinearLayout tools = new LinearLayout(this);
            tools.setOrientation(LinearLayout.HORIZONTAL);
            tools.setBackgroundColor(Color.parseColor("#0a4a59"));
            tools.setPadding(p, 0, p, dp(6));
            Button save = new Button(this);
            save.setText("이 화면 저장");
            save.setOnClickListener(new android.view.View.OnClickListener() { @Override public void onClick(android.view.View v) { if (client != null) client.saveHere(); } });
            tools.addView(save);
            Button pc = new Button(this);
            pc.setText(pt.pc ? "휴대폰 화면으로" : "PC 화면으로");
            pc.setOnClickListener(new android.view.View.OnClickListener() { @Override public void onClick(android.view.View v) {
                boolean now = getSharedPreferences(Portal.MY, MODE_PRIVATE).getBoolean("pc", false);
                getSharedPreferences(Portal.MY, MODE_PRIVATE).edit().putBoolean("pc", !now).apply();
                recreate();
            } });
            tools.addView(pc);
            root.addView(tools);
        }
        web = new WebView(this);
        root.addView(web, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
        client = new HyinClient(this, web, false, pt, this);
        client.start();
    }

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    @Override public void onProgress(String text) { status.setText(text); }
    @Override public void onLoginNeeded() { status.setText(portal.name + "에 로그인해 주세요."); }
    @Override public void onDone(int count) { setResult(RESULT_OK, new android.content.Intent().putExtra("key", portal.key)); finish(); }
    @Override public void onFail(String text) {
        if ("EMPTY".equals(text)) text = "이 화면에서 장학 목록을 찾지 못했어요. 장학 공지(또는 장학 신청) 목록이 보이는 화면에서 다시 눌러 주세요.";
        else if ("NOTFOUND".equals(text)) text = "장학 목록을 찾지 못했어요. 장학 화면을 열고 「이 화면 저장」을 눌러 주세요.";
        status.setText(text);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (web != null) { web.removeJavascriptInterface(HyinClient.NATIVE); web.destroy(); }
        super.onDestroy();
    }
}
