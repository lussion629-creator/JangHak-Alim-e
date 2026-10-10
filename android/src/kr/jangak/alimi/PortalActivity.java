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
        Portal pt = Portal.of(getIntent().getStringExtra("key"));
        if (pt == null) pt = Portal.HYIN;
        portal = pt;
        status.setText(pt.name + "에 로그인해 주세요. 비밀번호는 앱에 저장되지 않습니다.");
        bar.addView(status, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button close = new Button(this);
        close.setText("닫기");
        close.setOnClickListener(new android.view.View.OnClickListener() { @Override public void onClick(android.view.View v) { setResult(RESULT_CANCELED); finish(); } });
        bar.addView(close);
        root.addView(bar);
        web = new WebView(this);
        root.addView(web, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
        new HyinClient(this, web, false, pt, this).start();
    }

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    @Override public void onProgress(String text) { status.setText(text); }
    @Override public void onLoginNeeded() { status.setText(portal.name + "에 로그인해 주세요."); }
    @Override public void onDone(int count) { setResult(RESULT_OK, new android.content.Intent().putExtra("key", portal.key)); finish(); }
    @Override public void onFail(String text) { status.setText(text); }

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
