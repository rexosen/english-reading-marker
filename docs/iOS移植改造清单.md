# iOS 移植改造清单（安卓壳 → iPhone 壳）

源程序：`英语阅读标记器 / EnglishReadingMarker`
- 桌面版：Python 3.14 + PySide6（`src/`，同时是局域网同步**服务端**，端口 18765）
- 手机版：安卓壳 = `WebView` + JS↔Java 桥（`android/app/src/main/`，v1.7 / versionCode 8）
- 新增 iOS 壳 = `WKWebView` + JS↔Swift 桥（`ios/`，本清单逐条对照）

一句话结论：**页面（`index.html` / `app.js` / `learning.js` / `sync-core.js`）和桌面服务端一行都不用改**；
要改的全在「原生壳」这一层——安卓那 444 行 `MainActivity.java` 换成 11 个 Swift 文件，
外加 3 处平台硬限制（签名、存储可回收、iOS 18 本地网络授权）。

---

## 一、必须改的：原生 API 一一对应表

| 能力 | 安卓（`MainActivity.java`） | iOS（`ios/App/`） | 改动性质 |
|---|---|---|---|
| JS 调原生 | `web.addJavascriptInterface(bridge,"ReaderNative")` → JS 里直接 `ReaderNative.send(id,action,json)` | `WKScriptMessageHandler` + `window.webkit.messageHandlers.ReaderNative.postMessage({id,action,body})`；`postMessage` 只收**一个**对象参数 | **需注入兼容层** `ios/Web/ios-shim.js`，保持三参数签名，页面代码不动 |
| 原生回 JS | `web.evaluateJavascript("window.nativeReply(...)")` | `evaluateJavaScript` + `String(format:)`；返回值需 JSON 转义 | 等价（用 `JSON.jsLiteral` 防注入） |
| 页面加载 | `loadUrl("file:///android_asset/index.html")` | 无 `android_asset` 等价物；`loadFileURL` 对相对子资源授权不稳 | **改成内置 `127.0.0.1` 静态服务器** `WebServer.swift`（NWListener，支持 Range） |
| 系统朗读 | `TextToSpeech` + `UtteranceProgressListener.onRangeStart` 拿高亮偏移；`setSpeechRate(0.9f)` 是**倍率** | `AVSpeechSynthesizer` + `willSpeakRangeOfSpeechString` 拿偏移；`AVSpeechUtterance.rate` 是**绝对语速**，默认 0.5 | **必改**：倍率→绝对语速换算 `rate = 0.5 × speed`（0.5 为常速），见 `SpeechEngine.rate(for:)` |
| 继续朗读 | `tts.stop()` 后从头 `speak()` | `pauseSpeaking` 后**不能可靠恢复位置** | **必改**：按 `speechOffset` 截取剩余文本重新 `speak` |
| 音频播放 | `MediaPlayer` + `PlaybackParams().setSpeed()` | `AVAudioPlayer` + `enableRate = true; rate = speed` | 等价；需激活 `AVAudioSession .playback/.spokenAudio` |
| 音频焦点/后台 | `AudioAttributes(USAGE_MEDIA)` + Service | `UIBackgroundModes: [audio]` + Session 中断通知 | **必改**：plist 声明 + `AppDelegate` 里配置 session |
| 本地词库 | `SQLiteDatabase.openDatabase(getFilesDir()+"/dictionary.sqlite3", OPEN_READONLY)`，60 MB ECDICT 从 assets 拷出 | 系统只有 C 库：`sqlite3_open_v2` + 自建 `CSQLite` modulemap（`ios/CHeaders/`） | **必改**：`-lsqlite3` + `module.modulemap` + 构建时从 SDK 拷 `sqlite3.h`；SQL 与键算法不变 |
| 局域网同步 | `HttpURLConnection` + `isSiteLocalAddress()` 白名单 | `URLSession` + `DesktopSync.isPrivateAddress`（同网段判定） | 等价，**但必须加 ATS 例外** `NSAllowsLocalNetworking`（明文 HTTP 否则被系统拦截） |
| 在线翻译 | `translate.googleapis.com/translate_a/single?client=gtx` | 同一 URL，`URLSession` | 等价 |
| 单词发音 | 有道 `dict.youdao.com/dictvoice?audio=&type=1/2` | 同一 URL | 等价 |
| 整句发音 | Google `translate_tts?...&client=tw-ob` | 同一 URL | 等价；600 s「Google 可用」冷却逻辑照搬 |
| 桌面神经语音 | `POST http://<PC>:18765/tts`（edge-tts 缓存） | 同一路径，`DesktopSync.desktopTts` | 等价，**iOS 18 需本地网络授权** |
| 选背景图 | `ACTION_OPEN_DOCUMENT`(image/\*) + `BitmapFactory` 采样 ≤1600 + JPEG q78 + >900 KB 报错 | `PHPickerViewController`(iOS 14+) / `UIDocumentPicker` + `UIGraphicsImageRenderer` + `jpegData(0.78)` | 等价，阈值与中文错误文案保持完全一致 |
| 导入/导出 | `ACTION_CREATE_DOCUMENT`，CSV 带 `\ufeff` BOM | `UIDocumentPicker(forExporting:)` + `UTType` | 等价，BOM 保留（Excel/Numbers 都需要） |
| 返回键 | `onBackPressed()` → `window.handleBack()` | 无系统返回键 | **必改**：左边缘滑动 `UIScreenEdgePanGestureRecognizer` → 同一段 JS |
| 系统栏 | `setDecorFitsSystemWindows(false)` + inset padding | `additionalSafeAreaInsets` + `contentInsetAdjustmentBehavior = .never` | 等价（底色同为 `#f4f6fa`） |
| 存储 | `localStorage` 落在 app 私有目录，系统不清 | `localStorage` 属 WebKit 可回收网站数据，**会被系统抹掉且无报错** | **必改**：新增原生镜像 `StorageMirror.swift` + `Bridge` 的 `storage` 分支 + documentStart 回填 |
| 桌面文件分享 | 安卓走局域网同步 | iOS 无「文件夹」概念 | 不变（同步协议两端一致，桌面是服务端） |
| 打包 | `android/build_android.py`（aapt2 + d8 + apksigner，纯命令行、Windows 可跑） | 必须 macOS + Xcode：`xcodegen generate` → `xcodebuild` | **必改**：构建机换成 Mac（或云端 Mac / CI）；签名走 Apple ID |

