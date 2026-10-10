import UIKit
import WebKit

/// 앱이 읽을 수 있는 학교 포털 (hyin = 한양 포털 장학캘린더, kcloud = 강원대 K-Cloud 장학 신청 목록).
struct Portal {
    let key: String
    let name: String
    let start: URL
    let mainHost: String
    let script: String   // www/tools 아래 읽기 스크립트
    let fileName: String

    static let hyin = Portal(key: "hyin", name: "한양 포털", start: URL(string: "https://portal.hanyang.ac.kr/port.do")!,
                             mainHost: "portal.hanyang.ac.kr", script: "hyin-app", fileName: "hyin_calendar.json")
    static let kcloud = Portal(key: "kcloud", name: "강원대 K-Cloud", start: URL(string: "https://kcloud.kangwon.ac.kr/")!,
                               mainHost: "kcloud.kangwon.ac.kr", script: "portal-reader", fileName: "kcloud_scholarship.json")
    static let saint = Portal(key: "saint", name: "서강대 SAINT", start: URL(string: "https://saint.sogang.ac.kr/irj/portal")!,
                              mainHost: "saint.sogang.ac.kr", script: "portal-reader", fileName: "saint_scholarship.json")
    static let all = [hyin, kcloud, saint]
    static let desktopUA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

    /// 읽기 스크립트 설정 (메뉴 이름·학교 주소·안내 문구)
    var cfg: String {
        switch key {
        case "kcloud": return "window.__portalCfg={host:'kangwon.ac.kr',menus:[['학부생서비스','교과','장학','장학신청']],hint:'장학 신청 화면을 열어 주세요: 학부생서비스 → 교과 → 장학 → 장학신청'};"
        case "saint": return "window.__portalCfg={host:'sogang.ac.kr',menus:[['학사정보','장학','장학금신청'],['학사정보','장학','장학신청'],['학사정보','장학금','장학금 신청']],hint:'장학금 신청 화면을 열어 주세요 (학사정보 → 장학). 그 화면의 목록을 읽어 와요.'};"
        default: return ""
        }
    }

    /// 모바일 브라우저를 막는 포털(SAINT)은 PC 화면으로 연다
    var desktop: Bool { key == "saint" }

    /// 주소만으로 로그인 화면인지 알 수 없는 포털은 화면에 로그인 칸이 있는지 본다
    var loginProbe: String? {
        key == "saint" ? "(document.getElementById('logonForm')||document.getElementById('login_id'))?'login':'in'" : nil
    }
    static func of(_ key: String?) -> Portal? { all.first { $0.key == key } }

    /// 포털 화면으로 이어지는 학교 주소인지 (다른 주소로는 가지 않는다)
    func schoolHost(_ h: String?) -> Bool {
        guard let h = h else { return false }
        let base = key == "hyin" ? "hanyang.ac.kr" : key == "saint" ? "sogang.ac.kr" : "kangwon.ac.kr"
        return h == base || h.hasSuffix("." + base)
    }

    func isLogin(_ url: String) -> Bool {
        if key == "hyin" { return url.contains("lgin") || url.contains("/sso/") || url.contains("login") }
        if key == "saint" { return url.contains("logon") || url.contains("login") }
        return url.contains("/login") || url.contains("ssoLogin") || url.contains("ssm01008") || url.contains("cert_install")
            || url.contains("notice_before_login") || url.hasSuffix("kangwon.ac.kr/")
    }

