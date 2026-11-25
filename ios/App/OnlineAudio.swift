import Foundation
import AVFoundation

/// 在线发音播放（单词取有道音频、整句取 Google 或电脑 edge-tts 中转），
/// 对应安卓 MainActivity 的 startSpeech/playOnlineChunk/fallbackOnline 调用链。
///
/// MediaPlayer → AVAudioPlayer；安卓 `PlaybackParams().setSpeed()` → iOS
/// `enableRate = true; rate = speed`（同为变速，默认不做音高补偿）。
/// 想要“变速不变调”就换成 AVAudioEngine + AVAudioUnitVarispeed，
/// 对外接口不变（README「可选升级」一节给了写法）。
final class OnlineAudio: NSObject, AVAudioPlayerDelegate {

    weak var owner: Bridge?
    var notice: (String) -> Void = { _ in }
    var finished: (String, String) -> Void = { _, _ in }
    /// (text, accent, single) -> 已落地的 mp3 文件 URL
    var pronunciationProvider: ((String, String, Bool) throws -> URL)?
    /// 在线通道全挂时的兜底：交给系统语音读剩余文本
    var systemFallback: ((String, String, Double) -> Void)?

    private var player: AVAudioPlayer?
    private var generation = 0
    private var tag = ""
    private(set) var pausedByUser = false
    private var chunks: [String] = []
    private var chunkIndex = 0
    private var accent = "us"
    private var speed: Double = 0.75
    private var single = false

    /// 是否占用了在线播放通道（决定 action=pause 走在线分支还是系统分支）
    var isActive: Bool { player != nil || !chunks.isEmpty }

    /// 对应 startSpeech(source == "dictionary")
    func start(text: String, accent: String, speed: Double, requestTag: String) {
        stop()
        generation = playbackTokens.bump()
        tag = requestTag
        pausedByUser = false
        self.accent = accent
        self.speed = speed
        single = Self.isSingleWord(text)
        chunks = single ? [text] : Self.split(text)
        play(index: 0)
    }

    /// 对应 playOnlineChunk(chunks, index, accent, speed, generation, single)
    private func play(index: Int) {
        guard generation != 0, index < chunks.count else { finish(error: nil); return }
        chunkIndex = index
        let text = chunks[index]
        let generation = self.generation
        notice(single ? "正在载入词典发音…" : "正在载入在线整句语音…")

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            do {
                guard let provider = self.pronunciationProvider else { throw SyncError("发音服务暂不可用") }
                let file = try provider(text, self.accent, self.single)
                DispatchQueue.main.async {
                    guard self.generation == generation else { return }
                    if !self.startPlayback(file: file, index: index) {
                        self.fallback(index: index, generation: generation)
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    guard self.generation == generation else { return }
                    self.fallback(index: index, generation: generation)
                }
            }
        }
    }

    @discardableResult
    private func startPlayback(file: URL, index: Int) -> Bool {
        releasePlayer()
        guard let data = try? Data(contentsOf: file),
              let player = try? AVAudioPlayer(data: data) else { return false }
        player.delegate = self
        player.enableRate = true
        player.rate = Float(min(1.25, max(0.6, speed)))
        self.player = player
        chunkIndex = index
        if pausedByUser {
            notice("已暂停")
        } else {
            // AVAudioSession 已在 AppDelegate 配好（.playback + .spokenAudio），这里只起播
            guard player.play() else { return false }
            notice((single ? "词典发音" : "在线整句朗读") + " · \(speed) 倍速")
        }
        return true
    }

    /// 对应 fallbackOnline：用户处于暂停态时先等，否则用系统语音读剩余内容
    private func fallback(index: Int, generation: Int) {
        guard self.generation == generation, self.generation != 0 else { return }
        if pausedByUser {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
                guard let self, self.generation == generation else { return }
                self.fallback(index: index, generation: generation)
            }
            return
        }
        releasePlayer()
        let remaining = chunks.enumerated().filter { $0.offset >= index }.map(\.element)
            .joined(separator: " ")
        chunks = []
        notice("在线音频不可用，剩余内容改用系统语音")
        systemFallback?(remaining, accent, speed)
    }

    /// 对应 action=pause 的在线分支
    func togglePause() {
        guard let player else { return }
        if player.isPlaying {
            pausedByUser = true
            player.pause()
            notice("已暂停")
        } else {
            pausedByUser = false
            player.play()
            notice("继续发音")
        }
    }

    func stop() {
        playbackTokens.bump()
        generation = 0
        tag = ""
        pausedByUser = false
        chunks = []
        chunkIndex = 0
        releasePlayer()
    }

    func pauseForBackground() { player?.pause() }
    func resumeFromBackground() { if let player, !pausedByUser { player.play() } }

    private func releasePlayer() {
        player?.stop()
        player?.delegate = nil
        player = nil
    }

    private func finish(error: String?) {
        let requestTag = tag
        tag = ""
        chunks = []
        releasePlayer()
        finished(requestTag, error ?? "")
    }

    // MARK: - AVAudioPlayerDelegate

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        guard !chunks.isEmpty else { return }
        let next = chunkIndex + 1
        guard next < chunks.count else { finish(error: nil); return }
        play(index: next)
    }

    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        fallback(index: chunkIndex, generation: generation)
    }

    // MARK: - 文本分块（与 SpeechChunks.java 一致：180 字符内按最后一个空白断句）

    static func split(_ input: String) -> [String] {
        var chunks: [String] = []
        var text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        while !text.isEmpty {
            let characters = Array(text)
            var end = min(180, characters.count)
            if end < characters.count {
                var boundary = -1
                for index in 0..<end where characters[index].isWhitespace { boundary = index }
                if boundary > 0 { end = boundary }
            }
            chunks.append(String(characters[0..<end]))
            text = String(characters[end...]).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return chunks
    }

    /// 对应 isSingleWord：≤80 字符且为单词/撇号/连字符组成的词
    static func isSingleWord(_ text: String) -> Bool {
        guard text.count <= 80 else { return false }
        return text.range(of: "^[A-Za-z]+(?:['\u{2019}\\-][A-Za-z]+)*$", options: .regularExpression) != nil
    }
}
