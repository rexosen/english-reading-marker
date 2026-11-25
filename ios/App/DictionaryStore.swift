import Foundation
import CSQLite

/// 本地 ECDICT 词库，对应安卓 `getFilesDir()/dictionary.sqlite3` + `SQLiteDatabase.OPEN_READONLY`。
///
/// 与安卓的差异（重要）：
/// - 安卓的资源打在 APK 里，必须先从 `assets/` 拷到 `getFilesDir()` 才能打开；
///   iOS 的 Bundle 就是普通文件目录，**可以直接以只读方式打开 bundle 里的 58 MB 词库**，
///   省掉首次启动那一次全量拷贝。只有直连失败（例如词库带 `-wal`、或资源被平铺到别处）
///   才退回「拷到 Application Support 再打开」这条安卓老路。
/// - 拷贝出来的那份标记「不加入 iCloud 备份」（安装包能重建，没必要占备份额度）。
/// - `SQLITE_OPEN_READONLY` 与安卓 `OPEN_READONLY` 对齐：绝不写库，避免只读目录里建 journal 失败。
final class DictionaryStore {

    /// 词库不可用时提示用户（对应 notice("本地词库尚不可用…")）
    var onUnavailable: (String) -> Void = { _ in }

    private var handle: OpaquePointer?
    // 可重入锁：lookup() 里可能需要顺带触发首次安装
    private let lock = NSRecursiveLock()

    private static var copiedURL: URL {
        AppPaths.support.appendingPathComponent("dictionary.sqlite3")
    }

    /// bundle 里的词库位置：文件夹引用（蓝文件夹）与平铺两种打包形态都能找到
    private static func locateInBundle() -> URL? {
        if let url = Bundle.main.url(forResource: "dictionary", withExtension: "sqlite3") { return url }
        for directory in ["WebResources", "web", "assets"] {
            if let url = Bundle.main.url(forResource: "dictionary", withExtension: "sqlite3",
                                        subdirectory: directory) { return url }
        }
        guard let resources = Bundle.main.resourceURL else { return nil }
        for candidate in [resources.appendingPathComponent("dictionary.sqlite3"),
                          resources.appendingPathComponent("WebResources/dictionary.sqlite3")] {
            if FileManager.default.fileExists(atPath: candidate.path) { return candidate }
        }
        return nil
    }

    /// 对应 onCreate 里 executor.execute 的安装分支，懒执行一次
    func installIfNeeded() {
        lock.lock(); defer { lock.unlock() }
        if handle != nil { return }

        // 1) 先试直连 bundle，成功就不用拷 58 MB
        if let source = Self.locateInBundle(), open(source) { return }

        // 2) 失败再走安卓那条老路：拷到 Application Support
        let fm = FileManager.default
        if !fm.fileExists(atPath: Self.copiedURL.path) {
            guard let source = Self.locateInBundle() else {
                onUnavailable("本地词库尚不可用，可继续尝试在线翻译"); return
            }
            let staging = AppPaths.support.appendingPathComponent("dictionary.tmp")
            do {
                try? fm.removeItem(at: staging)
                try fm.copyItem(at: source, to: staging)
                try? fm.removeItem(at: Self.copiedURL)
                try fm.moveItem(at: staging, to: Self.copiedURL)
                var values = URLResourceValues()
                values.isExcludedFromBackup = true
                var url = Self.copiedURL
                try? url.setResourceValues(values)
            } catch {
                try? fm.removeItem(at: staging)
                // 上一步直连失败，这里也没有可打开的文件
                if !open(source) { onUnavailable("本地词库尚不可用，可继续尝试在线翻译") }
                return
            }
        }
        if !open(Self.copiedURL) { open(Self.locateInBundle() ?? Self.copiedURL) }
    }

    @discardableResult
    private func open(_ url: URL) -> Bool {
        if handle != nil { return true }
        var database: OpaquePointer?
        let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX
        if sqlite3_open_v2(url.path, &database, flags, nil) == SQLITE_OK, let database {
            handle = database
            return true
        }
        sqlite3_close(database)
        return false
    }

    /// 对应 dictionaryLookup(text)：命中返回释义，未命中/库不可用返回 nil
    func lookup(_ text: String) -> String? {
        let word = text.lowercased()
        guard word.count <= 100 else { return nil }
        lock.lock(); defer { lock.unlock() }
        if handle == nil { installIfNeeded() }        // 可重入锁，顺带完成首次安装
        guard let handle, let statement = prepare(handle, word) else { return nil }
        defer { sqlite3_finalize(statement) }
        if sqlite3_step(statement) == SQLITE_ROW, let column = sqlite3_column_text(statement, 0) {
            return String(cString: column)
        }
        return nil
    }

    private func prepare(_ handle: OpaquePointer, _ word: String) -> OpaquePointer? {
        var statement: OpaquePointer?
        let sql = "SELECT meaning FROM words WHERE word=?"
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK else { return nil }
        sqlite3_bind_text(statement, 1, word, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
        return statement
    }

    func close() {
        lock.lock(); defer { lock.unlock() }
        if let handle { sqlite3_close(handle) }
        handle = nil
    }
}
