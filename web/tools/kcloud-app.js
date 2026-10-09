// 강원대 K-Cloud(kcloud.kangwon.ac.kr) 장학 신청 목록 읽기 — 휴대폰 앱이 로그인된 K-Cloud 화면에 넣어 실행한다.
// 학생이 로그인한 화면에 보이는 '장학 신청' 목록 표에서 장학명·구분·신청 기간 같은 공개 항목만 읽는다.
// 신청 여부·결과·지급액·개인 정보 칸은 읽지 않는다. 결과는 PortalBridge.done(JSON)으로 앱에만 넘긴다.
(function () {
  "use strict";
  var B = window.PortalBridge;
  if (!B || window.__kcloudRunning) return;
  window.__kcloudRunning = true;
  var SILENT = !!window.__portalSilent;
  var MENU = ["학부생서비스", "교과", "장학", "장학신청"];
  var HEAD_NO = /상태|결과|신청일|지급|금액|학번|성명|이름|계좌|은행|연락|전화|주소|생년|소득|점수|순위|승인|선발\s*여부|신청\s*여부|수혜|환수|선택|체크/;
  var HEAD_OK = /장학|구분|유형|기간|시작|종료|마감|대상|학년|학기|년도|비고|접수|안내/;
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var txt = function (e) { return ((e && (e.innerText || e.textContent)) || "").replace(/\s+/g, " ").trim(); };
  var shown = function (e) { return !!(e && (e.offsetParent !== null || (e.getClientRects && e.getClientRects().length))); };

  function docs() {
    var out = [document];
    (function walk(d) {
      var fs = d.querySelectorAll("iframe,frame");
      for (var i = 0; i < fs.length; i++) {
        try { var cd = fs[i].contentDocument; if (cd && cd.location && /kangwon\.ac\.kr$/.test(cd.location.hostname)) { out.push(cd); walk(cd); } } catch (e) { }
      }
    })(document);
    return out;
  }

  function clickText(t) {
    var ds = docs();
    for (var k = 0; k < ds.length; k++) {
      var els = ds[k].querySelectorAll("a,span,li,div,button,p,td");
      for (var i = 0; i < els.length; i++) {
        var e = els[i];
        if (e.children.length <= 2 && txt(e) === t && shown(e)) { e.click(); return true; }
      }
    }
    return false;
  }

  function date(s) {
    var m = String(s || "").match(/(20\d{2})\s*[.\-\/년]\s*(\d{1,2})\s*[.\-\/월]\s*(\d{1,2})/);
    return m ? m[1] + "-" + ("0" + m[2]).slice(-2) + "-" + ("0" + m[3]).slice(-2) : "";
  }

  // 표(일반 table 또는 WebSquare 그리드)에서 머리글과 줄을 읽는다
  function grids() {
    var out = [], ds = docs();
    for (var k = 0; k < ds.length; k++) {
      var cs = ds[k].querySelectorAll("[class*='w2grid'],table");
      for (var i = 0; i < cs.length; i++) {
        var c = cs[i];
        if (c.tagName === "TABLE" && c.closest && c.closest("[class*='w2grid']")) continue; // 그리드 안의 표는 그리드 단위로 본다
        var ths = Array.prototype.filter.call(c.querySelectorAll("th"), shown).map(txt);
        if (!ths.length) continue;
        var rows = Array.prototype.filter.call(c.querySelectorAll("tr"), function (tr) { return shown(tr) && tr.querySelectorAll("td").length >= 2 && !tr.querySelector("th"); })
          .map(function (tr) { return Array.prototype.map.call(tr.querySelectorAll("td"), txt); });
        // 머리글이 여러 줄이면 줄 칸 수와 같은 마지막 묶음을 쓴다
        if (rows.length) { var n = rows[0].length; if (ths.length > n) ths = ths.slice(ths.length - n); }
        out.push({ heads: ths, rows: rows });
      }
    }
    return out;
  }

  function scrape() {
    var gs = grids();
    for (var g = 0; g < gs.length; g++) {
      var h = gs[g].heads, rows = gs[g].rows;
      var hs = h.join(" ");
      if (!/장학/.test(hs) || !/기간|시작|종료|마감|접수/.test(hs) || !rows.length) continue;
      var iName = -1, iPer = -1, iS = -1, iE = -1, iKind = -1;
      h.forEach(function (x, i) {
        if (iName < 0 && /장학(금)?\s*(명|이름)|장학금$|^장학$|장학\s*구분\s*명|명칭/.test(x)) iName = i;
        if (iPer < 0 && /(신청|접수)?\s*기간/.test(x) && !/시작|종료/.test(x)) iPer = i;
        if (iS < 0 && /시작/.test(x)) iS = i;
        if (iE < 0 && /종료|마감/.test(x)) iE = i;
        if (iKind < 0 && /구분|유형/.test(x) && i !== iName) iKind = i;
      });
      if (iName < 0) h.forEach(function (x, i) { if (iName < 0 && /장학/.test(x) && !HEAD_NO.test(x)) iName = i; });
      if (iName < 0) continue;
      var recs = [];
      rows.forEach(function (r) {
        if (r.length !== h.length) return;
        var name = r[iName]; if (!name || name.length < 2) return;
        var start = "", end = "";
        if (iPer >= 0) { var ds2 = (r[iPer].match(/20\d{2}\s*[.\-\/년]\s*\d{1,2}\s*[.\-\/월]\s*\d{1,2}/g) || []); start = date(ds2[0]); end = date(ds2[1] || ""); }
        if (iS >= 0) start = date(r[iS]) || start;
        if (iE >= 0) end = date(r[iE]) || end;
        var cols = {};
        h.forEach(function (x, i) { if (i !== iName && x && HEAD_OK.test(x) && !HEAD_NO.test(x) && r[i]) cols[x.slice(0, 20)] = r[i].slice(0, 120); });
        recs.push({ key: (name + "|" + start + "|" + end).slice(0, 120), name: name.slice(0, 100), kind: iKind >= 0 ? r[iKind].slice(0, 30) : "", start: start, end: end, cols: cols });
      });
      if (recs.length) return recs;
    }
    return null;
  }

  async function run() {
    B.progress("로그인 확인됨 · 장학 신청 화면을 찾는 중…");
    // 메뉴를 차례로 눌러 '장학신청' 화면으로 간다 (못 찾으면 학생이 직접 열 때까지 기다린다)
    for (var w = 0; w < 3 && !scrape(); w++) {
      for (var i = 0; i < MENU.length; i++) { if (clickText(MENU[i])) await sleep(1500); }
      await sleep(1500);
      if (scrape()) break;
    }
    var limit = SILENT ? 15 : 300; // 앱 화면에서는 학생이 직접 메뉴를 열 수 있도록 10분까지 기다린다
    for (var t = 0; t < limit; t++) {
      var recs = scrape();
      if (recs) { B.done(JSON.stringify({ records: recs })); return; }
      if (t === 3 && !SILENT) B.progress("장학 신청 화면을 열어 주세요: 학부생서비스 → 교과 → 장학 → 장학신청");
      await sleep(2000);
    }
    B.fail("NOTFOUND");
  }
  run().catch(function (e) { B.fail(String(e && e.message || e).slice(0, 100)); });
})();
