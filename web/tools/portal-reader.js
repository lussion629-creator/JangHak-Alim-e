// 학교 포털(강원대 K-Cloud, 서강대 SAINT) 장학 신청 목록 읽기 — 휴대폰 앱이 로그인된 포털 화면에 넣어 실행한다.
// 앱이 window.__portalCfg = {menus: [[메뉴 이름…], …], host: "학교 주소 끝", hint: "안내 문구"} 를 먼저 넣는다.
// 학생이 로그인한 화면에 보이는 '장학 신청' 목록 표에서 장학명·구분·신청 기간 같은 공개 항목만 읽는다.
// 신청 여부·결과·지급액·개인 정보 칸은 읽지 않는다. 결과는 PortalBridge.done(JSON)으로 앱에만 넘긴다.
(function () {
  "use strict";
  var B = window.PortalBridge;
  if (!B || window.__portalReaderRunning) return;
  window.__portalReaderRunning = true;
  var SILENT = !!window.__portalSilent;
  var SUB = window.top !== window; // 앱이 화면 속 작은 창(iframe)에도 넣은 경우: 표만 찾고, 메뉴 누르기·실패 알림은 바깥 창이 한다
  var CFG = window.__portalCfg || {};
  var MENUS = CFG.menus || [];
  var HOST = new RegExp((CFG.host || "kangwon.ac.kr").replace(/\./g, "\\.") + "$");
  // 본인 기록일 수 있는 칸(신청 상태·결과·성적·학과·연락처 등)은 읽지 않는다
  var HEAD_NO = /상태|결과|신청일|지급|금액|학번|성명|이름|계좌|은행|연락|전화|주소|생년|소득|점수|순위|승인|선발\s*여부|신청\s*여부|수혜|환수|선택|체크|성적|평점|학점|학과|전공|소속|비고|메모|사유|첨부/;
  var HEAD_OK = /장학|구분|유형|기간|시작|종료|마감|대상|년도|접수|안내/;
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var txt = function (e) { return ((e && (e.innerText || e.textContent)) || "").replace(/\s+/g, " ").trim(); };
  var shown = function (e) { return !!(e && (e.offsetParent !== null || (e.getClientRects && e.getClientRects().length))); };

  function docs() {
    var out = [document];
    (function walk(d) {
      var fs = d.querySelectorAll("iframe,frame");
      for (var i = 0; i < fs.length; i++) {
        try { var cd = fs[i].contentDocument; if (cd && cd.location && HOST.test(cd.location.hostname)) { out.push(cd); walk(cd); } } catch (e) { }
      }
    })(document);
    return out;
  }

  function clickText(t) {
    var ds = docs();
    for (var pass = 0; pass < 2; pass++) {
      for (var k = 0; k < ds.length; k++) {
        var els = ds[k].querySelectorAll("a,span,li,div,button,p,td");
        for (var i = 0; i < els.length; i++) {
          var e = els[i], x = txt(e);
          // 1차: 글자가 똑같은 메뉴, 2차: 띄어쓰기만 다른 메뉴
          if (e.children.length <= 2 && shown(e) && (pass === 0 ? x === t : x.replace(/\s/g, "") === t.replace(/\s/g, ""))) { e.click(); return true; }
        }
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
        var rows = Array.prototype.filter.call(c.querySelectorAll("tr"), function (tr) { return shown(tr) && tr.querySelectorAll("td").length >= 2 && !tr.querySelector("th"); })
          .map(function (tr) { return Array.prototype.map.call(tr.querySelectorAll("td"), txt); });
        if (!ths.length && rows.length > 1) {
          // 머리글을 th 없이 첫 줄 칸으로 그리는 표 (SAP 화면 등)
          var f = rows[0].join(" ");
          if (/장학/.test(f) && /기간|시작|종료|마감|접수/.test(f) && !/20\d\d/.test(f)) { ths = rows[0]; rows = rows.slice(1); }
        }
        if (!ths.length) continue;
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
    return CFG.generic ? generic() : null;
  }

  // 학생이 고른 학교 포털: 표 머리글이 정해져 있지 않으므로, 화면의 표 줄·목록 줄 가운데 '장학'이 들어간 줄을 공고로 읽는다.
  // 수혜 내역·지급액처럼 본인 기록인 표(머리글에 지급·수혜·계좌·학번 등)는 통째로 건너뛴다.
  var MINE = /지급|수혜|환수|계좌|은행|학번|성명|생년|연락처|전화|주소|성적|평점|선발\s*결과|신청\s*결과|승인/;
  var MINE_ROW = /계좌|학번|생년월일|연락처|전화번호|주민등록|수혜\s*내역|지급\s*내역/;
  var NAV = /^(장학|장학금|장학안내|장학공지|장학제도|장학신청|교내장학|교외장학|국가장학|장학금 신청|장학금 안내)$/;
  function dates(t) {
    // 2026.10.14 / 2026-10-14 / 26.10.14 (두 자리 해는 20~40 이고 띄어쓰기 없을 때만)
    var m = String(t).match(/20\d{2}\s*[.\-\/년]\s*\d{1,2}\s*[.\-\/월]\s*\d{1,2}|\b[2-4]\d[.\-\/]\d{1,2}[.\-\/]\d{1,2}\b/g) || [];
    return m.map(function (x) { return date(/^20\d{2}/.test(x) ? x : "20" + x); }).filter(Boolean);
  }
  function generic() {
    var out = [], seen = {}, ds = docs();
    for (var k = 0; k < ds.length; k++) {
      var d = ds[k];
      var rows = Array.prototype.slice.call(d.querySelectorAll("tr")).concat(Array.prototype.slice.call(d.querySelectorAll("li,[class*='list'] > *,[class*='item'],[class*='row']")));
      for (var i = 0; i < rows.length && out.length < 200; i++) {
        var r = rows[i];
        if (!shown(r)) continue;
        var tb = r.closest && r.closest("table");
        if (tb) { var hd = Array.prototype.map.call(tb.querySelectorAll("th"), txt).join(" "); if (MINE.test(hd)) continue; }
        if (r.tagName !== "TR" && r.querySelector("tr,li")) continue; // 목록을 감싼 큰 칸은 건너뛴다
        var full = txt(r);
        if (full.length < 4 || full.length > 400 || !/장학/.test(full) || MINE_ROW.test(full)) continue;
        var a = r.querySelector("a"), name = a ? txt(a) : "";
        if (r.tagName !== "TR" && (!a || name.length < 8)) continue; // 표가 아닌 목록은 제목 링크가 있는 줄만 (분류·작성자 줄 제외)
        if (!name || name.length < 4) {
          var cells = r.tagName === "TR" ? Array.prototype.map.call(r.querySelectorAll("td"), txt) : [full];
          name = cells.filter(function (c) { return /장학/.test(c); }).sort(function (x, y) { return y.length - x.length; })[0] || "";
        }
        name = name.replace(/\s*(new|N|새글)$/i, "").slice(0, 120);
        if (name.length < 8 || NAV.test(name) || seen[name]) continue; // 짧은 글자는 메뉴·분류 이름
        seen[name] = 1;
        var dt = dates(full).filter(function (x, j, arr) { return arr.indexOf(x) === j; });
        var rg = full.match(/(20\d{2}\s*[.\-\/년]\s*\d{1,2}\s*[.\-\/월]\s*\d{1,2})[^~～]{0,12}[~～][^0-9]{0,4}(20\d{2}\s*[.\-\/년]\s*\d{1,2}\s*[.\-\/월]\s*\d{1,2})/);
        var s0 = "", e0 = "", p0 = "";
        if (rg) { s0 = date(rg[1]); e0 = date(rg[2]); } else if (dt.length >= 2) { var so = dt.slice().sort(); s0 = so[0]; e0 = so[so.length - 1]; } else if (dt.length === 1) p0 = dt[0];
        if (!e0 && p0) { // 제목의 '(10. 14.(수) ~ 10. 22.(목))'처럼 해가 없는 기간은 게시일의 해로 채운다
          var md = name.match(/(?:(\d{1,2})\s*[.\/월]\s*(\d{1,2})[^~～]{0,14})?[~～]\s*(\d{1,2})\s*[.\/월]\s*(\d{1,2})/);
          if (md) {
            var y0 = +p0.slice(0, 4), pm = +p0.slice(5, 7);
            var mk = function (mm, dd) { var y = y0 + (+mm < pm - 6 ? 1 : 0); return y + "-" + ("0" + mm).slice(-2) + "-" + ("0" + dd).slice(-2); };
            e0 = mk(md[3], md[4]); if (md[1]) s0 = mk(md[1], md[2]);
          }
        }
        var href = a && a.href && /^https:/.test(a.href) ? a.href : "";
        out.push({ key: name.slice(0, 120), name: name, kind: "", start: s0, end: e0, posted: p0, href: href.slice(0, 300), cols: {} });
      }
    }
    return out.length ? out : null;
  }

  async function run() {
    if (SUB) {
      for (var q = 0; q < 300; q++) { var rr = scrape(); if (rr) { B.done(JSON.stringify({ records: rr })); return; } await sleep(2000); }
      return;
    }
    if (window.__portalNow) { // '이 화면 저장'을 눌렀을 때: 지금 화면만 읽는다
      for (var z = 0; z < 5; z++) { var rz = scrape(); if (rz) { B.done(JSON.stringify({ records: rz })); return; } await sleep(2000); }
      B.fail("EMPTY"); return;
    }
    B.progress("로그인 확인됨 · 장학 신청 화면을 찾는 중…");
    // 메뉴를 차례로 눌러 '장학신청' 화면으로 간다 (못 찾으면 학생이 직접 열 때까지 기다린다)
    for (var w = 0; w < MENUS.length && !scrape(); w++) {
      var path = MENUS[w];
      for (var i = 0; i < path.length; i++) { if (clickText(path[i])) await sleep(2000); }
      await sleep(2000);
    }
    var limit = SILENT ? 15 : 300; // 앱 화면에서는 학생이 직접 메뉴를 열 수 있도록 10분까지 기다린다
    for (var t = 0; t < limit; t++) {
      var recs = scrape();
      if (recs) { B.done(JSON.stringify({ records: recs })); return; }
      if (t === 3 && !SILENT) B.progress(CFG.hint || "장학 신청 화면을 열어 주세요.");
      await sleep(2000);
    }
    B.fail("NOTFOUND");
  }
  run().catch(function (e) { B.fail(String(e && e.message || e).slice(0, 100)); });
})();
