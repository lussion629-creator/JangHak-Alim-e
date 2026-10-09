import Foundation
import BackgroundTasks
import UserNotifications

/// 알림 보내기
enum Notify {
    static func post(id: String, title: String, body: String, info: [String: String] = [:], at date: DateComponents? = nil) {
        let c = UNMutableNotificationContent()
        c.title = title
        c.body = body
        c.sound = .default
        c.userInfo = info
        let trigger: UNNotificationTrigger? = date.map { UNCalendarNotificationTrigger(dateMatching: $0, repeats: false) }
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: id, content: c, trigger: trigger))
    }

    /// 페이지가 넘겨 준 '마감 임박 관심 장학' 목록을 바로 알린다
    static func deadlines(_ json: String) {
        guard let arr = (try? JSONSerialization.jsonObject(with: Data(json.utf8))) as? [[String: Any]] else { return }
        for o in arr.prefix(5) {
            let label = o["label"] as? String ?? "", title = o["title"] as? String ?? "", org = o["org"] as? String ?? ""
            post(id: "deadline-\(o["id"] as? String ?? title)", title: "\(label) · \(title)", body: org)
        }
    }

    static func loginStopped(_ p: Portal) {
        post(id: "login-\(p.key)", title: "\(p.name) 자동 로그인을 멈췄어요",
             body: "추가 인증이 필요하거나 비밀번호가 바뀌었을 수 있어요. 눌러서 한 번 로그인해 주세요.", info: ["portal": p.key])
    }
}

/// 사용자가 정한 알림 조건(키워드·지원 종류·학교)과 관심 장학 마감 알림. 조건은 이 기기에만 저장한다.
enum Alerts {
    static let defaultRemote = "https://lussion629-creator.github.io/JangHak-Alim-e/"
    static var cfg: [String: Any] {
        guard let s = UserDefaults.standard.string(forKey: "alerts.cfg"),
              let o = (try? JSONSerialization.jsonObject(with: Data(s.utf8))) as? [String: Any] else { return [:] }
        return o
    }

    static func save(_ json: String) {
        UserDefaults.standard.set(json, forKey: "alerts.cfg")
        scheduleFavorites()
    }

    /// 관심 장학 마감 전 알림은 아이폰에 미리 예약해 둔다 (앱이 꺼져 있어도 정한 날 오전 9시에 울림)
    static func scheduleFavorites() {
        let c = UNUserNotificationCenter.current()
        c.getPendingNotificationRequests { reqs in
            c.removePendingNotificationRequests(withIdentifiers: reqs.map(\.identifier).filter { $0.hasPrefix("fav-") })
            let fav = cfg["fav"] as? [[String: Any]] ?? [], before = cfg["before"] as? [Int] ?? []
            let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "ko_KR"); f.timeZone = TimeZone(identifier: "Asia/Seoul")
            var cal = Calendar(identifier: .gregorian); cal.timeZone = TimeZone(identifier: "Asia/Seoul")!
            var n = 0
            for o in fav {
                guard let id = o["id"] as? String, let e = o["e"] as? String, let end = f.date(from: e) else { continue }
                for d in before {
                    guard n < 60, let day = cal.date(byAdding: .day, value: -d, to: end) else { continue }
                    var comp = cal.dateComponents([.year, .month, .day], from: day); comp.hour = 9; comp.minute = 0
                    guard let fire = cal.date(from: comp), fire > Date() else { continue }
                    Notify.post(id: "fav-\(id)-\(d)", title: d == 0 ? "오늘 마감" : "마감 \(d)일 전", body: o["t"] as? String ?? "", at: comp)
                    n += 1
                }
            }
        }
    }

    /// 조건에 맞는 새 장학 (서버의 최신 목록과 비교)
    static func check(fetchRemote: Bool, done: @escaping () -> Void) {
        let c = cfg
        let kw = (c["kw"] as? [String] ?? []).map { $0.trimmingCharacters(in: .whitespaces).lowercased() }.filter { !$0.isEmpty }
        let cats = c["cats"] as? [String] ?? []
        let school = c["school"] as? String ?? ""
        guard fetchRemote, !(kw.isEmpty && cats.isEmpty) else { return done() }
        var base = c["remote"] as? String ?? defaultRemote
        if !base.hasPrefix("https://") { base = defaultRemote }
        if !base.hasSuffix("/") { base += "/" }
        guard let url = URL(string: base + "data/meta.json") else { return done() }
        URLSession.shared.dataTask(with: url) { data, _, _ in
            defer { done() }
            guard let data = data, data.count < 2_000_000,
                  let meta = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any], let open = meta["open"] as? [[String: Any]] else { return }
            var seen = Set(UserDefaults.standard.stringArray(forKey: "alerts.seen") ?? [])
            let first = seen.isEmpty
            var shown = 0
            for o in open {
                guard let id = o["id"] as? String, seen.insert(id).inserted, !first else { continue }
                if !school.isEmpty, let f = o["f"] as? [String], !f.isEmpty, !f.contains(school) { continue }
                let t = o["t"] as? String ?? "", hay = (t + " " + (o["o"] as? String ?? "")).lowercased()
                let s = o["s"] as? [String] ?? []
                let hit = kw.contains { hay.contains($0) } || s.contains { cats.contains($0) }
                if hit && shown < 5 { Notify.post(id: "new-\(id)", title: "새 장학 · 알림 조건에 맞음", body: t); shown += 1 }
            }
            UserDefaults.standard.set(Array(seen.suffix(3000)), forKey: "alerts.seen")
        }.resume()
    }
}