    var file: URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent(fileName)
    }

    var state: String {
        get { UserDefaults.standard.string(forKey: "portal.state.\(key)") ?? "" }
        nonmutating set { UserDefaults.standard.set(newValue, forKey: "portal.state.\(key)") }
    }

    var savedAt: Date? { (try? FileManager.default.attributesOfItem(atPath: file.path))?[.modificationDate] as? Date }

    /// 로그인 칸에 저장된 아이디·비밀번호를 넣고 로그인 버튼을 누른다 (포털 자체 로그인 절차를 그대로 쓴다).
    func loginScript(id: String, pw: String) -> String {
        func q(_ s: String) -> String {
            let d = (try? JSONSerialization.data(withJSONObject: [s])) ?? Data("[\"\"]".utf8)
            return String(String(data: d, encoding: .utf8)!.dropFirst().dropLast())
        }
        let setter = "var d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');"
            + "function s(e,v){d.set.call(e,v);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}"
        if key == "hyin" {
            return "(function(){var u=document.getElementById('userId'),p=document.getElementById('password');if(!u||!p)return;" + setter
                + "s(u,\(q(id)));s(p,\(q(pw)));"
                + "var a=Array.prototype.filter.call(document.querySelectorAll('a,button'),function(e){return (e.textContent||'').trim()==='로그인'&&e.offsetParent!==null;})[0];"
                + "if(a)a.click();})();"
        }
        if key == "saint" {
            return "(function(){var u=document.getElementById('login_id'),p=document.getElementById('login_pw');if(!u||!p)return;window.alert=function(){};" + setter
                + "s(u,\(q(id)));s(p,\(q(pw)));if(typeof btnLogin==='function'){btnLogin();}else{var b=document.querySelector('.form_login_btn');if(b)b.click();}})();"
        }
        return "(function(){var u=document.getElementById('NORMAL_ID'),p=document.getElementById('NORMAL_PWD'),b=document.getElementById('btn_Login');if(!u||!p||!b)return;"
            + "window.alert=function(){};" + setter + "s(u,\(q(id)));s(p,\(q(pw)));b.click();})();"
    }
}

/// 학생이 로그인한 포털 화면에서 장학 정보를 읽어 이 기기에만 저장한다. 비밀번호·입력칸·본인 신청 내역은 읽지 않는다.
final class PortalClient: NSObject, WKNavigationDelegate, WKScriptMessageHandler, WKUIDelegate {
    let portal: Portal
    let web: WKWebView
    let silent: Bool
    var onProgress: ((String) -> Void)?
    var onFinish: ((String) -> Void)?   // ok / login / fail / notfound
    private var finished = false
    private var triedLogin = false
    private var injected = false

    init(portal: Portal, silent: Bool, frame: CGRect = .zero) {
        self.portal = portal
        self.silent = silent
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()
        let ucc = WKUserContentController()
        cfg.userContentController = ucc
        web = WKWebView(frame: frame, configuration: cfg)
        if portal.desktop { web.customUserAgent = Portal.desktopUA }
        super.init()
        ucc.add(WeakHandler(self), name: "portal")
        web.navigationDelegate = self
        web.uiDelegate = self
    }

    func start() { web.load(URLRequest(url: portal.start)) }

    func stop() {
        finished = true
        web.stopLoading()
        web.configuration.userContentController.removeScriptMessageHandler(forName: "portal")
    }

    private func finish(_ result: String) {
        if finished { return }
        finished = true
        web.stopLoading()
        if result != "notfound" || portal.state != "notfound" { portal.state = result }
        onFinish?(result)
    }

