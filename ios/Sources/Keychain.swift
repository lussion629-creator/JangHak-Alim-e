import Foundation
import Security

/// 학교 포털 자동 로그인용 아이디·비밀번호. iOS 키체인(이 기기에만, 잠금 해제 후 접근)에 둔다. 서버로 보내지 않는다.
enum Cred {
    private static func service(_ key: String) -> String { "kr.jangak.alimi.portal.\(key)" }

    static func save(_ key: String, id: String, pw: String) -> Bool {
        guard let data = try? JSONSerialization.data(withJSONObject: ["id": id, "pw": pw]) else { return false }
        delete(key)
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service(key),
            kSecAttrAccount as String: "login",
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            kSecValueData as String: data,
        ]
        let ok = SecItemAdd(q as CFDictionary, nil) == errSecSuccess
        if ok { setState(key, "on") }
        return ok
    }

    static func load(_ key: String) -> (id: String, pw: String)? {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service(key),
            kSecAttrAccount as String: "login",
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data,
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: String],
              let id = o["id"], let pw = o["pw"] else { return nil }
        return (id, pw)
    }

    static func has(_ key: String) -> Bool { load(key) != nil }

    static func delete(_ key: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service(key)]
        SecItemDelete(q as CFDictionary)
    }

    /// on / failed / off
    static func state(_ key: String) -> String {
        has(key) ? (UserDefaults.standard.string(forKey: "cred.\(key)") ?? "on") : "off"
    }

    static func setState(_ key: String, _ s: String) { UserDefaults.standard.set(s, forKey: "cred.\(key)") }

    static func clear(_ key: String) {
        delete(key)
        UserDefaults.standard.removeObject(forKey: "cred.\(key)")
    }
}
