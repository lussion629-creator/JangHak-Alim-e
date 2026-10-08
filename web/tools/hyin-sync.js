/*
 * HY-in 장학캘린더 동기화 스크립트
 *
 * 사용법
 * 1. 브라우저에서 portal.hanyang.ac.kr 에 로그인 → 등록장학 > 장학 > 장학캘린더 화면을 엽니다.
 * 2. F12 → Console 에 이 파일 내용을 붙여 넣고 Enter.
 * 3. SERVER 와 TOKEN 을 채워 두면 서버로 바로 올라가고, 비워 두면 hyin_calendar_full.json 파일로 저장됩니다.
 *    (파일은 서버의 data/imports/ 폴더에 넣으면 다음 갱신 때 반영됩니다.)
 *
 * 비밀번호는 다루지 않습니다. 이미 로그인한 세션이 포털에 보내는 조회 요청만 그대로 사용합니다.
 */
(async function () {
  const SERVER = "";   // 예: "https://내서버주소"
  const TOKEN = "";    // 서버의 ADMIN_TOKEN
  const FROM = new Date(new Date().getFullYear() - 1, 0, 1);
  const TO = new Date(new Date().getFullYear() + 1, 5, 30);
  if (!window.Controller || !window.JCFUtils) { alert("장학캘린더 화면에서 실행하세요."); return; }

  const q = (dt) => {
    Controller.action = "/haksa/JhccAct/findJanghakCalendarList.do";
    Controller.setParams(null, { cbYearOfYm: dt.slice(0, 6), strYear: dt.slice(0, 4), strCampusCd: "", strApplyGb: "", strJaewonGb: "", strMojipGb: "", strDt: dt });
    return JCFUtils.getDataList(Controller.submit());
  };
  const det = (x) => {
    Controller.action = "/haksa/JhccAct/findJanghakGongji.do";
    Controller.setParams(null, { strYear: x.year, strTerm: x.term, strJanghakCd: x.cd, strSeq: String(x.seq), strCampusCd: x.campus === "서울" ? "H" : x.campus === "ERICA" ? "Y" : "" });
    return JCFUtils.getDataList(Controller.submit())[0];
  };
  const pad = (n) => String(n).padStart(2, "0");
  const all = {};
  for (let d = new Date(FROM); d <= TO; d.setDate(d.getDate() + 1)) {
    const dt = d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate());
    for (const r of q(dt)) {
      const k = [r.year, r.term, r.janghakCd, r.seq, r.campusNm].join("|");
      if (!all[k]) all[k] = { campus: r.campusNm, name: r.janghakNm, start: r.startDt, end: r.endDt, jaewon: r.jaewonGb, year: r.year, term: r.term, cd: r.janghakCd, seq: r.seq };
    }
  }
  const strip = (h) => { const el = document.createElement("div"); el.innerHTML = (h || "").replace(/<br\s*\/?>/gi, "\n").replace(/<\/p>/gi, "\n"); return { text: el.innerText.replace(/\n{3,}/g, "\n\n").trim(), imgs: [...el.querySelectorAll("img")].map((i) => i.src) }; };
  for (const x of Object.values(all)) {
    try {
      const r = det(x); if (!r) continue; const s = strip(r.janghakContents);
      x.detail = { office: r.jeopsuNm, text: s.text.slice(0, 6000), imgs: s.imgs,
        docs: [1,2,3,4,5,6,7,8,9,10].map((i) => r["jechulSahang" + i]).filter(Boolean),
        // fileNm1~10, 비고, 신청상태는 로그인한 학생 본인의 제출 서류·상태라서 절대 수집하지 않는다
        files: [r.fileNm].filter(Boolean),
        applyUrl: r.sincheongUrl, period: r.mojipGigan };
    } catch (e) { /* 상세 실패는 건너뜀 */ }
  }
  const payload = { collectedAt: new Date().toISOString(), source: "HY-in 장학캘린더", records: Object.values(all) };
  if (SERVER && TOKEN) {
    const res = await fetch(SERVER.replace(/\/$/, "") + "/api/import/hyin", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN }, body: JSON.stringify(payload) });
    console.log("서버 응답", res.status, await res.text());
  } else {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(payload)], { type: "application/json" }));
    a.download = "hyin_calendar_full.json"; document.body.appendChild(a); a.click();
  }
  console.log("HY-in 장학 " + payload.records.length + "건 수집 완료");
})();
