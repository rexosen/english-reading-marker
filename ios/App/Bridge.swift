import Foundation
import WebKit
import UniformTypeIdentifiers

/// 对应安卓 MainActivity.Bridge + 朗读/网络/文件各分支。
/// 协议保持不变：JS 侧 `ReaderNative.send(id, action, rawJSONString)`，
/// 原生侧回 `window.nativeReply(id, result)` / `window.nativeNotice(text)` /
/// `window.nativeSpeechDone(tag, error)`。
final class Bridge: NSObject, WKScriptMessageHandler {

    private weak var host: ReaderViewController?
    private let executor = DispatchQueue(label: "cn.readingdesk.reader.bridge", qos: .userInitiated)
    let speech = SpeechEngine()
    let online = OnlineAudio()
    let dictionary = DictionaryStore()
    let network = DesktopSync()
    private(set) lazy var files = FilePickers(host: host)
    private let storage: StorageMirror

    private let googleTTL: TimeInterval = 600          // 对应 markGoogleOk() 的 600000ms
    private var googleOkUntil = Date.distantPast
    private var pendingCsv: String?
    private var pendingBackup: String?

    private var googleHot: Bool { googleOkUntil > Date() }

    init(host: ReaderViewController, webDirectory: URL, storage: StorageMirror) {
        self.host = host
        self.storage = storage
        super.init()
        speech.owner = self
        online.owner = self
        online.systemFallback = { [weak self] text, accent, speed in
            self?.speech.speak(text: text, accent: accent, speed: speed)
        }
        online.pronunciationProvider = { [weak self] text, accent, single in
            guard let self else { throw SyncError("发音服务暂不可用") }
            return try self.pronunciationFile(text: text, accent: accent, single: single)
        }
        online.notice = { [weak self] in self?.notice($0) }
        online.finished = { [weak self] in self?.speechDone(tag: $0, error: $1) }
        dictionary.onUnavailable = { [weak self] in self?.notice($0) }
        // 对应安卓 onCreate 里后台拷贝 60 MB 词库：提前在串行队列装好，
        // 免得用户第一次查词才等拷贝（installIfNeeded 里已有可重入锁保护）
        executor.async { [weak self] in self?.dictionary.installIfNeeded() }
    }

    // MARK: - JS → 原生

    /// 注入两段用户脚本（都在 documentStart，早于 app.js 执行）：
    ///   1. bootstrap —— 把原生镜像快照回填进 localStorage（只在 WebKit 抹掉后触发）
    ///   2. ios-shim.js —— ReaderNative.send 兼容层 + localStorage 写回 + 自愈提示
    /// 对应安卓的 addJavascriptInterface(...)：iOS 没有等价 API，只能 postMessage。
    func installUserScripts(into controller: WKUserContentController) {
        let bootstrap = """
        (function () {
          try {
            var mirror = \(storage.snapshotForInjection());
            window.__storageMirror__ = mirror;
            var probe = null;
            try { probe = localStorage.getItem('reader-v1'); } catch (e) { probe = null; }
            if (!probe && mirror['reader-v1']) {
              try {
                localStorage.setItem('reader-v1', mirror['reader-v1']);
                if (mirror['listening-v1']) localStorage.setItem('listening-v1', mirror['listening-v1']);
                if (mirror['reader-backups-v1']) localStorage.setItem('reader-backups-v1', mirror['reader-backups-v1']);
                window.__storageRestored__ = true;
              } catch (e) { }
            }
          } catch (e) { }
        })();
        """
        controller.addUserScript(WKUserScript(source: bootstrap,
                                              injectionTime: .atDocumentStart,
                                              forMainFrameOnly: true))
        if let url = Self.shimURL, let text = try? String(contentsOf: url, encoding: .utf8) {
            controller.addUserScript(WKUserScript(source: text,
                                                  injectionTime: .atDocumentStart,
                                                  forMainFrameOnly: true))
        }
    }

