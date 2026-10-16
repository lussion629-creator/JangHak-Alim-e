package kr.jangak.alimi;

import android.content.Context;

import org.json.JSONObject;

import java.io.File;

/** 앱이 읽을 수 있는 학교 포털. 로그인 화면 판별·자동 로그인 입력·읽기 스크립트를 포털마다 정한다. */
final class Portal {
    final String key, name, start, mainHost, asset, fileName;
    // 학생이 직접 고른 학교 포털 (key "my"): 학교 주소(domain), 저장한 장학 화면 주소(saved)와 그 화면까지 누른 메뉴(menus)
    final boolean custom;
    final String domain, saved, menus;
    final boolean pc;

    private Portal(String key, String name, String start, String mainHost, String asset, String fileName) {
        this.key = key; this.name = name; this.start = start; this.mainHost = mainHost; this.asset = asset; this.fileName = fileName;
        this.custom = false; this.domain = ""; this.saved = ""; this.menus = "[]"; this.pc = false;
    }

    private Portal(String name, String domain, String entry, String saved, String menus, boolean pc) {
        this.key = "my"; this.name = name; this.domain = domain; this.saved = saved; this.menus = menus == null || menus.isEmpty() ? "[]" : menus; this.pc = pc;
        this.start = saved != null && !saved.isEmpty() ? saved : entry;
        String h = android.net.Uri.parse(this.start).getHost();
        this.mainHost = h == null ? domain : h; this.asset = "www/tools/portal-reader.js"; this.fileName = "my_portal.json"; this.custom = true;
    }

    static final String MY = "myportal";

    /** 학생이 고른 학교 포털 (없으면 null). */
    static Portal custom(Context c) {
        android.content.SharedPreferences sp = c.getSharedPreferences(MY, Context.MODE_PRIVATE);
        String d = sp.getString("domain", ""), e = sp.getString("entry", "");
        if (d.isEmpty() || e.isEmpty()) return null;
        return new Portal(sp.getString("name", "학교") + " 포털", d, e, sp.getString("saved", ""), sp.getString("menus", "[]"), sp.getBoolean("pc", false));
    }

    static Portal of(Context c, String key) { return "my".equals(key) ? custom(c) : of(key); }

    /** 미리 맞춘 포털 + 학생이 고른 학교 포털. */
    static java.util.List<Portal> all(Context c) {
        java.util.ArrayList<Portal> l = new java.util.ArrayList<>(java.util.Arrays.asList(ALL));
        Portal m = custom(c); if (m != null) l.add(m);
        return l;
    }

    /** 읽기 스크립트를 넣고 결과를 받을 수 있는 주소 (학생이 고른 포털은 그 학교 주소 전체). */
    boolean isMain(String h) {
        if (h == null) return false;
        if (custom) return h.equals(domain) || h.endsWith("." + domain) || h.equals(mainHost);
        return mainHost.equals(h);
    }

    static final Portal HYIN = new Portal("hyin", "한양 포털", "https://portal.hanyang.ac.kr/port.do", "portal.hanyang.ac.kr", "www/tools/hyin-app.js", "hyin_calendar.json");
    static final Portal KCLOUD = new Portal("kcloud", "강원대 K-Cloud", "https://kcloud.kangwon.ac.kr/", "kcloud.kangwon.ac.kr", "www/tools/portal-reader.js", "kcloud_scholarship.json");
    static final Portal SAINT = new Portal("saint", "서강대 SAINT", "https://saint.sogang.ac.kr/irj/portal", "saint.sogang.ac.kr", "www/tools/portal-reader.js", "saint_scholarship.json");
    static final Portal KUIS = new Portal("kuis", "건국대 학사정보시스템", "https://kuis.konkuk.ac.kr/", "kuis.konkuk.ac.kr", "www/tools/portal-reader.js", "kuis_scholarship.json");
    static final Portal[] ALL = {HYIN, KCLOUD, SAINT, KUIS};
    static final String DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";

    /** 읽기 스크립트 설정 (메뉴 이름·학교 주소·안내 문구). */
    String cfg() {
        if (this == KCLOUD) return "window.__portalCfg={host:'kangwon.ac.kr',menus:[['학부생서비스','교과','장학','장학신청']],hint:'장학 신청 화면을 열어 주세요: 학부생서비스 → 교과 → 장학 → 장학신청'};";
        if (this == KUIS) return "window.__portalCfg={host:'konkuk.ac.kr',menus:[['장학','장학금신청'],['장학','장학금 신청'],['장학','교내장학금신청'],['장학','장학신청']],hint:'장학금 신청 화면을 열어 주세요 (학사정보시스템 → 장학). 그 화면의 목록을 읽어 와요.'};";
        if (custom) return "window.__portalCfg={host:" + JSONObject.quote(domain) + ",menus:[" + menus + "],generic:true,hint:'장학 공지나 장학 신청 화면을 연 뒤 위의 「이 화면 저장」을 눌러 주세요.'};";
        if (this == SAINT) return "window.__portalCfg={host:'sogang.ac.kr',menus:[['학사정보','장학','장학금신청'],['학사정보','장학','장학신청'],['학사정보','장학금','장학금 신청']],hint:'장학금 신청 화면을 열어 주세요 (학사정보 → 장학). 그 화면의 목록을 읽어 와요.'};";
        return "";
    }

