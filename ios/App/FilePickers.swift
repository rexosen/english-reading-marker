import UIKit
import UniformTypeIdentifiers
import PhotosUI

/// 文件/图片选择与导出，对应安卓的 ACTION_OPEN_DOCUMENT / ACTION_CREATE_DOCUMENT + onActivityResult。
///
/// Intent(42/43/44/45) → UIDocumentPickerViewController / PHPickerViewController。
/// BitmapFactory(inSampleSize) → UIGraphicsImageRenderer 缩放；
/// compress(JPEG, 78) → jpegData(quality: 0.78)；阈值与错误文案保持完全一致，
/// 这样 JS 侧不用改（它只看返回的 `image` data URL 或 `error` 文本）。
final class FilePickers: NSObject {

    private weak var host: ReaderViewController?
    private var presented: AnyObject?
    private var completion: (([String: Any]) -> Void)?
    private var exportPayload: String?
    private var exportSuccess = ""
    private var exportFailure = ""

    var busy: Bool { presented != nil }

    init(host: ReaderViewController?) {
        self.host = host
    }

    // MARK: - 背景图（对应 request==43）

    func pickImage(_ done: @escaping ([String: Any]) -> Void) {
        guard let host else { return done(["error": "无法打开文件选择器"]) }
        if #available(iOS 14.0, *) {
            var config = PHPickerConfiguration()
            config.filter = .images
            config.selectionLimit = 1
            let picker = PHPickerViewController(configuration: config)
            arm(picker) { result in
                switch result {
                case .images(let data):
                    ImageEncoder.encode(data) { payload in done(payload) }
                case .files(let urls):
                    guard let url = urls.first, let data = try? ImageEncoder.read(url) else {
                        done(["error": "图片无法读取"]); return
                    }
                    ImageEncoder.encode(data) { done($0) }
                case .cancelled:
                    done(["cancelled": true])
                }
            }
            host.present(picker)
        } else {
            let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.image], asCopy: true)
            picker.allowsMultipleSelection = false
            arm(picker) { result in
                switch result {
                case .files(let urls):
                    guard let url = urls.first, let data = try? ImageEncoder.read(url) else {
                        done(["error": "图片无法读取"]); return
                    }
                    ImageEncoder.encode(data) { done($0) }
                case .images, .cancelled:
                    done(["cancelled": true])
                }
            }
            host.present(picker)
        }
    }

    // MARK: - 导入备份 JSON（对应 request==44）

    func pickJSON(_ done: @escaping ([String: Any]) -> Void) {
        guard let host else { return done(["error": "无法打开文件选择器"]) }
        let jsonType = UTType(filenameExtension: "json") ?? .json
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [jsonType, .plainText], asCopy: true)
        picker.allowsMultipleSelection = false
        arm(picker) { result in
            switch result {
            case .files(let urls):
                guard let url = urls.first else { done(["cancelled": true]); return }
                do {
                    let text = try FileRead.limitedText(from: url, limit: 15_000_000)
                    done(["data": text])
                } catch {
                    done(["error": error is SyncError ? error.localizedDescription : "文件无法读取"])
                }
            case .images, .cancelled:
                done(["cancelled": true])
            }
        }
        host.present(picker)
    }

    // MARK: - 导出（对应 request==42 CSV / 45 备份 JSON）

    func export(text: String, suggestedName: String, type: UTType, success: String, failure: String) {
        guard let host else { return }
        exportPayload = text
        exportSuccess = success
        exportFailure = failure
        let picker = UIDocumentPickerViewController(forExporting: [URL(fileURLWithPath: suggestedName)],
                                                    asCopy: false)
        arm(picker) { _ in }          // 导出只弹提示，不回 JS（与安卓一致）
        host.present(picker)
    }

    private func arm(_ picker: UIViewController, _ done: @escaping (PickerOutcome) -> Void) {
        let driver = PickerDriver(host: host, outcome: done)
        presented = driver
        if let picker = picker as? UIDocumentPickerViewController {
            picker.delegate = driver
        } else if let picker = picker as? PHPickerViewController {
            picker.delegate = driver
        }
        driver.onDismiss = { [weak self] in self?.presented = nil }
    }
}

