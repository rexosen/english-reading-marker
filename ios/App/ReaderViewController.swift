import UIKit
import WebKit

/// 对应安卓 MainActivity 的 WebView 容器 + 系统栏处理。
final class ReaderViewController: UIViewController {

    private var webView: WKWebView!
    private var bridge: Bridge!
    private var server: WebServer?
    private var storageMirror: StorageMirror!

    /// Web 资源目录：优先 Bundle/WebResources（project.yml 里 assembled 的那份）。
    /// XcodeGen / 手工拖工程都可能把资源平铺进 Bundle 根目录，所以这里按
    /// 「哪个目录里真的有 index.html」来判定，两种打包形态都能跑。
    private static let webDirectory: URL = {
        let fm = FileManager.default
        var candidates: [URL] = []
        for name in ["WebResources", "web", "assets"] {
            if let url = Bundle.main.url(forResource: name, withExtension: nil) { candidates.append(url) }
        }
        if let resources = Bundle.main.resourceURL {
            candidates.append(resources.appendingPathComponent("WebResources"))
            candidates.append(resources)                        // 平铺形态
        }
        candidates.append(Bundle.main.bundleURL)
        for directory in candidates where fm.fileExists(atPath: directory.appendingPathComponent("index.html").path) {
            return directory
        }
        return candidates.first ?? Bundle.main.bundleURL
    }()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.957, green: 0.965, blue: 0.980, alpha: 1) // #f4f6fa，与页面底色一致
        additionalSafeAreaInsets = .zero   // 页面自己带 top bar，内容铺满全屏

        storageMirror = StorageMirror()

        let config = WKWebViewConfiguration()
        let controller = WKUserContentController()
        bridge = Bridge(host: self, webDirectory: Self.webDirectory, storage: storageMirror)
        controller.add(bridge, name: "ReaderNative")           // 对应 addJavascriptInterface(..., "ReaderNative")
        config.userContentController = controller
        bridge.installUserScripts(into: controller)            // localStorage 镜像 + ReaderNative.send 兼容层
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.mediaTypesRequiringUserActionForPlayback = []    // 允许程序化播放音频（安卓默认可自动播）
        config.allowsInlineMediaPlayback = true
        if #available(iOS 14.5, *) {
            config.preferences.isElementFullscreenEnabled = true
        }
        config.preferences.setValue(true, forKey: "developerExtrasEnabled") // 调试用，上架可关

        webView = WKWebView(frame: view.bounds, configuration: config)
        webView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        webView.allowsBackForwardNavigationGestures = false
        webView.allowsLinkPreview = false
        webView.isOpaque = true
        webView.backgroundColor = view.backgroundColor
        scrollViewAppearance(webView.scrollView)
        if #available(iOS 16.4, *) { webView.isInspectable = true }  // Safari 网页检查器
        #if targetEnvironment(macCatalyst)
        webView.evaluateJavaScript("document.documentElement.classList.add('mac')", completionHandler: nil)
        #endif
        view.addSubview(webView)

        // iOS 没有返回键：左滑边缘手势等价 onBackPressed → window.handleBack()
        let swipe = UIScreenEdgePanGestureRecognizer(target: self, action: #selector(backGesture(_:)))
        swipe.edges = .left
        swipe.delaysTouchesBegan = false
        webView.addGestureRecognizer(swipe)

        loadPage()
    }

    private func scrollViewAppearance(_ scrollView: UIScrollView) {
        scrollView.contentInsetAdjustmentBehavior = .never     // 安卓用 setDecorFitsSystemWindows(false) 自己处理
        scrollView.bounces = true
        scrollView.keyboardDismissMode = .interactive
    }

    private func loadPage() {
        guard let index = Self.webDirectory.appendingPathComponent("index.html") as URL?,
              FileManager.default.fileExists(atPath: index.path) else {
            showToast("缺少 WebResources/index.html，请先运行 tools/sync_web_assets.py")
            return
        }
        if bridge.shimMissing {
            // 没有兼容层就没人把 ReaderNative.send 翻译成 postMessage，桥是死的
            showToast("缺少 WebResources/ios-shim.js，桥接不可用，请重新同步 Web 资源")
        }
        let server = WebServer(rootURL: Self.webDirectory)
        self.server = server
        server.start { [weak self] baseURL in
            guard let self else { return }
            let url: URL
            if let baseURL {
                url = baseURL
            } else {
                // 回退：直接 file:// 加载（子资源可能被拦，功能仍大部分可用）
                url = index
            }
            DispatchQueue.main.async {
                self.webView.load(URLRequest(url: url))
            }
        }
    }

    @objc private func backGesture(_ gesture: UIScreenEdgePanGestureRecognizer) {
        guard gesture.state == .recognized else { return }
        webView.evaluateJavaScript("window.handleBack && window.handleBack();", completionHandler: nil)
    }

    // MARK: - 供 Bridge 调用

    func executeOnMain(_ javascript: String) {
        guard let webView else { return }
        if Thread.isMainThread {
            webView.evaluateJavaScript(javascript, completionHandler: nil)
        } else {
            DispatchQueue.main.async { self.webView?.evaluateJavaScript(javascript, completionHandler: nil) }
        }
    }

    func present(_ viewController: UIViewController, completion: ((Bool) -> Void)? = nil) {
        DispatchQueue.main.async {
            viewController.modalPresentationStyle = .fullScreen
            self.present(viewController, animated: true) { completion?(true) }
        }
    }

    func showToast(_ message: String) { bridge.notice(message) }

    override func didReceiveMemoryWarning() {
        super.didReceiveMemoryWarning()
        // 页面数据由 StorageMirror 落在 Application Support，被系统回收 WebView 存储也不会丢
        server?.start { _ in }   // 服务器被系统回收时按需重启（幂等）
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        bridge.applicationPaused()
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        bridge.applicationResumed()
    }

    deinit {
        server?.stop()
        bridge.shutdown()
        webView?.configuration.userContentController.removeScriptMessageHandler(forName: "ReaderNative")
    }
}