    /// ios-shim.js 在 Bundle 里的位置：WebResources 优先，其次顶层 Web 目录
    static let shimURL: URL? = {
        let candidates = [
            Bundle.main.url(forResource: "ios-shim", withExtension: "js", subdirectory: "WebResources"),
            Bundle.main.url(forResource: "ios-shim", withExtension: "js", subdirectory: "Web"),
            Bundle.main.url(forResource: "ios-shim", withExtension: "js"),
        ]
        return candidates.compactMap { $0 }.first
    }()

    var shimMissing: Bool { Self.shimURL == nil }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "ReaderNative", let envelope = message.body as? [String: Any] else { return }
        let id = envelope["id"] as? String ?? ""
        let action = envelope["action"] as? String ?? ""
        // 兼容两种传法：安卓的三段式 raw 字符串，或 iOS 直接传对象
        let raw: String
        if let text = envelope["body"] as? String { raw = text }
        else if let object = envelope["body"] { raw = JSON.stringify(object) }
        else { raw = "{}" }
        executor.async { [weak self] in self?.handle(id: id, action: action, raw: raw) }
    }

    private func handle(id: String, action: String, raw: String) {
        var response: [String: Any] = [:]
        do {
            guard let payload = JSON.object(Data(raw.utf8)) else { throw SyncError("操作失败，请检查网络或重试") }
            switch action {
            case "pair", "sync":
                let url = payload["url"] as? String ?? ""
                let result = try network.request(endpoint: url,
                                                 path: action == "pair" ? "/pair" : "/sync",
                                                 payload: payload["body"] as? [String: Any] ?? [:],
                                                 token: payload["token"] as? String ?? "")
                network.lastEndpoint = url
                let issued = (result["token"] as? String).flatMap { $0.isEmpty ? nil : $0 }
                    ?? (payload["token"] as? String) ?? ""
                if !issued.isEmpty { network.lastToken = issued }
                response = result

            case "translate":
                response = ["text": try translate(payload)]

            case "speak":
                let text = ((payload["text"] as? String) ?? "").trimmingCharacters(in: .whitespaces)
                let accent = (payload["accent"] as? String) == "uk" ? "uk" : "us"
                let speed = min(1.25, max(0.6, (payload["speed"] as? NSNumber)?.doubleValue ?? 0.75))
                let source = (payload["source"] as? String) == "system" ? "system" : "dictionary"
                let requestTag = payload["request_id"] as? String ?? ""
                DispatchQueue.main.async { [weak self] in
                    if source == "system" {
                        self?.speech.speak(text: text, accent: accent, speed: speed, requestTag: requestTag)
                    } else {
                        self?.online.start(text: text, accent: accent, speed: speed, requestTag: requestTag)
                    }
                }
                response = ["ok": true]

            case "pause":
                DispatchQueue.main.async { [weak self] in self?.togglePause() }
                response = ["ok": true]

            case "stop":
                DispatchQueue.main.async { [weak self] in self?.stopAudio() }
                response = ["ok": true]

            case "clearAudioCache":
                DispatchQueue.main.async { [weak self] in self?.stopAudio() }
                var removed = 0
                if let items = try? FileManager.default.contentsOfDirectory(at: AppPaths.pronunciation, includingPropertiesForKeys: nil) {
                    for item in items where item.pathExtension == "mp3" || item.pathExtension == "tmp" {
                        if (try? FileManager.default.removeItem(at: item)) != nil { removed += 1 }
                    }
                }
                response = ["removed": removed]

            case "chooseBackground", "importBackup":
                let wantImage = action == "chooseBackground"
                DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    if self.files.busy {
                        self.reply(id, ["error": "已有文件选择窗口，请先完成或取消"]); return
                    }
                    if wantImage {
                        self.files.pickImage { [weak self] in self?.reply(id, $0) }
                    } else {
                        self.files.pickJSON { [weak self] in self?.reply(id, $0) }
                    }
                }
                return

            case "exportBackup":
                let data = payload["data"] as? String ?? ""
                if data.utf8.count > 15_000_000 { throw SyncError("备份过大，请先移除过大的背景图") }
                pendingBackup = data
                DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    self.reply(id, ["ok": true])
                    self.files.export(text: self.pendingBackup ?? "",
                                      suggestedName: "ReadingDesk-\(Int(Date().timeIntervalSince1970 * 1000)).json",
                                      type: UTType(filenameExtension: "json") ?? .json,
                                      success: "完整备份文件已导出",
                                      failure: "备份导出失败，请重新选择位置")
                    self.pendingBackup = nil
                }
                return

            case "export":
                pendingCsv = payload["csv"] as? String ?? ""
                DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    self.reply(id, ["ok": true])
                    // BOM 与安卓 ("\ufeff"+csv) 一致，Excel 打开中文表头才不乱码
                    self.files.export(text: "\u{FEFF}" + (self.pendingCsv ?? ""),
                                      suggestedName: "英语生词表.csv",
                                      type: UTType(filenameExtension: "csv") ?? .plainText,
                                      success: "CSV 已导出",
                                      failure: "导出失败，请重新选择保存位置")
                    self.pendingCsv = nil
                }
                return

            case "storage":                       // iOS 新增分支：localStorage 镜像写回原生文件
                let key = payload["key"] as? String ?? ""
                if payload["value"] is NSNull || payload["value"] == nil { storage.remove(key: key) }
                else if let value = payload["value"] as? String { storage.persist(key: key, value: value) }
                response = ["ok": true]

            case "platform":                      // iOS 新增分支：供页面判断运行平台
                response = ["platform": "ios", "ios": true,
                            "systemVersion": ProcessInfo.processInfo.operatingSystemVersionString]

            default:
                throw SyncError("不支持的操作")
            }
        } catch {
            response["error"] = error is SyncError ? error.localizedDescription : "操作失败，请检查网络或重试"
        }
        reply(id, response)
    }

    // MARK: - 原生 → JS

    private func reply(_ id: String, _ result: [String: Any]) {
        guard !id.isEmpty else { return }
        host?.executeOnMain("window.nativeReply&&window.nativeReply(\(JSON.quote(id)),\(JSON.jsLiteral(result)));")
    }

    func notice(_ message: String) {
        host?.executeOnMain("window.nativeNotice&&window.nativeNotice(\(JSON.quote(message)));")
    }

    func speechDone(tag: String, error: String) {
        guard !tag.isEmpty else { return }
        host?.executeOnMain("window.nativeSpeechDone&&window.nativeSpeechDone(\(JSON.quote(tag)),\(JSON.quote(error)));")
    }

    // MARK: - 暂停 / 停止

    private func togglePause() {
        if online.isActive { online.togglePause(); return }
        speech.togglePause()
    }

    private func stopAudio() {
        online.stop()
        speech.stop()
    }

    func applicationPaused() { online.pauseForBackground(); speech.stop() }
    func applicationResumed() { online.resumeFromBackground() }
    func shutdown() { stopAudio(); dictionary.close() }

    // MARK: - 翻译链路：本地词典 → 电脑中转 → Google → 电脑重试

    private func translate(_ payload: [String: Any]) throws -> String {
        let text = ((payload["text"] as? String) ?? "").trimmingCharacters(in: .whitespaces)
        if text.isEmpty || text.count > 20_000 { throw SyncError("请选择 20000 字符以内的英文内容") }
        if let local = dictionary.lookup(text) { return local }

        let url = payload["url"] as? String ?? ""
        let token = payload["token"] as? String ?? ""
        var lastError: Error?
        var desktopTried = false

        func viaDesktop() throws -> String {
            desktopTried = true
            let result = try network.request(endpoint: url, path: "/translate", payload: ["text": text], token: token)
            network.lastEndpoint = url
            if !token.isEmpty { network.lastToken = token }
            guard let value = result["text"] as? String else { throw SyncError("同步失败") }
            return value
        }

        // 哪条通道刚验证可用就先走哪条（10 分钟热度），Google 直连需要全局 VPN，电脑中转需要开机。
        if !googleHot && !url.isEmpty {
            do { return try viaDesktop() } catch { lastError = error }
        }
        do {
            let value = try sentenceTranslate(text)
            googleOkUntil = Date().addingTimeInterval(googleTTL)
            return value
        } catch { lastError = error; googleOkUntil = .distantPast }
        if !desktopTried && !url.isEmpty {
            do { return try viaDesktop() } catch { lastError = error }
        }
        throw lastError ?? SyncError("翻译未返回结果")
    }

    /// 按 400 字符分组调用 Google，与安卓 translate() 的分块逻辑一致。
    private func sentenceTranslate(_ text: String) throws -> String {
        var chunks: [String] = []
        var current = ""
        for piece in text.components(separatedBy: " ") {
            let candidate = current.isEmpty ? piece : current + " " + piece
            if current.count + piece.count + 1 > 400 && !current.isEmpty {
                chunks.append(current)
                current = piece
            } else {
                current = candidate
            }
        }
        if !current.isEmpty { chunks.append(current) }
        var result: [String] = []
        for chunk in chunks { result.append(try googleTranslate(chunk)) }
        return result.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func googleTranslate(_ text: String) throws -> String {
        if text.count > 1000 { throw SyncError("请选取较短的英文片段后重试") }
        let url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
            + text.wwwFormUrlEncoded
        let data = try network.fetchData(url, timeout: 5, expect: nil)
        guard let outer = try JSONSerialization.jsonObject(with: data) as? [Any],
              let segments = outer.first as? [Any] else { throw SyncError("翻译未返回结果") }
        var result = ""
        for segment in segments where (segment as? [Any])?.first as? String != nil {
            result += ((segment as? [Any])?.first as? String) ?? ""
        }
        if result.isEmpty { throw SyncError("翻译未返回结果") }
        return result
    }

    // MARK: - 发音缓存（对应 pronunciationFile）

    private func pronunciationFile(text: String, accent: String, single: Bool) throws -> URL {
        var word = text.replacingOccurrences(of: "\u{2019}", with: "'")
        let allCaps = word.count > 1 && word.allSatisfy { $0.isLetter && $0.isUppercase }
        if single && !allCaps { word = word.lowercased() }
        let name = Digest.sha256Hex((single ? "word:" : "sentence:") + accent + ":" + word)
        let target = AppPaths.pronunciation.appendingPathComponent(name + ".mp3")
        if let size = (try? FileManager.default.attributesOfItem(atPath: target.path))?[.size] as? Int,
           size >= 128 { return target }

        if single {
            let voiceType = accent == "uk" ? "1" : "2"
            let data = try network.downloadAudio("https://dict.youdao.com/dictvoice?audio="
                + word.wwwFormUrlEncoded + "&type=" + voiceType)
            try CachedFile.write(data, to: target)
            return target
        }

        let google = "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl="
            + (accent == "uk" ? "en-GB" : "en-US") + "&q=" + word.wwwFormUrlEncoded
        var last: Error?
        let hot = googleHot
        if hot {
            do { try CachedFile.write(try network.downloadAudio(google), to: target); googleOkUntil = Date().addingTimeInterval(googleTTL); return target }
            catch { last = error; googleOkUntil = .distantPast }
        }
        if !network.lastEndpoint.isEmpty {
            do { try CachedFile.write(try network.desktopTts(text: word, accent: accent), to: target); return target }
            catch { last = error }
        }
        if !hot {
            do { try CachedFile.write(try network.downloadAudio(google), to: target); googleOkUntil = Date().addingTimeInterval(googleTTL); return target }
            catch { last = error }
        }
        throw last ?? SyncError("发音服务暂不可用")
    }
}

struct SyncError: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

enum AppPaths {
    static let support: URL = {
        let url = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
            .appendingPathComponent("EnglishReadingMarker", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }()
    static let pronunciation: URL = {
        let url = support.appendingPathComponent("pronunciation", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }()
}

enum CachedFile {
    /// 先写临时文件再改名，避免半个 mp3 被当成有效缓存（安卓 writeCachedFile 同款）。
    static func write(_ data: Data, to target: URL) throws {
        let temporary = target.deletingLastPathComponent()
            .appendingPathComponent("voice-\(UUID().uuidString).tmp")
        do {
            try data.write(to: temporary)
            if FileManager.default.fileExists(atPath: target.path) { try? FileManager.default.removeItem(at: target) }
            try FileManager.default.moveItem(at: temporary, to: target)
        } catch {
            try? FileManager.default.removeItem(at: temporary)
            if !FileManager.default.fileExists(atPath: target.path) { throw SyncError("缓存失败") }
        }
    }
}
