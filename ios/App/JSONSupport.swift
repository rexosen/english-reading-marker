import Foundation
import CryptoKit

/// JSON 工具，与安卓里用的 org.json 一一对应，保证错误文案与序列化行为一致。
enum JSON {

    static func object(_ data: Data?) -> [String: Any]? {
        guard let data, let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return value
    }

    static func stringify(_ value: Any) -> String {
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8) else { return "{}" }
        return text
    }

    /// 把任意 JSON 值转成可以直接拼进 evaluateJavaScript 的 JS 字面量。
    static func jsLiteral(_ value: Any) -> String {
        if value is NSNull { return "null" }
        if let string = value as? String { return quote(string) }
        if let number = value as? NSNumber {
            if CFBooleanGetTypeID() == CFGetTypeID(number) { return number.boolValue ? "true" : "false" }
            return number.stringValue
        }
        guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else { return "null" }
        let text = String(decoding: data, as: UTF8.self)
        return "JSON.parse(\"\(escapeForJSString(text))\")"
    }

    /// 等价于 JSONObject.quote(String)：加双引号并逐字符转义。
    static func quote(_ string: String) -> String {
        var result = "\""
        for scalar in string.unicodeScalars {
            switch scalar {
            case "\"": result += "\\\""
            case "\\": result += "\\\\"
            case "\n": result += "\\n"
            case "\r": result += "\\r"
            case "\t": result += "\\t"
            case "\u{0008}": result += "\\b"
            case "\u{000C}": result += "\\f"
            case "\u{2028}": result += "\\u2028"
            case "\u{2029}": result += "\\u2029"
            default:
                if scalar.value < 0x20 { result += String(format: "\\u%04x", scalar.value) }
                else { result.unicodeScalars.append(scalar) }
            }
        }
        return result + "\""
    }

    private static func escapeForJSString(_ text: String) -> String {
        var result = ""
        for scalar in text.unicodeScalars {
            switch scalar {
            case "\\": result += "\\\\"
            case "\"": result += "\\\""
            case "\n": result += "\\n"
            case "\r": result += "\\r"
            case "\u{2028}": result += "\\u2028"
            case "\u{2029}": result += "\\u2029"
            default: result.unicodeScalars.append(scalar)
            }
        }
        return result
    }
}

enum Digest {
    /// 与安卓 MessageDigest("SHA-256") + %02x 拼接完全一致的十六进制摘要，
    /// 缓存文件名保持同一算法，桌面端/安卓端缓存可直接对照。
    static func sha256Hex(_ string: String) -> String {
        SHA256.hash(data: Data(string.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}

extension String {
    /// URLEncoder.encode(text, "UTF-8") 的等价物。
    var wwwFormUrlEncoded: String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        return addingPercentEncoding(withAllowedCharacters: allowed) ?? self
    }
}
