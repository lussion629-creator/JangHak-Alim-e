import UIKit
import WebKit
import UserNotifications

/// 웹앱(www)을 jangak://app/ 주소로 띄운다. 외부 링크는 Safari 로 연다.
/// 페이지에는 안드로이드 앱과 같은 이름의 window.AndroidBridge 를 넣어, 같은 웹앱이 두 앱에서 그대로 동작하게 한다.
final class MainViewController: UIViewController, WKNavigationDelegate, WKUIDelegate {
    static let scheme = "jangak"
    private var web: WKWebView!
    private var silent: PortalClient?
    private var dark = false

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    override func loadView() {
        let cfg = WKWebViewConfiguration()
        cfg.setURLSchemeHandler(AssetHandler(), forURLScheme: MainViewController.scheme)
        cfg.websiteDataStore = .default()
        let ucc = WKUserContentController()
        ucc.addUserScript(WKUserScript(source: MainViewController.bridgeJS, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        cfg.userContentController = ucc
        web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.scrollView.contentInsetAdjustmentBehavior = .automatic
        let root = UIView()
        root.backgroundColor = UIColor(red: 0.05, green: 0.36, blue: 0.43, alpha: 1)
        web.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(web)
        NSLayoutConstraint.activate([
            web.topAnchor.constraint(equalTo: root.safeAreaLayoutGuide.topAnchor),
            web.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: root.trailingAnchor),
        ])
        view = root
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        web.load(URLRequest(url: URL(string: "\(MainViewController.scheme)://app/index.html")!))
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
        NotificationCenter.default.addObserver(self, selector: #selector(foreground), name: UIApplication.didBecomeActiveNotification, object: nil)
    }

    @objc private func foreground() {
        silentSync()
        Background.schedule()
    }

    override func traitCollectionDidChange(_ previous: UITraitCollection?) {
        super.traitCollectionDidChange(previous)
        web.evaluateJavaScript("window.__sysTheme&&window.__sysTheme()")
    }

    // MARK: - 바깥 링크는 Safari 로
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let u = action.request.url else { return decisionHandler(.cancel) }
        if u.scheme == MainViewController.scheme && u.host == "app" { return decisionHandler(.allow) }
        if u.scheme == "about" || u.scheme == "blob" || u.scheme == "data" { return decisionHandler(.allow) }
        if u.scheme == "http" || u.scheme == "https" || u.scheme == "mailto" || u.scheme == "tel" { UIApplication.shared.open(u) }
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let u = action.request.url, u.scheme == "http" || u.scheme == "https" { UIApplication.shared.open(u) }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "확인", style: .default) { _ in completionHandler() })
        topMost.present(a, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "취소", style: .cancel) { _ in completionHandler(false) })
        a.addAction(UIAlertAction(title: "확인", style: .default) { _ in completionHandler(true) })
        topMost.present(a, animated: true)
    }

    // MARK: - 페이지 ↔ 앱 다리 (prompt 로 동기 호출)
    static let bridgeJS = """
    (function(){
      function call(m,a){ try{ var r=window.prompt('__jangak_bridge__',JSON.stringify({m:m,a:a})); return r===null?undefined:JSON.parse(r); }catch(e){ return undefined; } }
      var names=['platform','isDark','setDark','notifyDeadlines','fetchHanyang','markWorkSeen','setAlerts','openPortal','hyinData','hyinState','hyinClear',
        'autoLoginSetup','autoLoginState','autoLoginOff','portalOpen','portalData','portalState','portalClear','portalLoginSetup','portalLoginState','portalLoginOff'];
      var b={}; names.forEach(function(n){ b[n]=function(){ return call(n,Array.prototype.slice.call(arguments)); }; });
      Object.defineProperty(window,'AndroidBridge',{value:Object.freeze(b),writable:false,configurable:false});
    })();
    """

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        guard prompt == "__jangak_bridge__" else {
            let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
            a.addTextField { $0.text = defaultText }
            a.addAction(UIAlertAction(title: "취소", style: .cancel) { _ in completionHandler(nil) })
            a.addAction(UIAlertAction(title: "확인", style: .default) { _ in completionHandler(a.textFields?.first?.text) })
            return topMost.present(a, animated: true)
        }
        // 앱 자신의 페이지(jangak://app)에서 온 호출만 받는다
        guard frame.isMainFrame, frame.securityOrigin.protocol == MainViewController.scheme, frame.securityOrigin.host == "app",
              let t = defaultText, let o = try? JSONSerialization.jsonObject(with: Data(t.utf8)) as? [String: Any],
              let m = o["m"] as? String else { return completionHandler("null") }
        let a = o["a"] as? [Any] ?? []
        let r = handle(m, a)
        if let r = r, let d = try? JSONSerialization.data(withJSONObject: [r]), let s = String(data: d, encoding: .utf8) {
            completionHandler(String(s.dropFirst().dropLast()))
        } else { completionHandler("null") }
    }

    private func str(_ a: [Any], _ i: Int) -> String { i < a.count ? (a[i] as? String ?? "") : "" }

    private func handle(_ m: String, _ a: [Any]) -> Any? {
        switch m {
        case "platform": return "ios"
        case "isDark": return traitCollection.userInterfaceStyle == .dark
        case "setDark":
            dark = (a.first as? Bool) ?? false
            view.backgroundColor = dark ? UIColor(red: 0.055, green: 0.07, blue: 0.086, alpha: 1) : UIColor(red: 0.05, green: 0.36, blue: 0.43, alpha: 1)
            return nil
        case "notifyDeadlines": Notify.deadlines(str(a, 0)); return nil
        case "fetchHanyang":
            let url = str(a, 0), cb = str(a, 1)
            guard HyWork.allowed(url), cb.range(of: "^[A-Za-z0-9_]{1,40}$", options: .regularExpression) != nil else { return nil }
            HyWork.fetch(url) { [weak self] body in
                let arg: String
                if let body = body, let d = try? JSONSerialization.data(withJSONObject: [body]), let s = String(data: d, encoding: .utf8) { arg = String(s.dropFirst().dropLast()) } else { arg = "null" }
                self?.web.evaluateJavaScript("window.__hyCb&&window.__hyCb('\(cb)',\(arg))")
            }
            return nil
        case "markWorkSeen":
            if let d = str(a, 0).data(using: .utf8), let ids = try? JSONSerialization.jsonObject(with: d) as? [String] { HyWork.markSeen(ids) }
            return nil
        case "setAlerts":
            let j = str(a, 0)
            guard (try? JSONSerialization.jsonObject(with: Data(j.utf8))) != nil else { return nil }
            Alerts.save(j)
            Alerts.check(fetchRemote: true) { }
            return nil
        case "openPortal": openPortal("hyin"); return nil
        case "portalOpen": openPortal(str(a, 0)); return nil
        case "hyinData": return portalData("hyin")
        case "portalData": return portalData(str(a, 0))
        case "hyinState": return Portal.hyin.state
        case "portalState": return Portal.of(str(a, 0))?.state ?? ""
        case "hyinClear": portalClear("hyin"); return nil
        case "portalClear": portalClear(str(a, 0)); return nil
        case "autoLoginSetup": loginSetup("hyin"); return nil
        case "portalLoginSetup": loginSetup(str(a, 0)); return nil
        case "autoLoginState": return Cred.state("hyin")
        case "portalLoginState": return Portal.of(str(a, 0)).map { Cred.state($0.key) } ?? "off"
        case "autoLoginOff": Cred.clear("hyin"); return nil
        case "portalLoginOff": if let p = Portal.of(str(a, 0)) { Cred.clear(p.key) }; return nil
        default: return nil
        }
    }

    private func portalData(_ key: String) -> String {
        guard let p = Portal.of(key), let d = try? Data(contentsOf: p.file), d.count < 6_000_000 else { return "" }
        return String(data: d, encoding: .utf8) ?? ""
    }

    private func updated(_ p: Portal) {
        web.evaluateJavaScript(p.key == "hyin" ? "window.__hyinUpdated&&window.__hyinUpdated()" : "window.__portalUpdated&&window.__portalUpdated('\(p.key)')")
    }

    func openPortal(_ key: String) {
        guard let p = Portal.of(key) else { return }
        let vc = PortalViewController(portal: p)
        vc.onClose = { [weak self] r in if r == "ok" { self?.updated(p) } }
        topMost.present(vc, animated: true)
    }

    private func portalClear(_ key: String) {
        guard let p = Portal.of(key) else { return }
        try? FileManager.default.removeItem(at: p.file)
        p.state = ""
        // 그 포털 주소의 쿠키만 지운다
        let store = WKWebsiteDataStore.default().httpCookieStore
        store.getAllCookies { cookies in
            for c in cookies where p.schoolHost(c.domain.hasPrefix(".") ? String(c.domain.dropFirst()) : c.domain) { store.delete(c) }
        }
    }

    private func loginSetup(_ key: String) {
        guard let p = Portal.of(key) else { return }
        let a = UIAlertController(title: "\(p.name) 자동 로그인",
                                  message: "아이디·비밀번호는 이 아이폰의 키체인에 암호화해 두고 \(p.name) 로그인 칸에만 넣습니다. 서버로 보내지 않습니다. 로그인이 한 번 실패하면 계정이 잠기지 않도록 자동 로그인을 멈춥니다.",
                                  preferredStyle: .alert)
        a.addTextField { $0.placeholder = p.key == "hyin" ? "포털 아이디" : "학번"; $0.autocorrectionType = .no; $0.autocapitalizationType = .none; $0.textContentType = .username }
        a.addTextField { $0.placeholder = "비밀번호"; $0.isSecureTextEntry = true; $0.textContentType = .password }
        a.addAction(UIAlertAction(title: "취소", style: .cancel))
        a.addAction(UIAlertAction(title: "저장", style: .default) { [weak self] _ in
            let id = a.textFields?[0].text?.trimmingCharacters(in: .whitespaces) ?? "", pw = a.textFields?[1].text ?? ""
            guard !id.isEmpty, !pw.isEmpty, Cred.save(p.key, id: id, pw: pw) else { return }
            a.textFields?[1].text = ""
            self?.updated(p)
            UserDefaults.standard.set(0, forKey: "portal.force.\(p.key)")
            self?.silentSync(force: p.key)
        })
        topMost.present(a, animated: true)
    }

    // MARK: - 하루 한 번 조용히 포털 다시 읽기 (필요하면 저장된 아이디로 자동 로그인)
    func silentSync(force: String? = nil) {
        guard silent == nil else { return }
        for p in Portal.all {
            let has = FileManager.default.fileExists(atPath: p.file.path) || Cred.state(p.key) == "on"
            guard has else { continue }
            if force != p.key, let at = p.savedAt, Date().timeIntervalSince(at) < 20 * 3600 { continue }
            p.state = "checking"
            let c = PortalClient(portal: p, silent: true, frame: CGRect(x: 0, y: 0, width: 1, height: 1))
            c.web.alpha = 0
            view.insertSubview(c.web, at: 0)
            silent = c
            c.onFinish = { [weak self, weak c] r in
                c?.stop(); c?.web.removeFromSuperview()
                self?.silent = nil
                if r == "ok" { self?.updated(p) }
                if r == "login" && Cred.state(p.key) == "failed" { Notify.loginStopped(p) }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { self?.silentSync() }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 120) { [weak self, weak c] in
                guard let c = c, self?.silent === c else { return }
                c.stop(); c.web.removeFromSuperview(); self?.silent = nil; p.state = "login"
            }
            c.start()
            return
        }
    }
}

