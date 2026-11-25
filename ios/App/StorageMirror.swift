import Foundation

/// iOS 上必须有的“localStorage 镜像”。
///
/// 为什么安卓没有、iOS 一定要加：
/// 页面数据全在 localStorage 的三个键里（reader-v1 / listening-v1 / reader-backups-v1，
/// 最大可到十几 MB，因为里面内嵌了 base64 背景图）。Android WebView 的 localStorage
/// 落在 app 私有目录，系统不会主动清；而 WKWebView 的 localStorage 存在
/// Library/WebKit/…/LocalStorage，属于「可再生缓存」类别 —— iOS 在存储空间紧张、
/// App 长期不用、或系统清理网站数据时会把它整体抹掉（WebsiteDataStore 的
/// .dataDetection / purge），用户打开 App 就变成空白，且没有任何报错。
///
/// 对策：每次 setItem/removeItem 都同步写一份到 Application Support（受备份管理、
/// 不被系统清理），documentStart 时再把快照灌回 localStorage。页面完全无感知，
/// app.js / learning.js 一行都不用改。
final class StorageMirror {

    /// 页面里用到的键；其它键一并镜像，不硬限制，便于以后扩展
    private let knownKeys = ["reader-v1", "listening-v1", "reader-backups-v1"]
    private let queue = DispatchQueue(label: "cn.readingdesk.reader.storage", qos: .utility)
    private var cache: [String: String] = [:]
    private let mirrorURL: URL

    init() {
        let directory = AppPaths.support
        mirrorURL = directory.appendingPathComponent("storage-mirror.json")
        load()
    }

    // MARK: - 读取（documentStart 注入用）

    /// 返回给 JS 的表达式字面量：JSON.parse("…")，避免任何注入风险
    func snapshotForInjection() -> String {
        queue.sync {
            var object: [String: Any] = [:]
            for (key, value) in cache { object[key] = value }
            return JSON.jsLiteral(object)
        }
    }

    func snapshot() -> String {
        queue.sync { JSON.stringify(cache) }
    }

    // MARK: - 写入

    func persist(key: String, value: String) {
        guard !key.isEmpty, key.count <= 128 else { return }
        queue.async {
            self.cache[key] = value
            self.flush()
        }
    }

    func remove(key: String) {
        guard !key.isEmpty else { return }
        queue.async {
            self.cache[key] = ""
            self.flush()
        }
    }

    /// 供「连接电脑」拉回整份快照后写回（桌面 → iOS 的同步落盘也走这里）
    func importBackup(_ text: String) {
        persist(key: "reader-v1", value: text)
    }

    // MARK: - 落盘

    private func load() {
        guard let data = FileManager.default.contents(atPath: mirrorURL.path),
              let object = JSON.object(data) else { return }
        for (key, value) in object {
            if let text = value as? String { cache[key] = text }
        }
        knownKeys.forEach { cache[$0] = cache[$0] ?? "" }
    }

    /// tmp + rename，与安卓 writeCachedFile 一致，避免写一半掉电留下坏 JSON
    private func flush() {
        let directory = mirrorURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var object: [String: Any] = [:]
        for (key, value) in cache where !value.isEmpty { object[key] = value }
        guard let data = try? JSONSerialization.data(withJSONObject: object,
                                                    options: [.sortedKeys, .prettyPrinted]) else { return }
        let tmp = directory.appendingPathComponent("storage-mirror.tmp")
        do {
            try data.write(to: tmp, options: .atomic)
            _ = try FileManager.default.replaceItemAt(mirrorURL, withItemAt: tmp)
        } catch {
            try? FileManager.default.removeItem(at: tmp)
        }
    }
}