---

## 二、不是「改代码」但躲不掉的三件事

1. **签名与安装**
   安卓产出可直接安装的 `.apk`；iPhone 必须签名描述文件。没有 Mac/Apple ID 就只有三条路：
   免费 Apple ID（7 天过期、最多 3 个 App）、付费开发者账号（¥688/年，1 年不过期）、
   第三方签名服务（有隐私风险，不推荐）。详见 `docs/iOS签名与安装.md`。
   ⇒ **这台 Windows 不能生成能装进 iPhone 的产物**，只能生成源码和资源。

2. **`localStorage` 会被系统回收**
   文章、标注、生词本、备份快照都在 `reader-v1` / `listening-v1` / `reader-backups-v1` 里（可达十几 MB）。
   iOS 存储紧张或用户「清除网站数据」时整包消失。所以 iOS 壳每次写入都镜像一份到
   `Application Support/storage-mirror.json`（不参与 iCloud 备份以外的清理），启动时回填。
   这是 iOS 独有的一层，安卓没有也不需要。

3. **iOS 18 本地网络权限**
   「连接电脑」按钮走 `http://192.168.x.x:18765`，iOS 18 首次会弹「允许访问本地网络上的设备」。
   点了拒绝不会报错，只会一直「连接超时」。需在 `Info.plist` 提供 `NSLocalNetworkUsageDescription`，
   并且要告诉用户去 **设置 → 英语阅读标记器 → 本地网络** 打开。

