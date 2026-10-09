// 한양대 공개 공지 '모집/채용'(+ '장학/등록')에서 교내·교외 근로 모집 글을 모은다.
// 사용자 컴퓨터의 브라우저에서 https://www.hanyang.ac.kr/ko/notice_all 을 연 뒤 실행한다.
// 실행 전에 window.__known = ["entryId", ...] 로 이미 가진 글 번호를 넣어 두면 새 글만 본문까지 읽는다.
// 첫 쪽(최근 글)만 보고, 글 사이에 쉬어 가며 읽는다.
window.collectHanyangWork = async () => {
  const P = "kr_ac_hanyang_noticeBoard_web_portlet_NoticeBoardPortlet";
  const WORK = /근로|장학조교|학생\s*조교|도우미|튜터|Tutor/i, NOT = /계약직|직원\s*(채용|모집)|강사|교수|초빙|연구원|연구조교|연구병|인력풀/;
  const known = new Set(window.__known || []);
  const out = [];
  for (const cat of ["224311302", "224311300"]) {
    const u = `https://www.hanyang.ac.kr/notice_all?p_p_id=${P}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_${P}_action=view&_${P}_sCategoryId=${cat}&_${P}_cur=1`;
    const d = new DOMParser().parseFromString(await fetch(u).then(r => r.text()), "text/html");
    for (const it of d.querySelectorAll(".hyu-list-body-item")) {
      const a = it.querySelector("h4 a"); if (!a) continue;
      const t = a.textContent.trim(); if (!WORK.test(t) || NOT.test(t)) continue;
      const m = (a.getAttribute("href") || "").match(/entryId=(\d+)/);
      const badges = [...it.querySelectorAll("[data-itemvalue]")].map(b => b.getAttribute("data-itemvalue"));
      const spans = [...it.querySelectorAll("p > span:not(.hyu-badge)")].map(s => s.textContent.trim());
      const dt = (it.querySelector(".date")?.textContent || "").replace(/[^\d.\s]/g, "").trim().split(/\.\s*/).filter(Boolean);
      out.push({ id: m ? m[1] : t, title: t, campus: badges[0] || "", dept: spans[0] || "",
        date: dt.length === 3 ? `${dt[0]}-${dt[1].padStart(2, "0")}-${dt[2].padStart(2, "0")}` : "", cat });
    }
    await new Promise(s => setTimeout(s, 800));
  }
  for (const r of out) {
    if (known.has(r.id)) continue;
    const u = `https://www.hanyang.ac.kr/notice_all?p_p_id=${P}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_${P}_action=view_message&_${P}_sCategoryId=${r.cat}&_${P}_entryId=${r.id}`;
    const d = new DOMParser().parseFromString(await fetch(u).then(x => x.text()), "text/html");
    const det = {};
    d.querySelectorAll(".hyu-meta-item").forEach(mi => {
      const sp = [...mi.children].filter(c => c.tagName === "SPAN").map(s => s.textContent.trim());
      if (sp[0] === "공지기간") {
        const m = [...sp[1].matchAll(/(20\d\d)\.\s*(\d{1,2})\.\s*(\d{1,2})/g)].map(x => `${x[1]}-${x[2].padStart(2, "0")}-${x[3].padStart(2, "0")}`);
        if (m.length === 2) { det.start = m[0]; det.end = m[1]; }
      }
    });
    const b = d.querySelector(".entry-content");
    if (b) {
      b.querySelectorAll("br").forEach(x => x.replaceWith("\n"));
      b.querySelectorAll("p,div,li,tr,h1,h2,h3,h4,table").forEach(x => { x.prepend("\n"); x.append("\n"); });
      det.text = b.textContent.split("\n").map(l => l.replace(/[\s ]+/g, " ").trim()).filter(Boolean).join("\n").slice(0, 1500);
    }
    det.files = [...d.querySelectorAll(".file-download a")].map(a => a.textContent.trim()).slice(0, 2);
    r.detail = det;
    await new Promise(s => setTimeout(s, 800));
  }
  return JSON.stringify(out.filter(r => !known.has(r.id)));
};
