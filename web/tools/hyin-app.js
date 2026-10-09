/* 장학알리미 앱 전용: 로그인한 한양 포털(HY-in)에서 장학캘린더를 읽어 앱으로 넘긴다.
 * - 비밀번호·입력칸은 건드리지 않는다. 로그인된 세션이 포털에 보내는 조회 요청만 쓴다.
 * - 학생 본인의 제출 서류(fileNm1~10)·비고·신청 상태는 절대 읽지 않는다.
 * - 결과는 HyinBridge.done(JSON) 으로 앱에만 넘긴다(서버로 보내지 않음).
 */
(function () {
  if (window.__hyinRunning) return; window.__hyinRunning = true;
  var B = window.HyinBridge;
  var say = function (t) { try { B.progress(t); } catch (e) {} };
  var pad = function (n) { return String(n).padStart(2, "0"); };
  var ymd = function (d) { return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()); };
  var waited = 0;
  function ready() { return window.Controller && window.JCFUtils && typeof Controller.submit === "function"; }
  function start() {
    if (!ready()) {
      waited++;
      if (waited === 3) { // 메뉴에 '장학캘린더'가 보이면 눌러서 연다
        var a = Array.prototype.filter.call(document.querySelectorAll("a,li,span,button"), function (e) { return /장학\s*캘린더/.test(e.textContent || "") && (e.textContent || "").length < 30; })[0];
        if (a) try { a.click(); } catch (e) {}
      }
      if (waited > 60) return fail("장학캘린더 화면을 찾지 못했어요. 포털 메뉴에서 장학캘린더를 직접 열어 주세요.");
      if (waited === 8) say("포털 메뉴에서 ‘장학캘린더’ 화면을 열어 주세요. 열리면 자동으로 불러옵니다.");
      return setTimeout(start, 1500);
    }
    run();
  }
  function q(dt) {
    Controller.action = "/haksa/JhccAct/findJanghakCalendarList.do";
    Controller.setParams(null, { cbYearOfYm: dt.slice(0, 6), strYear: dt.slice(0, 4), strCampusCd: "H", strApplyGb: "", strJaewonGb: "", strMojipGb: "", strDt: dt });
    var res = Controller.submit();
    if (res === null || res === undefined) throw new Error("LOGIN"); // 로그인이 안 된 세션은 빈 응답(null)을 준다
    return JCFUtils.getDataList(res) || [];
  }
  function det(x) {
    Controller.action = "/haksa/JhccAct/findJanghakGongji.do";
    Controller.setParams(null, { strYear: x.year, strTerm: x.term, strJanghakCd: x.cd, strSeq: String(x.seq), strCampusCd: x.campus === "서울" ? "H" : x.campus === "ERICA" ? "Y" : "" });
    return (JCFUtils.getDataList(Controller.submit()) || [])[0];
  }
  function strip(h) {
    var el = document.createElement("div");
    el.innerHTML = String(h || "").replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr)>/gi, "\n").replace(/<(script|style|iframe)[\s\S]*?<\/\1>/gi, "");
    var imgs = Array.prototype.map.call(el.querySelectorAll("img"), function (i) { return i.getAttribute("src") || ""; }).filter(function (u) { return /^https:\/\//.test(u); });
    return { text: (el.textContent || "").replace(/[ \t ]+/g, " ").replace(/\n\s*\n\s*\n+/g, "\n\n").trim(), imgs: imgs.slice(0, 4) };
  }
  function run() {
    // 포털에 부담을 주지 않도록: 2주 전 ~ 5개월 뒤 일정만, 조금씩 쉬어 가며 읽는다
    var from = new Date(); from.setDate(from.getDate() - 14);
    var to = new Date(); to.setDate(to.getDate() + 150);
    var known = {}; (window.__hyinKnown || []).forEach(function (k) { known[k] = 1; });
    var days = []; for (var d = new Date(from); d <= to; d.setDate(d.getDate() + 1)) days.push(ymd(d));
    var all = {}, i = 0;
    function stepDays() {
      var end = Math.min(i + 10, days.length);
      try {
        for (; i < end; i++) {
          var rows = q(days[i]);
          for (var k = 0; k < rows.length; k++) {
            var r = rows[k], key = [r.year, r.term, r.janghakCd, r.seq, r.campusNm].join("|");
            if (r.campusNm === "ERICA") continue; // 서울캠퍼스만
            if (!all[key]) all[key] = { campus: r.campusNm, name: r.janghakNm, start: r.startDt, end: r.endDt, jaewon: r.jaewonGb, year: r.year, term: r.term, cd: r.janghakCd, seq: r.seq };
          }
        }
      } catch (e) { return fail(String(e && e.message) === "LOGIN" ? "LOGIN" : "장학캘린더를 읽지 못했어요. 로그인이 끝났는지 확인해 주세요."); }
      say("장학캘린더 읽는 중… " + Math.round(i / days.length * 70) + "%");
      if (i < days.length) return setTimeout(stepDays, 250);
      details(Object.keys(all).map(function (k) { return all[k]; }));
    }
    function details(list) {
      var j = 0;
      function stepDet() {
        var end = Math.min(j + 4, list.length);
        for (; j < end; j++) {
          var x = list[j];
          if (known[[x.year, x.term, x.cd, x.seq, x.campus].join("|")]) continue; // 전에 읽은 공고는 앱에 있는 내용을 그대로 쓴다
          try {
            var r = det(x); if (!r) continue; var s = strip(r.janghakContents);
            var docs = []; for (var n = 1; n <= 10; n++) if (r["jechulSahang" + n]) docs.push(String(r["jechulSahang" + n]).slice(0, 120));
            // fileNm1~10, bigo, sincheongStatus 는 학생 본인의 제출·신청 정보라서 읽지 않는다
            x.detail = { office: r.jeopsuNm || "", text: s.text.slice(0, 5000), imgs: s.imgs, docs: docs,
              files: [r.fileNm].filter(Boolean).slice(0, 1), applyUrl: /^https:\/\//.test(r.sincheongUrl || "") ? r.sincheongUrl : "", period: r.mojipGigan || "" };
          } catch (e) { /* 상세 실패는 건너뜀 */ }
        }
        say("공고 내용 읽는 중… " + (70 + Math.round(j / Math.max(1, list.length) * 30)) + "%");
        if (j < list.length) return setTimeout(stepDet, 250);
        if (!list.length) return fail("LOGIN"); // 아무것도 못 읽었으면 저장된 자료를 덮어쓰지 않는다
        try { B.done(JSON.stringify({ collectedAt: new Date().toISOString(), records: list })); } catch (e) {}
      }
      stepDet();
    }
    say("장학캘린더 읽는 중…");
    stepDays();
  }
  function fail(t) { window.__hyinRunning = false; try { B.fail(t); } catch (e) {} }
  start();
})();