/// 한양대 공개 공지 게시판(근로장학 모집 확인용)을 휴대폰에서 직접 읽는다. 한양대 공지 주소만 허용한다.
enum HyWork {
    static let p = "kr_ac_hanyang_noticeBoard_web_portlet_NoticeBoardPortlet"
    static let cats = ["224311302", "224311300"]

    static func allowed(_ s: String) -> Bool {
        guard let u = URL(string: s) else { return false }
        return u.scheme == "https" && u.host == "www.hanyang.ac.kr" && u.path.hasPrefix("/notice_all")
    }

    static func listURL(_ cat: String) -> String {
        "https://www.hanyang.ac.kr/notice_all?p_p_id=\(p)&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&_\(p)_action=view&_\(p)_sCategoryId=\(cat)&_\(p)_cur=1"
    }

    static func fetch(_ s: String, done: @escaping (String?) -> Void) {
        guard allowed(s), let u = URL(string: s) else { return done(nil) }
        var r = URLRequest(url: u, timeoutInterval: 15)
        r.setValue("ko-KR", forHTTPHeaderField: "Accept-Language")
        URLSession.shared.dataTask(with: r) { d, resp, _ in
            let ok = (resp as? HTTPURLResponse)?.statusCode == 200
            let body = ok ? d.flatMap { String(data: $0.prefix(3_000_000), encoding: .utf8) } : nil
            DispatchQueue.main.async { done(body) }
        }.resume()
    }

    static func markSeen(_ ids: [String]) {
        var s = Set(UserDefaults.standard.stringArray(forKey: "hywork.seen") ?? [])
        ids.forEach { s.insert($0) }
        UserDefaults.standard.set(Array(s), forKey: "hywork.seen")
    }

    /// 새 근로장학 모집 글을 알린다 (한양대 학생이거나 학교를 고르지 않은 경우만)
    static func check(done: @escaping () -> Void) {
        let school = Alerts.cfg["school"] as? String ?? ""
        guard school.isEmpty || school == "hy" else { return done() }
        let work = try! NSRegularExpression(pattern: "근로|장학조교|학생\\s*조교|도우미|튜터|Tutor", options: .caseInsensitive)
        let not = try! NSRegularExpression(pattern: "계약직|직원\\s*(채용|모집)|강사|교수|초빙|연구원|연구조교|연구병|인력풀")
        let item = try! NSRegularExpression(pattern: "entryId=(\\d+)[^\"]*\"[^>]*>\\s*([^<]{4,300}?)\\s*</a>")
        var posts: [(String, String)] = []
        let g = DispatchGroup()
        for c in cats {
            g.enter()
            fetch(listURL(c)) { body in
                defer { g.leave() }
                guard let body = body else { return }
                let ns = body as NSString
                for m in item.matches(in: body, range: NSRange(location: 0, length: ns.length)) {
                    let id = ns.substring(with: m.range(at: 1))
                    let t = ns.substring(with: m.range(at: 2)).replacingOccurrences(of: "&amp;", with: "&").replacingOccurrences(of: "&#39;", with: "'")
                        .replacingOccurrences(of: "&quot;", with: "\"").trimmingCharacters(in: .whitespacesAndNewlines)
                    let r = NSRange(location: 0, length: (t as NSString).length)
                    if work.firstMatch(in: t, range: r) != nil && not.firstMatch(in: t, range: r) == nil { posts.append((id, t)) }
                }
            }
        }
        g.notify(queue: .main) {
            var seen = Set(UserDefaults.standard.stringArray(forKey: "hywork.seen") ?? [])
            let first = seen.isEmpty
            var shown = 0
            for (id, t) in posts where seen.insert(id).inserted && !first && shown < 3 {
                Notify.post(id: "work-\(id)", title: "새 근로장학 모집", body: t); shown += 1
            }
            UserDefaults.standard.set(Array(seen), forKey: "hywork.seen")
            done()
        }
    }
}

/// iOS 가 정하는 때(보통 몇 시간마다)에 알림 조건·근로 모집을 확인한다.
enum Background {
    static let id = "kr.jangak.alimi.refresh"

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: id, using: nil) { task in
            schedule()
            var finished = false
            task.expirationHandler = { if !finished { finished = true; task.setTaskCompleted(success: false) } }
            let g = DispatchGroup()
            g.enter(); Alerts.check(fetchRemote: true) { g.leave() }
            g.enter(); DispatchQueue.main.async { HyWork.check { g.leave() } }
            g.notify(queue: .main) { if !finished { finished = true; task.setTaskCompleted(success: true) } }
        }
    }

    static func schedule() {
        let r = BGAppRefreshTaskRequest(identifier: id)
        r.earliestBeginDate = Date(timeIntervalSinceNow: 3 * 3600)
        try? BGTaskScheduler.shared.submit(r)
    }
}
