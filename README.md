# 英语阅读标记器 (English Reading Marker)

英语阅读学习工具：Windows 桌面版 + Android 版，导入文章、点词查释义、拖选整句翻译、划线标记、生词本导出、学习进度统计，手机与桌面通过局域网双向同步。

## 功能概览
- 导入/粘贴 UTF-8 文本文章；保存后按字符位置精确记录划线。
- 内置 ECDICT 离线词典（768,739 条中文释义），单词本地秒查；句段翻译走 Google/MyMemory 在线接口并持久缓存。
- 美式/英式发音，四档语速；单词音频取自有道词典并按需缓存，句段使用系统 TTS / edge-tts。
- 生词本独立窗口，支持释义、来源原句与 CSV（UTF-8 BOM，Excel 友好）导出。
- 学习视图：分句、分组、笔记、复习评分（`src/study.py` / `study_ui.py` / 安卓 `learning.js`）。
- 听力训练（Windows 与安卓）：逐句“听懂/没听懂”自评与“只重听没听懂句”，听写练习按词对照并给出准确率，0.6–1.25 五档语速。
- 生词本（Windows 与安卓）：单击条目即朗读该词或词组（词典真人发音优先，断网回落系统/神经网络语音）；自定义分类＋内置「听力／阅读」两类，筛选实时计数；可多选批量归类，右键菜单或 Delete 键删除；「＋ 加入词组」直接录入单词/词组、释义和例句（带 ✎，可再编辑），不必先在文章里划词。CSV 导出跟随当前筛选并带“分类”列。
- 逐句快捷键（Windows）：焦点在正文时，空格＝暂停/继续朗读，↑＝上一句，↓＝下一句，←／→＝重复当前句（按设定的"遍"数再念一遍），1＝1 倍速、2＝0.75 倍速；逐句切换时正文自动跟随高亮句滚动，光标同步落到当前句；带修饰键的方向键（Shift/Ctrl）与 PageUp/PageDown 保持原有选择与滚动行为。
- 安卓与 Windows 局域网同步：文章、划线、生词、阅读位置双向同步；6 位一次性配对码，凭证只存哈希，操作按 ID 去重。
- 数据固定存放于 `%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`，每天首次打开自动快照备份。

