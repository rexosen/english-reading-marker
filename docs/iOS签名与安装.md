# 把 iOS 工程文件跑起来（构建 / 签名 / 装机）

## 0. 这台 Windows 能做到的与做不到的

| 步骤 | Windows | macOS |
|---|---|---|
| 改原生代码、改页面 | ✅ | ✅ |
| 同步页面资源到 `ios/WebResources` | ✅ `python tools\sync_web_assets.py` | ✅ |
| 编译成 `.app` | ❌ 没有 `xcodebuild`/`swiftc` | ✅ |
| 签名 | ❌ `codesign` 只在 macOS | ✅ |
| 装进 iPhone | ⚠️ 只能靠 AltStore / Sideloadly 自签 | ✅ Xcode 直装 |

本机实测：`xcodebuild`、`swift`、`pod` 均不存在；`iTunes 12.13.12.3` 与
`Apple Mobile Device Support 20.0.1.47` 已安装（说明驱动链路在，但没有可编包的工具链）。
⇒ **必须找一台 Mac**（自有的、借的、或云端租的）。

---

## 1. 准备（一次性）

```sh
xcode-select --install                       # 命令行工具
brew install xcodegen python@3.12            # 生成工程 + 同步脚本
```
Xcode 里 Settings → Accounts 登录你的 Apple ID（免费账号即可真机调试）。

## 2. 出包

```sh
cd <项目>/ios
python3 ../tools/sync_web_assets.py          # 也可省，build_ios.sh 会自动做
./build_ios.sh                               # → build/DerivedData/.../EnglishReadingMarker.app
```

只想在 Xcode 里点运行：
```sh
./build_ios.sh --open
```
打开后 target → Signing & Capabilities：
- Team 选你的 Apple ID
- Bundle Identifier 保持 `cn.readingdesk.reader.ios`（**必须是 globally unique 的**，
  如果你的 Apple ID 下已有同名 App ID，改成你自己的域名反写，例如 `com.yourname.reader.ios`，
  同时改 `project.yml` 里的 `PRODUCT_BUNDLE_IDENTIFIER`）
- 插上 iPhone → 手机上「信任此电脑」→ 顶部设备下拉选中它 → Run（⌘R）

不想用 XcodeGen 也可以手动建工程：Xcode → New Project → iOS App（Storyboard 模板随意，
删掉模板的 ViewController），把 `ios/App/*.swift`、`ios/Resources`、`ios/WebResources`
（用 **Create folder references** 方式拖入，蓝色文件夹）加进 target，
Build Settings 里加：
- `SWIFT_INCLUDE_PATHS = $(SRCROOT)/CHeaders`
- `OTHER_LDFLAGS = -lsqlite3`
- `iOS Deployment Target = 16.0`
Info.plist 用 `ios/App/Info.plist` 覆盖即可。

## 3. 装到没连 Mac 的手机

- **免费账号**：7 天后 App 打不开。解决：重连一次 Mac 打开 App；或用
  AltServer（Windows 版叫 AltStore/Sideloadly）在手机/电脑上下 7 天内自动续签。
- **付费开发者账号（¥688/年）**：Arch → Export → Ad Hoc 或 App Store 分发；
  TestFlight 内测 90 天有效，别人也能装。
- **完全没有 Mac**：用云端 Mac（MacStadium / AWS EC2 Mac / 腾讯·阿里的 macOS 云主机）
  跑一次 `build_ios.sh`，把 `.app` 打包成 `.ipa`（`xcrun altool --validate-app` 可选），
  再交给 Sideloadly 在 Windows 上自签安装。

## 4. 常见失败与判断

| 现象 | 原因 | 处理 |
|---|---|---|
| `No signing certificate "iOS Development" found` | 钥匙串没有 Apple Development 证书 | Xcode → Accounts → Manage Certificates → + |
| `WebResources/index.html` 找不到 → App 里弹「缺少 WebResources/index.html」 | 忘了同步，或拖入工程时用了黄色 group 而不是蓝色 folder reference | 跑 `tools/sync_web_assets.py`；用 *folder references* 重新加入 |
| 「连接电脑」一直超时 | ATS 缺 `NSAllowsLocalNetworking`；或 iOS 18 未给「本地网络」权限；或不在同一 Wi-Fi / 路由器开了 AP 隔离 | 见 `docs/iOS移植改造清单.md` 第二节第 3 条 |
| 查词每次都走在线翻译 | `dictionary.sqlite3` 没进 bundle，或首次拷贝失败 | 检查 bundle 里有 58 MB 的 `WebResources/dictionary.sqlite3` |
| 朗读没有英文声音 | 系统未下载英文语音 | 设置 → 辅助功能 → 朗读内容 → 语音 → 英语 下载（Enhanced/Premium 更好） |
| App 装好但图标点开闪退 | 7 天签名过期 | 重连 Xcode 或 AltStore 续签 |

## 5. 回滚

iOS 这套全部在 `ios/` + `tools/sync_web_assets.py` + 两份文档里，
`src/`（桌面）与 `android/`（安卓壳）没有任何改动 —— 不要 iOS 版直接删 `ios/` 即可，
不会留下悬空引用。
