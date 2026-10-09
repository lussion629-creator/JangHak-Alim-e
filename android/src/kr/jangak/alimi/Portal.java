package kr.jangak.alimi;

import android.content.Context;

import org.json.JSONObject;

import java.io.File;

/** 앱이 읽을 수 있는 학교 포털. 로그인 화면 판별·자동 로그인 입력·읽기 스크립트를 포털마다 정한다. */
final class Portal {
    final String key, name, start, mainHost, asset, fileName;

    private Portal(String key, String name, String start, String mainHost, String asset, String fileName) {
        this.key = key; this.name = name; this.start = start; this.mainHost = mainHost; this.asset = asset; this.fileName = fileName;
    }

    static final Portal HYIN = new Portal("hyin", "한양 포털", "https://portal.hanyang.ac.kr/port.do", "portal.hanyang.ac.kr", "www/tools/hyin-app.js", "hyin_calendar.json");
    static final Portal KCLOUD = new Portal("kcloud", "강원대 K-Cloud", "https://kcloud.kangwon.ac.kr/", "kcloud.kangwon.ac.kr", "www/tools/kcloud-app.js", "kcloud_scholarship.json");
    static final Portal[] ALL = {HYIN, KCLOUD};

    static Portal of(String key) {
        for (Portal p : ALL) if (p.key.equals(key)) return p;
        return null;
    }

    /** 이 포털의 화면으로 이어지는 학교 주소인지 (다른 주소로는 가지 않는다). */
    boolean schoolHost(String h) {
        if (h == null) return false;
        if (this == HYIN) return h.equals("hanyang.ac.kr") || h.endsWith(".hanyang.ac.kr");
        return h.equals("kangwon.ac.kr") || h.endsWith(".kangwon.ac.kr");
    }

    boolean isLogin(String url) {
        if (this == HYIN) return url.contains("lgin") || url.contains("/sso/") || url.contains("login");
        return url.contains("/login") || url.contains("ssoLogin") || url.contains("ssm01008") || url.contains("cert_install") || url.contains("notice_before_login") || url.endsWith("kangwon.ac.kr/");
    }

    File file(Context c) { return new File(c.getFilesDir(), fileName); }

    String prefs() { return this == HYIN ? "hyin" : "portal_" + key; }

    /** 로그인 칸에 저장된 아이디·비밀번호를 넣고 로그인 버튼을 누른다 (포털 자체 로그인 절차를 그대로 쓴다). */
    String loginScript(String id, String pw) {
        String setter = "var d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');"
                + "function s(e,v){d.set.call(e,v);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}";
        if (this == HYIN) {
            return "(function(){var u=document.getElementById('userId'),p=document.getElementById('password');if(!u||!p)return;" + setter
                    + "s(u," + JSONObject.quote(id) + ");s(p," + JSONObject.quote(pw) + ");"
                    + "var a=Array.prototype.filter.call(document.querySelectorAll('a,button'),function(e){return (e.textContent||'').trim()==='로그인'&&e.offsetParent!==null;})[0];"
                    + "if(a)a.click();})();";
        }
        // K-Cloud '아이디 로그인'(학생) 칸. 문자·메일 추가 인증이 켜진 계정은 자동으로 끝낼 수 없어 실패로 처리된다.
        return "(function(){var u=document.getElementById('NORMAL_ID'),p=document.getElementById('NORMAL_PWD'),b=document.getElementById('btn_Login');if(!u||!p||!b)return;"
                + "window.alert=function(){};" + setter
                + "s(u," + JSONObject.quote(id) + ");s(p," + JSONObject.quote(pw) + ");b.click();})();";
    }
}
