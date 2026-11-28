import UIKit
import AVFoundation

@main
final class AppDelegate: NSObject, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication,
                     didFinishLaunching options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // 朗读/在线发音要走扬声器，并且允许锁屏后继续播放（对应安卓 USAGE_MEDIA 属性）
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .spokenAudio,
                                 options: [.mixWithOthers, .allowBluetoothA2DP])
        try? session.setActive(true)

        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = ReaderViewController()
        window.makeKeyAndVisible()
        self.window = window
        return true
    }
}