## 版本与下载
- 最新安装包见 [Releases](https://github.com/rexosen/english-reading-marker/releases)：Windows 桌面版 v1.4.0、Android 版 v1.8（详见下方最新更新记录）。
- 完整演进记录见下方各版本小节。

## 快速开始
依赖 Python 3 与 PySide6。开发版从项目根目录运行：

```powershell
python -m src.main
```

## 离线词典（可选）
本地秒查依赖 `assets/dictionary.sqlite3`（由 ECDICT 转换而来，约 58 MB，不随仓库分发）。缺失时应用自动改用在线翻译，其余功能不受影响。构建方法：

1. 从 https://github.com/skywind3000/ECDICT 下载 `stardict.csv`（完整版）或 `ecdict.mini.csv`（精简版）。
2. 运行 `python tools/build_dictionary.py <csv路径>`，默认生成 `assets/dictionary.sqlite3`。

Windows/Android 打包脚本会自动引用该文件。ECDICT 采用 MIT 许可，见 `assets/ECDICT-LICENSE.txt`。

## 关键路径
- `src/`：Windows 桌面版代码（PySide6）
- `android/`：Android 版源码与构建脚本
- `tests/`：自动化测试
- `tools/`：词典构建等辅助脚本
- `docs/`：验证记录与功能说明
- `EnglishReadingMarker.spec` / `build_windows.ps1`：Windows 打包

## Windows 打包
创建 `.venv` 并安装 `requirements.txt` 后，在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\build_windows.ps1
```

可通过 `-DeliveryPath` 指定运行包输出目录。

打包脚本会移除 Qt wheel 中与当前 Windows ICU 不匹配的副本，运行时使用 Windows 系统 ICU。

## 下一步
可继续迭代词典质量、阅读字号设置、文章编辑后的划线维护等体验。首版自动化测试为 30 项，均通过，`src/` 行覆盖率 91%；已在当前 Windows 11 上启动桌面包并验证示例文章。

## 第二版（2026-10-23）
- 阅读区右键单词直接显示释义；左键拖选或右键拖选句子/段落后，右键松开直接翻译。
- 内置 ECDICT 768,739 条有中文释义的词条，本地单词查询无需等待网络；在线译文持久缓存。
- 英文语音使用 Windows SAPI，支持所选词句段落、全文、暂停/继续和停止。
- 句段翻译使用 Google 公共翻译接口，失败时尝试 MyMemory；公共接口可能受网络或限流影响。发送的是用户所选内容。
- 保留原有文章、精确位置划线、词表与 CSV 数据。
- 37 项自动化测试通过；实测本地 online 约 1ms，首次句段翻译约 0.8–1.2 秒（本机当时网络），不构成延时保证。
- ECDICT 来源：https://github.com/skywind3000/ECDICT，许可证随包附带。

## 第三版（2026-10-23）
- 修复长英文选区标题扩大最小宽度、挤压左侧文章列表和阅读区的问题。标题可换行，右侧限宽 240–360，译文独立滚动。
- 生词本移至独立非模态窗口，主窗口点击“生词本”打开；支持释义、来源原句和 CSV 导出。
- 新增长句布局回归测试、独立生词本窗口测试，39 项测试全部通过。

## 第四版（2026-10-23）
- 左侧文章列表右键“重命名”，弹出预填原名的输入框。取消或空名不会修改文章。
- 按稳定文章 ID 更新标题，保留正文、划线、生词和当前阅读选区；生词来源标题同步更新。
- 44 项测试全部通过，新增覆盖保存、取消、空名、非当前文章和关联数据保留。

## 安卓 / 局域网同步第一版（2026-10-23）
- Android 8.0+ 签名 APK，原生 Activity + 本地 WebView 阅读界面、本地词库与系统英文 TTS；采用此实现避免给首版引入 Flutter 完整工具链，后续可保留协议更换客户端。
- Windows 手机同步入口：显式开启服务、显示可选局域网地址和一次性配对码、提供 APK 下载页。
- SQLite 增量添加同步元数据与触发器，保留旧 ID/正文/标记；首次实际升级前自动备份。
- 操作队列和本地快照原子保存；服务端按操作 ID 去重，完整快照响应，避免同步数据库文件。
- 文章创建/重命名、位置划线、生词、阅读位置双向同步；标题版本冲突需手机明确选择。
- 手机前台每3秒同步，Windows 每1.5秒轮询变化；每次重启桌面版需手动开启服务，不承诺安卓后台同步。
- 配对码6位，10分钟一次性使用，配对尝试限速；持久凭证只在服务端存哈希；仅局域网 IP；HTTP 用于可信任家庭网络。
- 53项 Python 测试通过，src 行覆盖率86%；手机界面 E2E 使用真实隔离 HTTP 服务和模拟原生桥接，不代表安卓真机验证。
- APK 实际编译、v2/v3 签名通过；当前 adb 未连接设备，手机系统语音/选择菜单/权限尚需真机确认。

### Android 构建
官方 SDK 工具放于 work/android-sdk；JDK17 可通过 --jdk 指定。运行 `python android/build_android.py --output <APK路径>`。脚本自动使用 Windows 短路径兼容 AAPT2。签名密钥与密码在 work/android-signing，不能提交或分发；后续升级需保留签名材料。

### 同步验证
`python -m unittest discover -s tests`；`node tests/mobile_e2e.cjs`（需要 Node.js 与 `npm install playwright`，使用本机 Chromium 与 Playwright，隔离测试资料库）。

## 发音改进 1.1（2026-10-23）
- 默认美式词典发音、0.75倍速。英/美切换，0.6/0.75/0.9/1.0四档可选；句段使用可调速系统英文语音。
- 单词音频按需从有道词典HTTPS取用，验证MP3格式并本机缓存；不批量抓取。公共音频入口可用性依赖服务端，失败会提示并降级为慢速系统语音。
- Android MediaPlayer/Windows QMediaPlayer播放缓存音频；新请求、停止、关闭会取消旧音频，避免异步下载后串音。
- Android发音设置迁移保留reader-v1本地数据与配对；版本码2，包名和签名与1.0相同，可覆盖安装。
- Windows设置写入资料库同目录audio.ini，手机设置写入本地状态，均不改变同步协议。
- 60项Python测试通过，src覆盖率85%；手机E2E验证美式默认、设置持久化和语音参数桥接。Windows实际MP3播放1440ms文件，0.75速率，Playing→Stopped，无错误；安卓原生音频仍需真机试听。
- 来源：https://dict.youdao.com/w/online/ 及其词典音频；Qt/Android系统播放器接口。


## 2026-10-24：桌面版 1.2 资料恢复与存储修复

- 原因：由 MSIX 打包的 Codex 启动时，AppData 被重定向到包的 LocalCache；由桌面启动时读取另一份同名数据库。旧程序对空库自动导入示例，掩盖了数据目录分叉。
- 固定主库：`%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`，不再依据 LOCALAPPDATA 选择资料库。词典翻译缓存、词典音频与发音设置也使用该目录。
- 首次迁移先用 SQLite 在线备份保存每份可读取的旧主库，再以文章较完整的一份作为基础，保留原同步实例编号、已配对设备及文章编号，合并其他当前主库里的额外文章、划线和生词。迁移通过临时文件完成后替换目标文件。
- 已存在的固定主库不会在每次启动被旧库覆盖；损坏或读取失败会提示错误并停止，不重置为空库。真正首次使用才插入示例。
- 每天首次打开自动生成 SQLite 快照；菜单“数据与备份”可以查看位置、打开目录和手动备份。没有自动删除备份。
- 本次真实资料恢复：4 篇文章（含用户改名“模拟听力3”）、1 处划线、0 条生词；保留原手机配对与同步身份。另一份只有 1 篇的升级前备份也单独保留。原主库均未删除。
- 未执行本次新增自动化测试；实际恢复结果、运行包启动和列表另行记录。未连接安卓真机验证本次同步。

实际启动确认：Windows_LAN_v1.2 运行包窗口显示四篇文章及“数据与备份”菜单，桌面快捷方式指向该运行包。


## 2026-10-24：学习功能版（Windows 1.3 / Android 1.2）

新增 `src/study.py`（分句、分组/笔记/复习存储、评分规则）、`src/study_ui.py`（Qt学习窗口）、安卓 `learning.js` 与原生图片/JSON选择桥接。`study_items` 以稳定文章编号和字符位置定位，通过持久操作队列同步，删除使用墓碑；并发笔记编辑保留分支副本。分组/已读/置顶/复习按最后提交合并。显示配置及压缩背景图各设备独立保存。
Windows恢复：预览→用户确认→备份当前→暂存→退出→下次启动前恢复；保留当前配对凭证及已确认操作，提升同步修订号。QLockFile防止同版多实例同时打开库。安卓保留最多7个本机快照及独立JSON导入导出，恢复保留当前配对信息并先备份现状。
交付说明在当前任务 outputs/学习功能版_使用说明.md。Windows实际启动看到4篇文章与新控件；安卓编译签名及脚本语法/包内容检查完成，尚未进行本次安卓真机验证。本次未运行自动化测试，未在用户主库执行回滚恢复。


## 2026-10-24：Windows 1.3.1 正文宽度修复

用户截图指出1.3阅读框居中后只剩约256逻辑像素宽。原因：QVBoxLayout对单个QTextEdit设置AlignHCenter后采用sizeHint，setMaximumWidth只设上限，不强制填充。修复为独立水平布局，编辑器取得水平伸展，达到用户设定宽度上限后由两侧弹性空白居中。未更改正文、划线、字号、背景或同步资料，安卓无需更新。

1.3.1实际运行确认：最终运行包已打开，正文恢复正常宽度，四篇文章可见，桌面快捷方式已更新。

## 2026-10-26：Windows 1.3.2 阅读布局
压缩应用标题栏，正文工具栏合并为一行；保留翻译、划线、加生词，朗读/学习/设置使用菜单。朗读菜单可展开逐句控制；专注阅读临时隐藏两侧栏。侧栏默认200/240，新增空间优先分给正文。修改测试中列表刷新后失效的旧QListWidgetItem引用，改为检查当前列表项。隔离资料库验证普通/专注布局与逐句控件，60项测试通过（最终标题伸展修正后另行复跑）。交付目录：2026-10-26/ti/outputs/Windows_LAN_v1.3.2。
最终标题布局修正后60项测试再次全部通过；原生Windows Qt窗口预览已检查。桌面快捷方式已切换至1.3.2。


## 2026-10-27：安卓1.3整句在线语音
单词保留词典音频，句段、全文、逐句接入Google在线语音，分段缓存及失败回退系统。设置说明文本发送。交付 outputs/英语阅读标记器_安卓整句语音版_v1.3.apk；验证边界见 docs/安卓整句语音验证.md。

## 2026-11-03：Windows 1.3.3 听力训练增强
- 逐句控制新增“✓ 听懂 / ✗ 没听懂”自评与“只重听没听懂句”开关：标记绑定文章编号与句子位置，正文编辑后旧标记自动失效；开启后上一句/下一句/自动推进只在没听懂的句子间跳转。自评保存在本机资料目录 `listening_reviews.json`，不进入手机同步数据。
- 新增“听写练习（当前文章）”（“学习”菜单与“学习与阅读”菜单）：隐藏原文逐句播放，手敲听写内容，对照时按词标注写错（红色下划线）与漏写（红色方括号），忽略大小写、标点与撇号差异，给出每句与平均准确率。
- 发音设置增加 1.25 倍速，用于高于考场语速的抗干扰训练；朗读状态栏改为显示当前实际倍速。
- 听写词级对照（`src/dictation.py`）与自评存储（`src/listening.py`）为独立可测模块；75 项测试全部通过（新增听写 7 项、自评 6 项、窗口集成 2 项）。本次仅 Windows；安卓端于同日 1.6 版补齐，见下节。

## 2026-11-03：安卓 1.6 听力训练移植
- 逐句控制新增“✓ 听懂 / ✗ 没听懂”自评与“只重听没听懂句”开关（`learning.js`）：标记存 localStorage 独立键 `listening-v1`，不进同步 outbox，不影响电脑端数据；按文章 ID + 句子范围 + 原文校验，正文编辑后旧标记自动失效；开启后上一句/下一句/自动推进只在没听懂句之间跳转。
- 新增“⌨ 听写”浮层：隐藏原文逐句播放，手敲后按词对照（红下划线=写错、红方括号=漏写、多写词单列），给出本句与平均准确率；判分算法 `dictationCompare` 与桌面 `src/dictation.py` 在四个用例上逐词一致。
- 发音设置新增 1.25 倍速档；`MainActivity` 速度钳制放宽到 1.25，在线整句（setPlaybackParams）、词典单词与系统 TTS 全通道生效。
- 交付 [v1.6 Release](https://github.com/rexosen/english-reading-marker/releases/tag/v1.6)（versionCode 7，v2/v3 签名，与 v1.5 同密钥可覆盖安装）；Windows v1.3.3 zip 内嵌 APK 同步更新至 1.6，手机从电脑“下载手机版”即得新版。
- `tests/mobile_e2e.cjs` 扩展听力训练段：自评落盘、outbox 不变、只重听从没听懂句开始、听写满分与错词判定；360/393px 布局无溢出，Chromium 桥端到端通过。

## 2026-11-08：Windows 1.3.4 逐句快捷键
- `ReadingTextEdit` 新增 `speech_toggle_requested` 与 `sentence_step_requested` 两个信号，并在 `keyPressEvent` 中只拦截**无修饰键**的空格与 ↑/↓：空格接 `pause_speech`（句间等待、系统 TTS、神经网络语音、单词音频四条通道都走原逻辑），↑/↓ 接新增的 `keyboard_sentence_step`——逐句尚未启动时从光标所在句开始，已启动时按 `_sentence_order()` 上下句切换（“只重听没听懂句”开启时仍只在没听懂句之间跳）。
- 带 Shift/Ctrl 的 ↑↓ 与 PageUp/PageDown 原样交回 `QTextEdit`，选择与滚动行为不变；正文为只读，空格本无编辑用途。
- 逐句控制提示文案补充快捷键说明。新增 2 项窗口集成测试（信号发射与修饰键透传、从光标起步再步进），全套 84 项测试通过。
- 交付目录 `outputs/Windows_LAN_v1.3.4`，资料库沿用 `%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`，与 1.3.3 同一份数据，无需迁移。本次仅 Windows，安卓端未改动。

## 2026-11-10：Windows 1.3.5 逐句跟随滚动 + ←/→ 重复当前句
- **修 bug：↑/↓ 换句时正文不跟着滚。** 根因在 `_play_sentence()`：高亮句先用 `setTextCursor(extra.cursor)` 设为当前句、调 `ensureCursorVisible()`，紧接着又 `setTextCursor(cursor)` 把光标**同步还原**到上一句的位置——Qt 的这次还原会把滚动条拽回旧光标处，实测 `ensureCursorVisible` 的滚动被完全抵消（一篇 18 句的文章里 16 句"有声无画"，滚动条从第 2 句起一直钉在 4px）。同一段里还留着 `scroll=self.reader.verticalScrollBar().value()` 这个取了不用的死变量，是当初想保滚动没保成的痕迹。
- 新增 `_reveal_sentence(start, end)`：高亮 + 滚动一步做完，**不再还原光标**——光标随当前句移动（双击查词、听写起步、`jump_to_range` 都以光标为准，跟读时落到当前句更一致）。滚动不用 `ensureCursorVisible()`（它只保证"光标那一行"可见，而且是 `QTimer::singleShot(0)` 延后的，长句会被切一半），改为用 `QTextEdit.cursorRect()` 量出句子首行顶边与末行底边在视口中的位置，超出就按 28px 内边距（视口很矮时退化为高度的 1/6）直接写 `verticalScrollBar()`，同步步进、可预测；整句比视口还高时改保首行在顶部。`ensureCursorVisible()` 只在视口高度为 0（窗口尚未布局）时兜底。
- **新功能：←／→ 重复当前句。** `ReadingTextEdit` 增 `sentence_repeat_requested` 信号，`keyPressEvent` 里只拦截**无修饰键**的 Left/Right（Ctrl+←/→ 仍按词跳、Shift+←/→ 仍扩选，PageUp/PageDown 不受影响）；接新增的 `keyboard_sentence_repeat()`：正在逐句时按 `_sentence_round=0` 重念当前句、句号不变（"遍"数仍按控制面板设置走）；空闲或一轮已结束时，从光标所在句起步重念——↑/↓ 之后光标就跟句，所以 ←/→ 重复的正是耳朵里那句。重复前先 `stop_audio()`，避免 TTS 队列叠加。
- 提示文案补齐 `←／→＝重复当前句`。新增 3 项窗口集成测试（逐句全篇滚动能让每句留在视口内且只向前推进、←/→ 发信号且修饰键透传、重复不换句且空闲时按光标定位），全套 87 项测试通过。
- 交付目录 `outputs/Windows_LAN_v1.3.5`，资料库沿用 `%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`，与 1.3.4 同一份数据，无需迁移。本次仅 Windows，安卓端未改动。

## 2026-11-10：Windows 1.3.6 生词本分类、删除与单击朗读
- **单击朗读**：`VocabularyList.itemClicked` → `speak_vocabulary_word()` → 复用 `_speak()` 通道（有道词典真人音频优先，失败自动回落系统/神经网络语音）；右键菜单里另有“▶ 朗读本词”。
- **分类**：新增 `src/vocabulary.py`，一词一分类，取值顺序为**手动归类 > 文章自动归类**。自动归类按文章标题前缀判定（`听力:`／`阅读:`／`Listening:`／`Reading:`，半角全角冒号均可），标题没前缀时回退用文章所在分组名，因此按 AGENTS.md 规范导入的文章**不需要任何操作就已在「听力」「阅读」两类里**；内置两类不落库、不可改名或删除。手动归类记录写进 `study_items`（`vcat:<百分号编码的词>`，`vgroup:<uuid>` 存自定义分类），大小写与空格不敏感、同一个词跨文章共享一条记录，因此**沿用现有 study 同步通道，不改表结构**：`set_study` 的键语法放宽到 `(group|meta|note|review|vgroup|vcat):[A-Za-z0-9:_~.%-]+` 并允许删除 `vgroup`/`vcat`，`vcat` 分支只校验分类存在、不绑定文章。分类名比较忽略空白（“必 背”＝“必背”），重名直接复用已有分类。
- **删除**：`ReaderRepository.delete_vocabulary(ids)` 批量删除；`lan_sync` 补 `sync_word_remove` 触发器，删除同样写 `sync_journal`，版本号上升后手机端 `sync-core.js` 用快照整表覆盖 `articles`（含 `vocabulary` 数组），**手机上这些生词随之消失**；只删生词记录，文章里的划线保留。UI 支持 Ctrl/Shift 多选后按钮删除、右键删除、Delete 键删除（`QListWidget` 没有 `deletePressed`，故用 `VocabularyList` 子类把 Del/Backspace 转成信号），删除前确认并说明同步后果。
- **筛选与导出**：窗口顶部新增分类下拉（全部分类／听力／阅读／自定义／未分类，实时计数）、新建／重命名／删除分类、移到分类…；列表项尾部显示 `[听力]` 一类徽标，计数行显示“共 N 条 · 当前分类 M 条”；CSV 增加“分类”列并只导出当前筛选结果。
- 新增 10 项 `tests/test_vocabulary.py` 单元用例与 6 项窗口用例（自动归类、手动优先、跨文章共享、清除回落、内置分类保护、删除后同步版本上升、Del 键、导出跟随筛选），全套 103 项测试通过。
- 交付目录 `outputs/Windows_LAN_v1.3.6`，资料库沿用 `%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`，旧库无需迁移（分类是新增的 `study_items` 记录，`vocabulary` 表结构未变）。本次仅 Windows，安卓端只被动接收新记录，未改动。

## 2026-11-10：Windows 1.3.7 + 安卓 1.7 生词本可自建词组，功能两端对齐
- **数据层**：`vocabulary.article_id/start/end` 改为可空（`_allow_manual_vocabulary()` 在建表后检查 `PRAGMA table_info`，非空才重建表；重建前自动 `backup_database`，DROP 掉的同步触发器由紧随其后的 `initialize_sync()` 重新创建，旧库原地升级、行数据与 id 全保留）。SQLite 的 `UNIQUE(article_id,start,end)` 不约束 NULL，所以自建词条与文章词条天然共存。新增 `add_manual_vocabulary()`（折叠空白、大小写不敏感查重、最长 200 字）与 `update_vocabulary()`（**只有自建词条能改写法**，文章词条的文字与划线位置绑定，改它会让位置校验失效，因此只允许改释义和例句）。`list_vocabulary()` 改 LEFT JOIN 并带出 `manual` 标记。
- **复习不落下词组**：`study_items` 新增 `review:manual:<生词编号>` 记录格式（`set_study` 里独立分支校验编号确实指向一条自建词条，评分/间隔/到期字段与文章词一致），`review_cards()`／`grade()` 两端共用；`vcat:` 键语法与安卓对齐——Python 用 `quote(word.casefold(), safe='')`，JS 用 `encodeURIComponent` 再补 `!'()*`，`don't`、`e.g.`、`50%`、`what (really)!` 等 10 个刁钻写法在两端算出**同一个编号**，测试里两侧断言同一批字面量。
- **同步协议**：快照新增 `vocabulary_manual` 数组（自建词条不属于任何文章，因此单列）；新增 `vocabulary_manual`／`vocabulary_manual_remove`／`vocabulary_remove`（按 start/end 删文章里的生词）三种操作，均按 op_id 去重；补 `sync_word_change` 触发器，改释义也会提升版本号。旧版手机收到多出来的键会忽略，旧版电脑收到 `vocabulary_manual` 会明确报“不支持的操作”，不会写坏数据。
- **安卓 1.7**（versionCode 8，与 1.5/1.6 同一签名密钥，可覆盖安装）：生词本页重写——顶部「＋ 加入词组」「分类管理」，分类 chips（全部／听力／阅读／自定义／未分类，带计数），点卡片任意位置即朗读该词（原来只有小喇叭按钮），删除按钮走 `vocabulary_remove`/`vocabulary_manual_remove` 并同步回电脑，自建词条带 ✎ 且可编辑；分类规则与桌面同一套 JS 实现（`vocabCategoryOf`：手动优先，其次标题前缀，再次文章分组名）；复习卡片把自建词条一起排进队列（还没同步到编号时先记本机并提示）；CSV 增加“分类”列；文章里“存生词”不再限制只能单个单词，最长 6 个词的词组也能记（与桌面一致）。`sync-core.js` 负责快照替换与未发操作重放，`learning.js` 的备份校验/恢复同时带上 `vocabulary_manual`。
- 构建脚本 `android/build_android.py` 改用 `Path(__file__).absolute()` 而非 `resolve()`，这样可以通过 `subst` 映射的 ASCII 盘符构建（aapt2 在含中文的项目路径下会 `failed to open directory`，8.3 短名在该卷不可用时旧代码就卡在这里）。
- 测试：桌面 117 项全过（新增词组迁移、查重、编辑锁、复习编号、同步操作、分类与安卓编码对齐等）；安卓新增 `tests/mobile_vocabulary.test.cjs`（8 项，纯 Node，无需浏览器）；`tests/mobile_e2e.cjs` 补生词本端到端段（加入词组→点卡片朗读→分类筛选→CSV→电脑端收到→手机删除→电脑端同步删除），该脚本依赖 playwright，本机未安装故**未执行**，仅静态检查通过。
- 交付：`outputs/Windows_LAN_v1.3.7`（桌面快捷方式已改指此目录，1.3.6/1.3.5/1.3.4 保留可回滚）与 `outputs/EnglishReadingMarker_Android_v1.7.apk`（已复制为 v1.3.7 包内 `EnglishReader_Android_v1.apk`，手机“下载手机版”即得新版）。

## 2026-11-11：Windows 1.3.8 文章里可直接存词组、发音独立按钮、数字键调速
- **修 bug：文章里划了词组仍存不进生词本**（上一版只放宽了安卓端和“＋ 加入词组”手工入口，桌面端从正文划词这条路径还卡在 `find_selected_word` 的单词校验上，提示“请只选择一个完整的英文单词”）。`src/domain.py` 新增 `find_selected_phrase()`：允许最多 6 个词的词组（词内支持连字符、撇号、数字、点，如 `newly-made plastic`、`don't give up`、`mp3 level`、`e.g. recycled plastic`），并把范围**收到文字本身**（拖选常带首尾空格），保证 `text[start:end] == word`，与 `add_vocabulary` 的位置校验严格一致；仍拒绝从单词中间截断的选区和更长的句子，提示改成“生词本可以记单词，也可以记最多 6 个词的词组；更长的句段请用收藏句段”。`_get_translation_selection()` 同步改为裁剪范围，`save_vocabulary()` 按**选中文字**（而不是位置元组）匹配已查到的释义，右键查词与“翻译所选”两条路径的释义都能接上。“划线”同样支持词组。
- **发音设置改成独立按钮**：工具栏“设置”右边新增大号按钮「🔊 发音」（最小 104×44，加粗内边距），直接打开“发音与语速”；原来藏在“朗读”二级菜单里的“发音设置”一项已移除，其余菜单项不变。
- **数字键调速**：`ReadingTextEdit` 新增 `speech_speed_requested` 信号，焦点在正文时按 **1＝1 倍速、2＝0.75 倍速**（只拦无修饰键，Ctrl/Shift＋数字仍走原功能）；接 `set_speech_speed()`，与「发音」按钮写的是同一份设置（`audio.ini` 的 `speed`），词典单词音频立刻变速，句子/全文从下一句起生效，重启后保持；状态栏提示当前倍速与快捷键含义。逐句控制提示文案补上 `1＝1 倍速，2＝0.75 倍速`。
- 测试：`Ran 127 tests OK`。新增 `tests/test_domain.py` 词组用例 5 项（多词、连字符/撇号/数字/点、空格裁剪、句子与半词拒绝、词数上限可调、`trim_range`）与 `tests/test_main_window.py` 4 项（词组存进生词本并带原句、词组划线、长句提示、发音按钮存在且直接打开对话框且菜单里已无该项、数字键调速与修饰键透传）。
- 交付目录 `outputs/Windows_LAN_v1.3.8`，资料库沿用 `%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`，无需迁移。安卓端词组限制上一版已放宽到 6 个词，两端一致。

## 2026-11-12：Windows 1.3.9 发音按钮单击只调速，不再弹窗
- **交互改动**：上一版「🔊 发音」按钮点一下就弹“发音与语速”窗口，实际使用时只想快点调速、不想被窗口打断。现在按钮**单击＝在 1 倍速与 0.75 倍速之间来回切**，不弹任何窗口；按钮文字直接写成当前倍速（`🔊 1 倍速`／`🔊 0.75 倍速`），一眼看清现在是什么速度。
- **设置窗口没删，挪到右键**：右键该按钮（`CustomContextMenu` → `open_audio_settings`）仍可打开“发音与语速”，改发音来源、美音/英音、0.6／0.9／1.25 倍速、句子与全文朗读声音；对话框里保存的其它倍速保存后按钮文字同步刷新，此时再点按钮会先回到 0.75 倍速，不会跳到别的档位。
- **实现**：新增 `toggle_speech_speed()` 与 `_refresh_audio_button_text()`；`set_speech_speed()` 增加 `hint` 参数，按钮、数字键 1／2、右键对话框三条路径写的仍是 `audio.ini` 里同一个 `speed`，词典单词音频立刻变速、句子与全文从下一句起生效、重启后保持；状态栏提示改为跟随入口给对应说明。
- 测试：`Ran 128 tests OK`。原“点按钮直接打开对话框”用例改为断言**单击不弹窗**且 1.0↔0.75 来回切、写盘、按钮文字跟随、0.6/0.9/1.25 先回落 0.75；新增右键打开发音与语速的用例。
- 交付目录 `outputs/Windows_LAN_v1.3.9`（桌面快捷方式已改指此目录，1.3.8 及更早保留可回滚），资料库沿用 `%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`，无需迁移。安卓端未改动。

## 2026-11-17：iPhone 版壳（ios/，页面与词库继续共用）
- **新增 iOS 原生壳**：`ios/` 用 `WKWebView` + `WKScriptMessageHandler` 复刻安卓壳的 14 项原生能力（朗读、倍速、在线发音、离线词库、局域网同步、翻译、图片背景、导入导出、返回手势等），Swift 共 11 个文件，逐条对照见 [docs/iOS移植改造清单.md](docs/iOS移植改造清单.md)。
- **页面零改动**：`index.html`／`app.js`／`learning.js`／`sync-core.js` 与 60 MB ECDICT 仍只有安卓那一份，构建前由 `tools/sync_web_assets.py` 同步进 `ios/WebResources/`；桥签名不变，靠注入的 `ios/Web/ios-shim.js` 把 `ReaderNative.send(id,action,json)` 翻译成 `postMessage({id,action,body})`。唯一文案差异：`app.js` 的「请使用安卓安装包打开」在 iOS 副本里替换为「请在手机 App 内打开本页面」。
- **iOS 特有的一处新增**：`StorageMirror` 把 `localStorage` 的 `reader-v1`／`listening-v1`／`reader-backups-v1` 镜像到 `Application Support/storage-mirror.json` 并在启动时回填——WebKit 的网站数据会被系统回收，不镜像就会出现「文章凭空消失」。桌面版与安卓版不涉及。
- **签名与装机**：iPhone 不能像安卓那样在 Windows 上直接出可装包，需 macOS + Xcode（免费 Apple ID 7 天 / 开发者账号 / AltStore 三条路），见 [docs/iOS签名与安装.md](docs/iOS签名与安装.md)；`ios/build_ios.sh` 一条命令生成工程并编译。
- 桌面版（同步服务端）与安卓版代码未改动，资料库仍是 `%USERPROFILE%/Documents/EnglishReadingMarker/reader.sqlite3`；测试仍 `Ran 128 tests OK`。iOS 壳需 macOS 编译，本仓库不含 `.xcodeproj`（由 `ios/project.yml` 生成）。

## 2026-11-25：Windows 1.4.0 + 安卓 1.8 综合修复与体验优化
- **修复 4 项明确缺陷**：
  - 安卓端编辑自建词组（只改释义/例句不改词）不再被静默忽略；改名时服务端按 `old_word` 原地更新，保留词条编号与 `review:manual:<id>` 复习记录。
  - 安卓端系统返回键优先关闭听写、编辑词组、分类管理、文章整理等动态浮层，不再切走底层页面。
  - 安卓端生词本「导出 CSV」改为跟随当前分类与搜索筛选结果，与 Windows 一致。
  - 双端听写练习按句号去重计分（同一句重复对照不再虚增句数与平均分）、转义 HTML、关闭听写窗口/浮层时自动停止朗读。
- **双端功能补齐**：
  - 双端支持删除文章（含同步 `delete` 操作）；Windows 端支持右键「编辑正文…」（自动清理位置失效的划线与生词）。
  - 双端生词本新增实时搜索框；Windows 生词本右键新增「回到原文」跳转。
  - 安卓阅读页新增「🔊 倍速」一键切换按钮（`1 倍速 ↔ 0.75 倍速`）。
  - Windows 端神经网络语音新增 15 秒超时保护与长文自动分段队列，全文朗读更快首播、不再卡死。
- **性能与存储优化**：
  - 局域网 `/sync` 轮询携带 `revision`，无变更时直接返回 `unchanged: true`，避免手机端每 3 秒全量拉取快照与重复写 `localStorage`。
  - Windows 端 Google 翻译增加 10 分钟失败冷却，避免国内网络每次句段翻译白等超时。
  - Windows 端「手机同步」支持勾选「下次启动自动开启局域网同步」。
  - 每日自动备份自动保留最近 30 份（不动手动/迁移备份）；双端均新增「清理语音缓存」入口；安卓 CSV/备份导出移至后台线程。
- **验证与交付**：Python 135 项测试全过、Node 8 项安卓生词/同步测试全过，`ios/WebResources` 已同步；交付 `outputs/Windows_LAN_v1.4.0`（内嵌安卓 v1.8 APK，桌面快捷方式已更新）与 `outputs/EnglishReadingMarker_Android_v1.8.apk`（versionCode 9）。

## 许可
MIT License，见 [LICENSE](LICENSE)。离线词典数据来自 [ECDICT](https://github.com/skywind3000/ECDICT)（MIT）。样例文章及用户导入的文章内容版权归原出处所有，分发或公开使用时请注意排除受版权保护的文章文本。