---

## 三、新增/改动的文件

新增（iOS 壳，全在 `ios/`）：

```
ios/App/AppDelegate.swift            音频会话、场景委托
ios/App/ReaderViewController.swift   WKWebView 容器、边缘滑动返回
ios/App/Bridge.swift                 ReaderNative 消息处理：pair/sync/translate/speak/pause/stop/
                                     chooseBackground/importBackup/export/exportBackup
                                     + iOS 新增 storage / platform 两个分支
ios/App/WebServer.swift              127.0.0.1 静态服务器（替代 android_asset）
ios/App/SpeechEngine.swift           AVSpeechSynthesizer（语速换算 + 偏移续读）
ios/App/OnlineAudio.swift            AVAudioPlayer + 倍速 + 失败回落系统语音
ios/App/DictionaryStore.swift        系统 sqlite3 只读查词
ios/App/DesktopSync.swift            URLSession + 局域网地址白名单 + /pair /sync /translate /tts
ios/App/FilePickers.swift            PHPicker/DocumentPicker + 图片压缩 + 导出
ios/App/StorageMirror.swift          localStorage 原生镜像（iOS 专属）
ios/App/JSONSupport.swift            org.json 等价物 + SHA-256 缓存键（与安卓同算法）
ios/Web/ios-shim.js                  桥兼容层 + 写回钩子（唯一的页面侧文件）
ios/CHeaders/module.modulemap        CSQLite 模块声明
ios/Resources/LaunchScreen.storyboard 启动底色（替代安卓 splash）
ios/App/Info.plist                   ATS / 本地网络 / 后台音频 / 权限文案
ios/App/EnglishReadingMarker.entitlements
ios/project.yml                      XcodeGen 工程描述（不提交 .xcodeproj）
ios/build_ios.sh                     Mac 上一条龙构建
ios/README.md                        构建、签名、装机
```

新增（跨端工具）：

```
tools/sync_web_assets.py             安卓 assets → ios/WebResources（含 1 处文案替换）
docs/iOS移植改造清单.md              本文件
docs/iOS签名与安装.md                没有 Mac 时的三条路
```

改动（非新增，就一处页面文案）：

```
android/app/src/main/assets/app.js:18 「请使用安卓安装包打开」
  → iOS 副本里改成「请在手机 App 内打开本页面」
  由 tools/sync_web_assets.py 在同步时替换，安卓源文件不动
```

不改的（这是移植的前提）：

```
src/*.py（桌面版 = 同步服务端，18765 协议不变）
android/app/src/main/assets/index.html、app.js、learning.js、sync-core.js
android/app/src/main/java/**（安卓壳继续独立演进）
```

---

## 四、验收对照（把安卓上的行为逐条在 iPhone 上比一遍）

| 场景 | 期望 |
|---|---|
| 导入文章、划词、标句、生词本 | 与安卓一致，重启不丢 |
| 单词发音（源=词典） | 有道 mp3 命中缓存 → 秒播；倍速 0.6/0.75/0.9/1/1.25 听得出差异 |
| 整句发音（源=系统） | 逐词高亮跟随；暂停后继续**从中断处**读，不从头 |
| 整句发音（源=联网） | Google mp3；无网时提示「在线音频不可用，剩余内容改用系统语音」 |
| 连电脑（同 Wi-Fi） | 配对码 6 位 → token；断网重连不覆盖本地（instance 不一致时提示「电脑身份不同…」） |
| 系统存储被清理 | 打开 App 数据仍在，提示「已按本机备份恢复数据」 |
| 导出 CSV | Excel/Numbers 打开不乱码（BOM） |
| 左滑返回 | 从阅读页退回列表页，与安卓返回键一致 |
