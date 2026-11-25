# iPhone / iPad 版（ios/）

安卓壳的 iOS 对应物。页面（`index.html` / `app.js` / `learning.js` / `sync-core.js`）
和 58 MB 离线词库**仍然是安卓目录里那一份**，构建前由 `tools/sync_web_assets.py`
同步进 `WebResources/`；桌面版（同步服务端）代码零改动。

## 目录

```
ios/
├── App/                    11 个 Swift 文件 + Info.plist + entitlements
│   ├── AppDelegate.swift        场景/音频会话（对应 Application + Manifest）
│   ├── ReaderViewController.swift  WKWebView 宿主、返回手势、资源装载
│   ├── Bridge.swift               JS↔原生桥（对应 addJavascriptInterface("ReaderNative")）
│   ├── SpeechEngine.swift         AVSpeechSynthesizer（对应 TextToSpeech）
│   ├── OnlineAudio.swift          AVAudioPlayer + 倍速（对应 MediaPlayer + PlaybackParams）
│   ├── DictionaryStore.swift      sqlite3 只读词库（对应 SQLiteDatabase OPEN_READONLY）
│   ├── DesktopSync.swift          局域网 /pair /sync /translate /tts（对应 HttpURLConnection）
│   ├── FilePickers.swift          PHPicker / UIDocumentPicker（对应 ACTION_OPEN/CREATE_DOCUMENT）
│   ├── StorageMirror.swift        localStorage 本机镜像（iOS 新增，防系统回收）
│   ├── WebServer.swift            127.0.0.1 静态服务（对应 file:///android_asset/）
│   └── JSONSupport.swift          JSON / SHA-256 / URL 编码小工具
├── Web/ios-shim.js         唯一新增的 Web 侧文件：把 ReaderNative.send 翻译成 postMessage
├── Resources/              LaunchScreen.storyboard
├── CHeaders/module.modulemap   系统 sqlite3 的 Clang 模块（sqlite3.h 由 build_ios.sh 从 SDK 拷入）
├── project.yml             XcodeGen 工程定义（.xcodeproj 是构建产物，不入库）
├── build_ios.sh            一条命令：同步资源 → 生成工程 → 编译
└── WebResources/           构建产物（.gitignore），sync_web_assets.py 的输出目录
```

## 构建

需要 macOS + Xcode（本机是 Windows，只能改代码，出包必须去 Mac；
签名与装机的三条路见 [../docs/iOS签名与安装.md](../docs/iOS签名与安装.md)）。

```sh
brew install xcodegen
cd ios && ./build_ios.sh          # 产物在 ios/build/DerivedData/.../EnglishReadingMarker.app
./build_ios.sh --open             # 生成工程后用 Xcode 打开，插手机直接 Run
./build_ios.sh --ip <UDID>        # 编译后用 xcrun devicectl 装机并启动
```

不用 XcodeGen 的话，手工建工程也可以：把 `App/*.swift`、`Resources`、`WebResources`
以 **folder reference（蓝色文件夹）** 拖进 target，Build Settings 加
`SWIFT_INCLUDE_PATHS = $(SRCROOT)/CHeaders`、`OTHER_LDFLAGS = -lsqlite3`、
Deployment Target 16.0，Info.plist 指向 `App/Info.plist`。
代码里对「蓝文件夹」和「平铺到 Bundle 根」两种资源形态都做了兼容，不会因工程建法不同而白屏。

## 与安卓的差异，集中在一份清单里

逐条 API 对照、阈值、错误文案，以及三件「不是改代码但躲不掉的事」
（签名、WebKit 存储回收、iOS 18 本地网络权限）见
[../docs/iOS移植改造清单.md](../docs/iOS移植改造清单.md)。

## 已知未完成

- 未在真机上跑过（这台机器没有 macOS 工具链），Swift 侧只做了人工走查；
  首次编译大概要处理若干类型标注问题，逻辑分支已按安卓 1:1 对齐。
- 后台播放只在 `audio` 模式下锁屏可控，未做 CarPlay / 灵动岛。
- 未接 App Store 上架材料（截图、隐私标签、出口合规已用 `ITSAppUsesNonExemptEncryption=false` 占位）。