    // 포털 밖 주소로는 이동하지 않는다. 2차 인증 앱 호출 같은 외부 주소는 앱 화면에서만 기기의 앱으로 연다.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let u = action.request.url else { return decisionHandler(.cancel) }
        if u.scheme == "https" && portal.schoolHost(u.host) { return decisionHandler(.allow) }
        if u.scheme == "about" { return decisionHandler(.allow) }
        if !silent && action.navigationType == .linkActivated || (!silent && u.scheme != "http" && u.scheme != "https") {
            UIApplication.shared.open(u)
        }
        decisionHandler(.cancel)
    }

    // 새 창(target=_blank)은 같은 화면에서 연다
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let u = action.request.url, u.scheme == "https", portal.schoolHost(u.host) { webView.load(URLRequest(url: u)) }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        if !silent, let vc = webView.window?.rootViewController?.topMost {
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "확인", style: .default) { _ in completionHandler() })
            vc.present(a, animated: true)
        } else { completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        if !silent, let vc = webView.window?.rootViewController?.topMost {
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "취소", style: .cancel) { _ in completionHandler(false) })
            a.addAction(UIAlertAction(title: "확인", style: .default) { _ in completionHandler(true) })
            vc.present(a, animated: true)
        } else { completionHandler(false) }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard !finished, let url = webView.url?.absoluteString, let host = webView.url?.host else { return }
        let main = host == portal.mainHost
        if main, let probe = portal.loginProbe {
            webView.evaluateJavaScript(probe) { [weak self] r, _ in
                guard let self = self, !self.finished else { return }
                self.route(webView, url: url, main: true, login: (r as? String) != "in")
            }
        } else {
            route(webView, url: url, main: main, login: portal.isLogin(url))
        }
    }

    private func route(_ webView: WKWebView, url: String, main: Bool, login: Bool) {
        if main && !login {
            if portal.key == "kcloud" && !url.contains("/websquare/") { return }  // 넘어가는 중인 중간 화면
            if portal.key == "saint" && !url.contains("/irj/") { return }
            onProgress?("로그인 확인됨 · 장학 정보를 불러오는 중…")
            inject()
        } else if silent && main && login && !triedLogin && Cred.state(portal.key) == "on" {
            // 저장된 아이디·비밀번호로 한 번만 로그인을 시도한다 (틀리면 계정이 잠기지 않도록 다시 시도하지 않음)
            triedLogin = true
            guard let c = Cred.load(portal.key) else { return finish("login") }
            onProgress?("자동 로그인 중…")
            webView.evaluateJavaScript(portal.loginScript(id: c.id, pw: c.pw))
            DispatchQueue.main.asyncAfter(deadline: .now() + 25) { [weak self] in
                guard let self = self, !self.finished, !self.injected else { return }
                Cred.setState(self.portal.key, "failed")
                self.finish("login")
            }
        } else if silent && triedLogin && main && login {
            // 자동 로그인 뒤 다음 단계로 넘어가는 중: 위의 시간 제한이 판단한다
        } else if silent {
            if triedLogin { Cred.setState(portal.key, "failed") }
            finish("login")
        } else {
            onProgress?("\(portal.name)에 로그인해 주세요. 비밀번호는 앱에 저장되지 않습니다.")
        }
    }

    private func inject() {
        guard let p = Bundle.main.url(forResource: portal.script, withExtension: "js", subdirectory: "www/tools"),
              let js = try? String(contentsOf: p, encoding: .utf8) else { return finish("fail") }
        let bridge = "window.HyinBridge=window.PortalBridge={progress:function(t){webkit.messageHandlers.portal.postMessage({m:'progress',a:String(t)})},"
            + "done:function(t){webkit.messageHandlers.portal.postMessage({m:'done',a:String(t)})},fail:function(t){webkit.messageHandlers.portal.postMessage({m:'fail',a:String(t)})}};"
        if portal.key == "saint" && !injected {
            // SAP 포털은 화면 내용을 다른 주소의 작은 창(iframe)에 띄우므로, 학교 주소의 작은 창에도 같은 읽기 스크립트를 넣는다
            let sub = "if(window.top!==window&&/sogang\\.ac\\.kr$/.test(location.hostname)){window.__portalSilent=\(silent);" + portal.cfg + bridge + "\n" + js + "}"
            web.configuration.userContentController.addUserScript(WKUserScript(source: sub, injectionTime: .atDocumentEnd, forMainFrameOnly: false))
        }
        injected = true
        web.evaluateJavaScript("window.__portalSilent=\(silent);window.__hyinKnown=\(knownKeys());" + portal.cfg + bridge + "\n" + js)
    }

    /// 전에 불러온 공고(본문 포함) 번호 — 이번에는 본문을 다시 읽지 않는다 (한양 포털)
    private func knownKeys() -> String {
        guard portal.key == "hyin", let d = try? Data(contentsOf: portal.file),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any], let rs = o["records"] as? [[String: Any]] else { return "[]" }
        let keys = rs.filter { $0["detail"] != nil }.map(PortalClient.key)
        let data = (try? JSONSerialization.data(withJSONObject: keys)) ?? Data("[]".utf8)
        return String(data: data, encoding: .utf8) ?? "[]"
    }

    static func key(_ r: [String: Any]) -> String {
        func s(_ k: String) -> String { if let v = r[k] { return "\(v)" }; return "" }
        return [s("year"), s("term"), s("cd"), s("seq"), s("campus")].joined(separator: "|")
    }

    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) {
        guard !finished, portal.schoolHost(message.frameInfo.securityOrigin.host),
              let b = message.body as? [String: Any], let m = b["m"] as? String, let a = b["a"] as? String else { return }
        switch m {
        case "progress": onProgress?(String(a.prefix(120)))
        case "done": save(a)
        case "fail":
            if a == "LOGIN" {
                if silent { finish("login") } else { onProgress?("\(portal.name)에 로그인해 주세요. 로그인하면 자동으로 불러옵니다.") }
            } else if a == "NOTFOUND" { finish("notfound") } else { if silent { finish("fail") } else { onProgress?(a) } }
        default: break
        }
    }

    private func save(_ json: String) {
        guard json.count < 6_000_000, var o = (try? JSONSerialization.jsonObject(with: Data(json.utf8))) as? [String: Any],
              var rs = o["records"] as? [[String: Any]] else { return finish("fail") }
        if portal.key == "hyin", let d = try? Data(contentsOf: portal.file), let prev = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any],
           let prs = prev["records"] as? [[String: Any]] {
            var old: [String: Any] = [:]
            for r in prs { if let det = r["detail"] { old[PortalClient.key(r)] = det } }
            for i in rs.indices where rs[i]["detail"] == nil { if let det = old[PortalClient.key(rs[i])] { rs[i]["detail"] = det } }
            o["records"] = rs
        }
        o["savedAt"] = Int(Date().timeIntervalSince1970 * 1000)
        guard let out = try? JSONSerialization.data(withJSONObject: o) else { return finish("fail") }
        do {
            try out.write(to: portal.file, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        } catch { return finish("fail") }
        if Cred.state(portal.key) == "failed" { Cred.setState(portal.key, "on") }
        finish("ok")
    }
}

