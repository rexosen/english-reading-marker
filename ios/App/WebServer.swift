import Foundation
import Network

/// 内置 127.0.0.1 静态服务器。
///
/// 安卓壳用 `file:///android_asset/index.html` 加载页面，`index.html` 里的
/// `<script src="app.js">` 等同目录相对引用由 Android AssetManager 直接解析。
/// WKWebView 的 `loadFileURL(_:allowingReadAccessTo:)` 在 iOS 9~17 上对同目录
/// 子资源的放行策略并不稳定（小图标/字体经常 404，且每次系统升级都可能变），
/// 所以在 App 进程内起一个只监听回环地址的极简 HTTP 服务器，行为与安卓一致。
///
/// 回环流量不触发 iOS 18 的「本地网络」权限弹窗，也不受 ATS 限制。
final class WebServer {

    private let rootURL: URL
    private var listener: NWListener?
    private var connections: [NWConnection] = []
    private let queue = DispatchQueue(label: "cn.readingdesk.reader.webserver")

    /// 页面基地址，形如 http://127.0.0.1:49321/
    private(set) var baseURL: URL?

    init(rootURL: URL) {
        self.rootURL = rootURL
    }

    func start(completion: @escaping (URL?) -> Void) {
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = NWEndpoint.hostPort(host: .ipv4(.loopback), port: .any)
        params.allowLocalEndpointReuse = true
        guard let listener = try? NWListener(using: params, on: .any) else {
            completion(nil); return
        }
        self.listener = listener
        listener.newConnectionHandler = { [weak self] connection in
            guard let self else { return }
            self.queue.async {
                self.connections.append(connection)
                connection.stateUpdateHandler = { state in
                    if case .failed = state { connection.cancel() }
                    if case .cancelled = state {
                        self.queue.async { self.connections.removeAll { $0 === connection } }
                    }
                }
                connection.start(queue: self.queue)
                self.receive(connection, buffer: Data())
            }
        }
        listener.stateUpdateHandler = { [weak self, weak listener] state in
            guard let self, case .ready = state,
                  let port = listener?.port else { return }
            self.baseURL = URL(string: "http://127.0.0.1:\(port.rawValue)/")
            completion(self.baseURL)
        }
        listener.start(queue: queue)
    }

    func stop() {
        listener?.cancel(); listener = nil
        connections.forEach { $0.cancel() }; connections.removeAll()
    }

    // MARK: - 连接处理

    private func receive(_ connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, _ in
            guard let self else { return }
            var accumulated = buffer
            if let data { accumulated.append(data) }
            // 请求头以空行结束；GET 无 body，收到空行即可处理。
            if let range = accumulated.range(of: Data("\r\n\r\n".utf8)) {
                self.handle(connection, request: Data(accumulated[..<range.lowerBound]))
                connection.cancel()
                self.queue.async { self.connections.removeAll { $0 === connection } }
            } else if isComplete {
                connection.cancel()
            } else {
                self.receive(connection, buffer: accumulated)
            }
        }
    }

    private func handle(_ connection: NWConnection, request: Data) {
        guard let text = String(data: request, encoding: .utf8) else { return send(connection, status: "400 Bad Request", headers: [:], body: Data()) }
        let lines = text.components(separatedBy: "\r\n")
        let parts = lines[0].split(separator: " ", maxSplits: 2)
        guard parts.count >= 2, parts[0] == "GET" || parts[0] == "HEAD" else {
            return send(connection, status: "405 Method Not Allowed", headers: ["Content-Length": "0"], body: Data())
        }
        let target = String(parts[1])
        guard let file = resolve(target) else {
            return send(connection, status: "404 Not Found",
                        headers: ["Content-Type": "text/plain; charset=utf-8"],
                        body: Data("not found".utf8))
        }
        let attributes = try? FileManager.default.attributesOfItem(atPath: file.path)
        let size = (attributes?[.size] as? NSNumber)?.int64Value ?? 0
        var headers = ["Content-Type": mime(file.pathExtension),
                       "Accept-Ranges": "bytes",
                       "Cache-Control": "no-store"]
        var body: Data?
        var status = "200 OK"
        if let range = byteRange(in: text, total: size), let handle = try? FileHandle(forReadingFrom: file) {
            defer { try? handle.close() }
            let (start, end) = range
            status = "206 Partial Content"
            headers["Content-Range"] = "bytes \(start)-\(end)/\(size)"
            headers["Content-Length"] = String(end - start + 1)
            try? handle.seek(toOffset: UInt64(start))
            body = try? handle.read(upToCount: Int(end - start + 1))
        } else {
            headers["Content-Length"] = String(size)
            body = (parts[0] == "HEAD") ? Data() : try? Data(contentsOf: file)
        }
        send(connection, status: status, headers: headers, body: body ?? Data())
    }

    /// 目录穿越防护：只允许 rootURL 之内的文件。
    private func resolve(_ target: String) -> URL? {
        let path = target.split(separator: "?")[0].split(separator: "#")[0]
        var name = String(path)
        if name.isEmpty || name == "/" { name = "/index.html" }
        name = name.removingPercentEncoding ?? name
        let candidate = rootURL.appendingPathComponent(
            name.hasPrefix("/") ? String(name.dropFirst()) : name)
            .standardizedFileURL
        let root = rootURL.standardizedFileURL.path
        guard candidate.path.hasPrefix(root + "/") || candidate.path == root else { return nil }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: candidate.path, isDirectory: &isDirectory),
              !isDirectory.boolValue else { return nil }
        return candidate
    }

    private func byteRange(in request: String, total: Int64) -> (Int64, Int64)? {
        guard total > 0,
              let line = request.components(separatedBy: "\r\n")
                .first(where: { $0.lowercased().hasPrefix("range:") }),
              let value = line.split(separator: ":").last?.trimmingCharacters(in: .whitespaces)
                .replacingOccurrences(of: "bytes=", with: "") else { return nil }
        let pieces = value.split(separator: "-")
        let start = Int64(pieces.first ?? "0") ?? 0
        let end = pieces.count > 1 ? (Int64(pieces[1]) ?? total - 1) : total - 1
        guard start < total, start <= end else { return nil }
        return (start, min(end, total - 1))
    }

    private func send(_ connection: NWConnection, status: String, headers: [String: String], body: Data) {
        var response = "HTTP/1.1 \(status)\r\n"
        for (key, value) in headers { response += "\(key): \(value)\r\n" }
        response += "Connection: close\r\n\r\n"
        var payload = Data(response.utf8)
        payload.append(body)
        connection.send(content: payload, completion: .contentProcessed { _ in })
    }

    private func mime(_ ext: String) -> String {
        switch ext.lowercased() {
        case "html", "htm": return "text/html; charset=utf-8"
        case "js", "mjs": return "application/javascript; charset=utf-8"
        case "css": return "text/css; charset=utf-8"
        case "json": return "application/json; charset=utf-8"
        case "mp3": return "audio/mpeg"
        case "m4a", "mp4": return "audio/mp4"
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "svg": return "image/svg+xml"
        case "sqlite3", "db": return "application/octet-stream"
        default: return "application/octet-stream"
        }
    }
}