/// 앱에 들어 있는 웹앱 파일(www)을 jangak://app/ 주소로 내준다.
final class AssetHandler: NSObject, WKURLSchemeHandler {
    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url, url.host == "app" else { return task.didFailWithError(URLError(.badURL)) }
        var path = url.path
        if path.isEmpty || path == "/" { path = "/index.html" }
        guard !path.contains(".."), let root = Bundle.main.url(forResource: "www", withExtension: nil) else {
            return task.didFailWithError(URLError(.noPermissionsToReadFile))
        }
        let file = root.appendingPathComponent(String(path.dropFirst()))
        guard let data = try? Data(contentsOf: file) else {
            let r = HTTPURLResponse(url: url, statusCode: 404, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "text/plain"])!
            task.didReceive(r); task.didReceive(Data("Not Found".utf8)); return task.didFinish()
        }
        let r = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                headerFields: ["Content-Type": AssetHandler.mime(path), "Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"])!
        task.didReceive(r)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) { }

    static func mime(_ p: String) -> String {
        if p.hasSuffix(".html") { return "text/html; charset=utf-8" }
        if p.hasSuffix(".json") { return "application/json" }
        if p.hasSuffix(".js") { return "application/javascript" }
        if p.hasSuffix(".css") { return "text/css" }
        if p.hasSuffix(".svg") { return "image/svg+xml" }
        if p.hasSuffix(".png") { return "image/png" }
        if p.hasSuffix(".woff2") { return "font/woff2" }
        if p.hasSuffix(".webmanifest") { return "application/manifest+json" }
        return "application/octet-stream"
    }
}