/// 메시지 핸들러가 클라이언트를 붙잡아 두지 않게 한다
final class WeakHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?
    init(_ t: WKScriptMessageHandler) { target = t }
    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(ucc, didReceive: message)
    }
}

/// 학생이 직접 포털에 로그인하는 화면. 장학 정보를 읽으면 닫힌다.
final class PortalViewController: UIViewController {
    let client: PortalClient
    var onClose: ((String) -> Void)?
    private let status = UILabel()

    init(portal: Portal) {
        client = PortalClient(portal: portal, silent: false)
        super.init(nibName: nil, bundle: nil)
        modalPresentationStyle = .fullScreen
    }
    required init?(coder: NSCoder) { fatalError() }

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.05, green: 0.36, blue: 0.43, alpha: 1)
        let bar = UIView()
        bar.backgroundColor = view.backgroundColor
        status.textColor = .white
        status.font = .systemFont(ofSize: 13)
        status.numberOfLines = 2
        status.text = "\(client.portal.name)에 로그인해 주세요. 비밀번호는 앱에 저장되지 않습니다."
        let close = UIButton(type: .system)
        close.setTitle("닫기", for: .normal)
        close.setTitleColor(.white, for: .normal)
        close.addTarget(self, action: #selector(closeTap), for: .touchUpInside)
        for v in [bar, status, close, client.web] as [UIView] { v.translatesAutoresizingMaskIntoConstraints = false }
        view.addSubview(bar); bar.addSubview(status); bar.addSubview(close); view.addSubview(client.web)
        NSLayoutConstraint.activate([
            bar.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            bar.leadingAnchor.constraint(equalTo: view.leadingAnchor), bar.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            bar.heightAnchor.constraint(equalToConstant: 52),
            status.leadingAnchor.constraint(equalTo: bar.leadingAnchor, constant: 12), status.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
            close.leadingAnchor.constraint(equalTo: status.trailingAnchor, constant: 8),
            close.trailingAnchor.constraint(equalTo: bar.trailingAnchor, constant: -12), close.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
            client.web.topAnchor.constraint(equalTo: bar.bottomAnchor),
            client.web.leadingAnchor.constraint(equalTo: view.leadingAnchor), client.web.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            client.web.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
        close.setContentCompressionResistancePriority(.required, for: .horizontal)
        client.onProgress = { [weak self] t in self?.status.text = t }
        client.onFinish = { [weak self] r in
            guard let self = self else { return }
            if r == "ok" { self.dismiss(animated: true) { self.onClose?("ok") } }
            else if r == "notfound" { self.status.text = "장학 신청 화면을 찾지 못했어요. 메뉴에서 직접 열어 주세요." }
        }
        client.start()
    }

    @objc private func closeTap() {
        client.stop()
        dismiss(animated: true) { self.onClose?("cancel") }
    }
}

extension UIViewController {
    var topMost: UIViewController { presentedViewController?.topMost ?? self }
}
