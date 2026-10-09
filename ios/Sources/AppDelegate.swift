import UIKit
import BackgroundTasks
import UserNotifications

/// 장학알리미 iOS 앱. 웹앱(www)을 WKWebView 로 띄우고, 알림·포털 로그인·백그라운드 새로고침을 맡는다.
@main
final class AppDelegate: UIResponder, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        Background.register()
        let w = UIWindow(frame: UIScreen.main.bounds)
        w.rootViewController = MainViewController()
        w.makeKeyAndVisible()
        window = w
        return true
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        Background.schedule()
    }

    // 앱을 보고 있을 때도 알림을 배너로 보여 준다
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let key = response.notification.request.content.userInfo["portal"] as? String,
           let main = window?.rootViewController as? MainViewController {
            main.openPortal(key)
        }
        completionHandler()
    }
}
