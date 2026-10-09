package kr.jangak.alimi;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 한양대 공개 공지 게시판(근로장학 모집 확인용)을 휴대폰에서 직접 읽는다. 한양대 주소만 허용한다. */
final class HyWork {
    static final String P = "kr_ac_hanyang_noticeBoard_web_portlet_NoticeBoardPortlet";
    static final String[] CATS = {"224311302", "224311300"};
    static final Pattern WORK = Pattern.compile("근로|장학조교|학생\\s*조교|도우미|튜터|Tutor", Pattern.CASE_INSENSITIVE);
    static final Pattern NOT = Pattern.compile("계약직|직원\\s*(채용|모집)|강사|교수|초빙|연구원|연구조교|연구병|인력풀");
    static final Pattern ITEM = Pattern.compile("entryId=(\\d+)[^\"]*\"[^>]*>\\s*([^<]{4,300}?)\\s*</a>");

    private HyWork() { }

    static String listUrl(String cat) {
        return "https://www.hanyang.ac.kr/notice_all?p_p_id=" + P + "&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_" + P
                + "_action=view&_" + P + "_sCategoryId=" + cat + "&_" + P + "_cur=1";
    }

    static boolean allowed(String url) {
        try {
            URL u = new URL(url);
            return "https".equals(u.getProtocol()) && "www.hanyang.ac.kr".equals(u.getHost()) && u.getPath().startsWith("/notice_all");
        } catch (Exception e) {
            return false;
        }
    }

    static String fetch(String url) throws Exception {
        if (!allowed(url)) throw new SecurityException("blocked");
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(12000);
        c.setReadTimeout(15000);
        c.setInstanceFollowRedirects(false);
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android) JangakAlimiApp/1.0");
        c.setRequestProperty("Accept-Language", "ko-KR");
        try (InputStream in = c.getInputStream()) {
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int n, total = 0;
            while ((n = in.read(buf)) > 0 && total < 3_000_000) { bo.write(buf, 0, n); total += n; }
            return bo.toString("UTF-8");
        } finally {
            c.disconnect();
        }
    }

    /** 첫 쪽에서 근로 모집 글의 [번호, 제목] 목록. */
    static List<String[]> workPosts() throws Exception {
        List<String[]> out = new ArrayList<>();
        for (String cat : CATS) {
            Matcher m = ITEM.matcher(fetch(listUrl(cat)));
            while (m.find()) {
                String t = m.group(2).replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", "\"").trim();
                if (WORK.matcher(t).find() && !NOT.matcher(t).find()) out.add(new String[]{m.group(1), t});
            }
        }
        return out;
    }
}
