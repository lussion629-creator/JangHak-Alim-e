// 장학알리미 웹앱(아이폰 홈 화면 앱 포함) 오프라인 저장. 같은 주소의 파일만 다루고, 다른 사이트 요청은 건드리지 않는다.
const V = "jangak-v2";
const SHELL = ["./", "index.html", "app.js", "manifest.webmanifest", "icon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "fonts/pretendard.woff2"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const fresh = req.mode === "navigate" || /\/(index\.html|app\.js|sw\.js)?$/.test(url.pathname) || url.pathname.includes("/data/");
  if (fresh) {
    // 화면·자료는 새것을 먼저, 안 되면 저장해 둔 것
    e.respondWith(fetch(req).then(r => {
      if (r.ok) { const c = r.clone(); caches.open(V).then(cc => cc.put(req, c)); }
      return r;
    }).catch(() => caches.match(req).then(m => m || caches.match("index.html"))));
  } else {
    // 글꼴·아이콘은 저장해 둔 것을 먼저
    e.respondWith(caches.match(req).then(m => m || fetch(req).then(r => {
      if (r.ok) { const c = r.clone(); caches.open(V).then(cc => cc.put(req, c)); }
      return r;
    })));
  }
});