enum PickerOutcome {
    case files([URL])
    case images(Data)
    case cancelled
}

/// 真正的 delegate 持有者：iOS 的 picker delegate 是 weak，必须自己保活。
final class PickerDriver: NSObject, UIDocumentPickerDelegate, PHPickerViewControllerDelegate {

    private weak var host: ReaderViewController?
    private let outcome: (PickerOutcome) -> Void
    var onDismiss: (() -> Void)?

    init(host: ReaderViewController?, outcome: @escaping (PickerOutcome) -> Void) {
        self.host = host
        self.outcome = outcome
    }

    // UIDocumentPickerViewController
    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        let secured = urls.map { url -> URL in
            url.startAccessingSecurityScopedResource()
            return url
        }
        outcome(.files(secured))
        secured.forEach { $0.stopAccessingSecurityScopedResource() }
        release()
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        outcome(.cancelled); release()
    }

    // PHPickerViewController（相册）
    @available(iOS 14.0, *)
    func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
        picker.dismiss(animated: true)
        guard let item = results.first?.itemProvider else { outcome(.cancelled); release(); return }
        if item.canLoadObject(ofClass: UIImage.self) {
            item.loadObject(ofClass: UIImage.self) { [weak self] object, _ in
                guard let self else { return }
                if let image = object as? UIImage, let data = image.jpegData(compressionQuality: 0.92) ?? image.pngData() {
                    DispatchQueue.main.async { self.outcome(.images(data)); self.release() }
                } else {
                    DispatchQueue.main.async { self.outcome(.cancelled); self.release() }
                }
            }
        } else {
            outcome(.cancelled); release()
        }
    }

    private func release() {
        DispatchQueue.main.async { self.host?.dismiss(animated: true) { self.onDismiss?() } }
    }
}

enum FileRead {
    /// readAll(input, limit) 的等价物：超过上限就报同样的中文提示
    static func limitedText(from url: URL, limit: Int) throws -> String {
        let attributes = try? FileManager.default.attributesOfItem(atPath: url.path)
        if let size = attributes?[.size] as? Int, size > limit { throw SyncError("数据过大，请分批导入") }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var data = Data()
        while true {
            let chunk = handle.readData(ofLength: 8192)
            if chunk.isEmpty { break }
            data.append(chunk)
            if data.count > limit { throw SyncError("数据过大，请分批导入") }
        }
        guard let text = String(data: data, encoding: .utf8) else { throw SyncError("文件无法读取") }
        return text
    }
}

enum ImageEncoder {
    static func read(_ url: URL) throws -> Data {
        let accessed = url.startAccessingSecurityScopedResource()
        defer { if accessed { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url), !data.isEmpty else { throw SyncError("图片无法读取") }
        return data
    }

    /// 最长边 ≤1600、JPEG 质量 78、成品 ≤900 KB —— 与安卓 BitmapFactory+compress 的参数一致
    static func encode(_ data: Data, _ done: @escaping ([String: Any]) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            guard let image = UIImage(data: data) else {
                DispatchQueue.main.async { done(["error": "图片无法读取"]) }; return
            }
            guard image.size.width > 0, image.size.height > 0 else {
                DispatchQueue.main.async { done(["error": "图片无法读取"]) }; return
            }
            let longest = max(image.size.width, image.size.height)
            let scale = longest > 1600 ? 1600.0 / longest : 1.0
            let target = CGSize(width: max(1, floor(image.size.width * scale)),
                                height: max(1, floor(image.size.height * scale)))
            let format = UIGraphicsImageRendererFormat.default()
            format.scale = 1
            let resized = UIGraphicsImageRenderer(size: target, format: format).image { _ in
                image.draw(in: CGRect(origin: .zero, size: target))
            }
            guard let jpeg = resized.jpegData(compressionQuality: 0.78) else {
                DispatchQueue.main.async { done(["error": "图片无法读取"]) }; return
            }
            if jpeg.count > 900_000 {
                DispatchQueue.main.async { done(["error": "图片过大，请选择较小的图片"]) }; return
            }
            let payload = "data:image/jpeg;base64," + jpeg.base64EncodedString()
            DispatchQueue.main.async { done(["image": payload]) }
        }
    }
}
