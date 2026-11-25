import Foundation

/// 桌面版局域网同步（18765）与在线翻译/音频请求。
/// 对应安卓 MainActivity.request / readAll / postDesktopTts / downloadAudio。
///
/// HttpURLConnection → URLSession，但保留“后台线程同步等待”的写法：
/// Bridge 的所有分支都跑在自己的串行队列上，逻辑顺序与安卓一致，便于对照与回归。
///
/// ⚠️ iOS 上连 `http://192.168.x.x:18765` 需要两处配置（Info.plist 里已给）：
///   1. ATS 例外 `NSAllowsLocalNetworking`（明文 HTTP）；
///   2. iOS 18 起访问本地网络要 `NSLocalNetworkUsageDescription` 授权文案，
///      首次连接会弹「允许访问本地网络上的设备」，拒绝后同步/电脑语音全部失败，
///      需要用户去 设置 → App → 本地网络 手动打开。回环 127.0.0.1（内置服务器）不受此限制。
final class DesktopSync {

    private static let decoder = JSONDecoder()

    var lastEndpoint = ""
    var lastToken = ""

    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = false
        config.shouldUseExtendedBackgroundIdleMode = true
        config.httpAdditionalHeaders = ["User-Agent": "ReadingDesk/1.0 (iOS)"]
        return URLSession(configuration: config)
    }()

    // MARK: - 同步接口（/pair /sync /translate）

    func request(endpoint: String, path: String, payload: [String: Any], token: String) throws -> [String: Any] {
        guard let url = Self.validate(endpoint: endpoint, path: path) else {
            throw SyncError("请填写电脑显示的地址，例如 http://192.168.1.10:18765")
        }
        guard Self.isPrivateAddress(url) else { throw SyncError("仅允许连接局域网电脑地址") }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = path == "/translate" ? 20 : 10
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        if !token.isEmpty { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])

        let (data, response) = try wait(request, emptyMessage: "电脑未响应，请检查同步服务与网络")
        guard let http = response as? HTTPURLResponse else { throw SyncError("电脑未响应，请检查同步服务与网络") }
        let text = try Self.decode(data, limit: 5_000_000)
        guard let object = JSON.object(Data(text.utf8)) else { throw SyncError("同步失败") }
        if !(200..<300 ~= http.statusCode) {
            throw SyncError(object["error"] as? String ?? "同步失败")
        }
        return object
    }

    /// 桌面 /tts 中转（微软 edge-tts 神经语音），返回已校验的 mp3 字节
    func desktopTts(text: String, accent: String) throws -> Data {
        guard !lastEndpoint.isEmpty else { throw SyncError("发音服务暂不可用") }
        guard let base = URL(string: lastEndpoint), let host = base.host,
              let port = base.port, port >= 1, port <= 65535, base.scheme == "http" else {
            throw SyncError("电脑地址无效")
        }
        guard let url = URL(string: "http://\(host):\(port)/tts") else { throw SyncError("电脑地址无效") }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        if !lastToken.isEmpty { request.setValue("Bearer \(lastToken)", forHTTPHeaderField: "Authorization") }
        request.httpBody = try JSONSerialization.data(withJSONObject: ["text": text, "accent": accent],
                                                      options: [.sortedKeys])
        let (data, response) = try wait(request, emptyMessage: "电脑未响应，请检查同步服务与网络")
        guard let http = response as? HTTPURLResponse else { throw SyncError("电脑语音服务返回错误") }
        guard (200..<300).contains(http.statusCode) else {
            throw SyncError("电脑语音服务返回 \(http.statusCode)")
        }
        try Self.expectMp3(data)
        return data
    }

    /// 有道单词音频 / Google 整句音频
    func downloadAudio(_ urlString: String) throws -> Data {
        guard let url = URL(string: urlString) else { throw SyncError("音频内容无效") }
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        request.setValue("Mozilla/5.0 ReadingDesk/1.1 (iOS)", forHTTPHeaderField: "User-Agent")
        let (data, _) = try wait(request, emptyMessage: "发音服务暂不可用")
        try Self.expectMp3(data)
        return data
    }

    /// Google 翻译接口（返回 JSON 文本）
    func fetchData(_ urlString: String, timeout: TimeInterval, expect: Int?) throws -> Data {
        guard let url = URL(string: urlString) else { throw SyncError("翻译未返回结果") }
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("ReadingDesk/1.0", forHTTPHeaderField: "User-Agent")
        let (data, _) = try wait(request, emptyMessage: "翻译未返回结果")
        return data
    }

    // MARK: - 内部

    private func wait(_ request: URLRequest, emptyMessage: String) throws -> (Data, URLResponse) {
        let semaphore = DispatchSemaphore(value: 0)
        var result: (Data?, URLResponse?, Error?)
        result = (nil, nil, nil)
        let task = session.dataTask(with: request) { data, response, error in
            result = (data, response, error)
            semaphore.signal()
        }
        task.resume()
        semaphore.wait()
        if let error = result.2 { throw SyncError(Self.describe(error)) }
        guard let data = result.0, let response = result.1 else { throw SyncError(emptyMessage) }
        return (data, response)
    }

    /// 复刻安卓的 endpoint 白名单校验：只接受 http://纯 IPv4:端口 且无 userinfo/query/fragment
    static func validate(endpoint: String, path: String) -> URL? {
        let trimmed = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        let pattern = #"^http://([0-9]{1,3}(?:\.[0-9]{1,3}){3}):([1-9][0-9]{0,4})(?:/)?"#
        guard let match = trimmed.range(of: pattern, options: .regularExpression) else { return nil }
        let matched = String(trimmed[match])
        guard matched == trimmed || matched + "/" == trimmed else { return nil }
        guard let url = URL(string: matched + path) else { return nil }
        guard (1...65535).contains(url.port ?? -1) else { return nil }
        return url
    }

    /// 对应 isSiteLocalAddress() || isLoopbackAddress()
    static func isPrivateAddress(_ url: URL) -> Bool {
        guard let host = url.host else { return false }
        let octets = host.split(separator: ".").compactMap { Int($0) }
        guard octets.count == 4 else { return false }
        switch octets[0] {
        case 10: return true
        case 127: return true
        case 172: return (16...31).contains(octets[1])
        case 192: return octets[1] == 168
        case 169: return octets[1] == 254        // 链路本地：安卓同样允许，桌面多网卡时要用
        default: return false
        }
    }

    static func decode(_ data: Data, limit: Int) throws -> String {
        if data.count > limit { throw SyncError("数据过大，请分批导入") }
        guard let text = String(data: data, encoding: .utf8) else { throw SyncError("同步失败") }
        return text
    }

    /// mp3 魔数校验（ID3 头或帧同步头），与安卓 downloadAudio/postDesktopTts 一致
    static func expectMp3(_ data: Data) throws {
        guard data.count >= 128 else { throw SyncError("音频内容无效") }
        if data.count > 512_000 { throw SyncError("音频过大") }
        let bytes = [UInt8](data)
        let id3 = bytes[0] == UInt8(ascii: "I") && bytes[1] == UInt8(ascii: "D") && bytes[2] == UInt8(ascii: "3")
        let frame = (bytes[0] & 0xFF) == 0xFF && (bytes[1] & 0xE0) == 0xE0
        guard id3 || frame else { throw SyncError("音频内容无效") }
    }

    private static func describe(_ error: Error) -> String {
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain {
            switch ns.code {
            case NSURLErrorTimedOut: return "连接电脑超时，请确认桌面版已开启同步服务"
            case NSURLErrorNotConnectedToInternet: return "手机未联网，请检查 Wi-Fi 或蜂窝网络"
            case NSURLErrorNetworkConnectionLost: return "网络中断，请重试"
            case NSURLErrorCannotConnectToHost: return "无法连接电脑，请确认在同一 Wi-Fi 且已开启同步"
            case NSURLErrorCancelled: return "操作已取消"
            default: break
            }
        }
        return "电脑未响应，请检查同步服务与网络"
    }
}