    /** 모바일 브라우저를 막는 포털(SAINT)은 PC 화면으로 연다. */
    boolean desktop() { return custom ? pc : (this == SAINT || this == KUIS); }

    /** 주소만으로 로그인 화면인지 알 수 없는 포털은 화면에 로그인 칸이 있는지 본다 ('login' / 'in'). */
    String loginProbe() {
        if (this == SAINT) return "(function(){return (document.getElementById('logonForm')||document.getElementById('login_id'))?'login':'in';})()";
        // 화면에 보이는 비밀번호 칸이 있으면 로그인 화면 (작은 창 안의 로그인 칸도 본다)
        if (this == KUIS || custom) return "(function(){function v(d){try{return Array.prototype.some.call(d.querySelectorAll('input[type=password]'),function(e){return e.offsetParent!==null;})}catch(x){return false}}"
                + "if(v(document))return 'login';var f=document.querySelectorAll('iframe,frame');for(var i=0;i<f.length;i++){try{if(f[i].contentDocument&&v(f[i].contentDocument))return 'login';}catch(x){}}return 'in';})()";
        return null;
    }

    static Portal of(String key) {
        for (Portal p : ALL) if (p.key.equals(key)) return p;
        return null;
    }

    /** 이 포털의 화면으로 이어지는 학교 주소인지 (다른 주소로는 가지 않는다). */
    boolean schoolHost(String h) {
        if (h == null) return false;
        if (custom) return isMain(h) || h.endsWith(".ac.kr") || h.equals("ac.kr"); // 학교 통합 로그인(SSO)이 다른 학교 주소로 넘어가는 경우
        if (this == HYIN) return h.equals("hanyang.ac.kr") || h.endsWith(".hanyang.ac.kr");
        if (this == SAINT) return h.equals("sogang.ac.kr") || h.endsWith(".sogang.ac.kr");
        if (this == KUIS) return h.equals("konkuk.ac.kr") || h.endsWith(".konkuk.ac.kr");
        return h.equals("kangwon.ac.kr") || h.endsWith(".kangwon.ac.kr");
    }

    boolean isLogin(String url) {
        if (this == HYIN) return url.contains("lgin") || url.contains("/sso/") || url.contains("login");
        if (this == SAINT) return url.contains("logon") || url.contains("login");
        if (this == KUIS || custom) return url.toLowerCase().contains("login") || url.toLowerCase().contains("sso") || url.toLowerCase().contains("logon");
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
        if (this == SAINT) {
            return "(function(){var u=document.getElementById('login_id'),p=document.getElementById('login_pw');if(!u||!p)return;window.alert=function(){};" + setter
                    + "s(u," + JSONObject.quote(id) + ");s(p," + JSONObject.quote(pw) + ");"
                    + "if(typeof btnLogin==='function'){btnLogin();}else{var b=document.querySelector('.form_login_btn');if(b)b.click();}})();";
        }
        if (this == KUIS || custom) {
            // 보이는 비밀번호 칸과 그 앞의 아이디 칸을 채우고, 로그인 버튼(없으면 폼 제출)을 누른다
            return "(function(){window.alert=function(){};" + setter
                    + "function go(d){var p=Array.prototype.filter.call(d.querySelectorAll('input[type=password]'),function(e){return e.offsetParent!==null;})[0];if(!p)return false;"
                    + "var ins=Array.prototype.filter.call(d.querySelectorAll('input'),function(e){return e.offsetParent!==null&&/^(text|email|tel|)$/.test(e.type||'');});"
                    + "var u=null;for(var i=0;i<ins.length;i++){if(ins[i].compareDocumentPosition(p)&4)u=ins[i];}if(!u)return false;"
                    + "s(u," + JSONObject.quote(id) + ");s(p," + JSONObject.quote(pw) + ");"
                    + "var b=Array.prototype.filter.call(d.querySelectorAll('button,input[type=submit],input[type=image],a'),function(e){return e.offsetParent!==null&&/로그인|LOGIN|Login|확인/.test((e.textContent||'')+(e.value||'')+(e.alt||''));})[0];"
                    + "if(b)b.click();else if(p.form)p.form.submit();return true;}"
                    + "if(!go(document)){var f=document.querySelectorAll('iframe,frame');for(var i=0;i<f.length;i++){try{if(f[i].contentDocument&&go(f[i].contentDocument))break;}catch(x){}}}})();";
        }
        // K-Cloud '아이디 로그인'(학생) 칸. 문자·메일 추가 인증이 켜진 계정은 자동으로 끝낼 수 없어 실패로 처리된다.
        return "(function(){var u=document.getElementById('NORMAL_ID'),p=document.getElementById('NORMAL_PWD'),b=document.getElementById('btn_Login');if(!u||!p||!b)return;"
                + "window.alert=function(){};" + setter
                + "s(u," + JSONObject.quote(id) + ");s(p," + JSONObject.quote(pw) + ");b.click();})();";
    }
}
