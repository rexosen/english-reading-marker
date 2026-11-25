import Foundation
import AVFoundation

/// 全局播放代数：任何一次新的朗读/播放都会 +1，旧回调据此丢弃（对应安卓 audioGeneration）。
final class TokenJar {
    private var value = 0
    private let lock = NSLock()
    func bump() -> Int { lock.lock(); defer { lock.unlock() }; value += 1; return value }
    var current: Int { lock.lock(); defer { lock.unlock() }; return value }
}

let playbackTokens = TokenJar()

/// 系统英文语音（AVSpeechSynthesizer），对应安卓 MainActivity 的 TextToSpeech 分支。
///
/// 三个必须改的差异：
/// 1. 安卓 `setSpeechRate(0.9f)` 是相对正常语速的倍数，iOS 的 `rate` 是绝对值
///    （`AVSpeechUtteranceDefaultSpeechRate` ≈ 0.5），页面传 0.6~1.25 倍速要换算。
/// 2. iOS 的 `pauseSpeaking` 恢复后不一定停在原字符位置，因此沿用安卓的做法：
///    暂停时 stop 并记住已读偏移，继续时从该偏移重新 speak 剩余文本。
/// 3. 逐词高亮偏移来自 `willSpeakRangeOfSpeechString`，等价 `onRangeStart`。
final class SpeechEngine: NSObject, AVSpeechSynthesizerDelegate {

    weak var owner: Bridge?

    private let synthesizer = AVSpeechSynthesizer()
    private var generation = 0
    private var tag = ""
    private var spokenText = ""
    private var characters: [Character] = []
    private var baseOffset = 0
    private(set) var speechOffset = 0
    private var chunkEnd = 0
    private var speed: Double = 0.75
    private var accent = "us"
    private var paused = false

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    var isSpeaking: Bool { synthesizer.isSpeaking }

    /// 对应 speakSystem(text, accent, speed)
    func speak(text: String, accent: String, speed: Double, requestTag: String = "") {
        stop()
        self.accent = accent
        self.speed = speed
        generation = playbackTokens.current
        tag = requestTag
        characters = Array(text)
        spokenText = text
        if Self.pickVoice(accent: accent) == nil {
            let requestTag = tag
            tag = ""
            owner?.notice("未找到英文语音，请在系统的「设置 → 辅助功能 → 朗读内容」下载英语语音")
            owner?.speechDone(tag: requestTag, error: "未找到英文语音，请先下载英语语音包")
            return
        }
        speakFrom(offset: 0)
    }

    private func speakFrom(offset: Int) {
        let start = min(max(0, offset), characters.count)
        let remaining = String(characters[start...])
        baseOffset = start
        chunkEnd = start + remaining.count
        speechOffset = start
        paused = false
        guard !remaining.isEmpty else { complete(); return }

        let utterance = AVSpeechUtterance(string: remaining)
        utterance.voice = Self.pickVoice(accent: accent)
        utterance.rate = Self.rate(for: speed)
        utterance.pitchMultiplier = 1.0
        synthesizer.speak(utterance)
    }

    /// 倍速 → iOS 绝对语速：正常 0.5，按倍速线性缩放并夹到合法区间。
    static func rate(for speed: Double) -> Float {
        let normal = Double(AVSpeechUtteranceDefaultSpeechRate)
        return Float(min(1.0, max(0.2, normal * min(1.25, max(0.6, speed)))))
    }

    /// 口音 → 语音：en-US / en-GB，优先 Premium/Enhanced 高质量语音。
    static func pickVoice(accent: String) -> AVSpeechSynthesisVoice? {
        let identifier = accent == "uk" ? "en-GB" : "en-US"
        let pool = AVSpeechSynthesisVoice.speechVoices().filter { $0.language.hasPrefix(identifier) }
        if #available(iOS 13.0, *) {
            if let best = pool.min(by: { quality($0) < quality($1) }) { return best }
        }
        return AVSpeechSynthesisVoice(language: identifier) ?? AVSpeechSynthesisVoice(language: "en-US")
    }

    @available(iOS 13.0, *)
    private static func quality(_ voice: AVSpeechSynthesisVoice) -> Int {
        switch voice.quality {
        case .premium: return 0
        case .enhanced: return 1
        case .default: return 2
        @unknown default: return 3
        }
    }

    /// 对应 action=pause 的系统语音分支
    func togglePause() {
        if paused {
            speakFrom(offset: speechOffset)
            owner?.notice("继续朗读")
        } else if synthesizer.isSpeaking {
            paused = true
            synthesizer.stop(at: .word)
            owner?.notice("已暂停")
        }
    }

    /// 对应 action=stop / stopAudio() 的系统部分
    func stop() {
        playbackTokens.bump()
        generation = playbackTokens.current
        if synthesizer.isSpeaking { synthesizer.stop(at: .immediate) }
        paused = false
        speechOffset = 0
        baseOffset = 0
        chunkEnd = 0
        tag = ""
    }

    func pauseForBackground() {
        if synthesizer.isSpeaking { paused = true; synthesizer.stop(at: .word) }
    }

    // MARK: - AVSpeechSynthesizerDelegate

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                           willSpeakRangeOfSpeechString characterRange: NSRange,
                           utterance: AVSpeechUtterance) {
        guard generation == playbackTokens.current else { return }
        let local = max(0, min(characterRange.location, (utterance.sentence ?? "").count))
        speechOffset = baseOffset + local
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        guard generation == playbackTokens.current else { return }
        if chunkEnd < characters.count {
            speakFrom(offset: chunkEnd)
        } else {
            complete()
        }
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                           didFail utterance: AVSpeechUtterance,
                           error: AVSpeechSynthesisError) {
        guard generation == playbackTokens.current else { return }
        let requestTag = tag
        tag = ""
        owner?.notice("朗读失败，请检查手机英文语音设置")
        owner?.speechDone(tag: requestTag, error: "朗读失败，请检查英文语音设置")
    }

    private func complete() {
        speechOffset = 0
        paused = false
        let requestTag = tag
        tag = ""
        if requestTag.isEmpty { owner?.notice("朗读完成") }
        owner?.speechDone(tag: requestTag, error: "")
    }
}
