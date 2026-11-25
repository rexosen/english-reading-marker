#!/bin/sh
# iPhone 版一键构建（只能在 macOS + Xcode 上跑；这台 Windows 只能产源码，见 ios/README.md）
#
#   ./build_ios.sh              # 生成工程 + 编译到 Debug-iphoneos
#   ./build_ios.sh --open       # 生成后用 Xcode 打开，方便点真机运行
#   ./build_ios.sh --ip <UDID>  # 直接装到已连接的真机
#
# 对应安卓那边的 android/build_android.py：同样是「一条命令出包」，
# 区别是 iOS 必须经过 Xcode 的代码签名，产物是 .app 而不是 .apk。

set -eu

cd "$(dirname "$0")"
ROOT=$(pwd)
BUNDLE_ID=cn.readingdesk.reader.ios
SCHEME=EnglishReadingMarker
CONFIG=Debug
DERIVED="$ROOT/build/DerivedData"

# 1) 依赖检查
need() {
	command -v "$1" >/dev/null 2>&1 || {
		echo "缺少 $1。$2" >&2
		exit 1
	}
}
need xcodebuild "请安装 Xcode（App Store）并执行：sudo xcode-select -s /Applications/Xcode.app"
need xcodegen "请执行：brew install xcodegen"
need python3 "请执行：brew install python（tools/sync_web_assets.py 需要）"

# 2) 页面与词库：和安卓共用同一份源
python3 ../tools/sync_web_assets.py

# 3) 系统 SQLite 头文件：跟着当前 SDK 走，不签进仓库
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
if [ ! -f "$ROOT/CHeaders/sqlite3.h" ]; then
	echo "→ 从 SDK 复制 sqlite3.h"
	cp "$SDK/usr/include/sqlite3.h" "$ROOT/CHeaders/sqlite3.h"
fi

# 4) 生成 .xcodeproj（产物不入库）
xcodegen generate --spec project.yml

# 5) 签名身份：优先钥匙串里的 Apple Development
IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null \
	| awk '/"Apple Development"/ {print $2; exit}' || true)
if [ -z "$IDENTITY" ]; then
	echo "! 钥匙串里没有 Apple Development 证书。"
	echo "  在 Xcode → Settings → Accounts 登录 Apple ID 后重试；"
	echo "  免费账号可以真机调试（7 天有效），详见 docs/iOS签名与安装.md"
fi

if [ "${1:-}" = "--open" ]; then
	open "$SCHEME.xcodeproj"
	exit 0
fi

echo "→ 编译 device 版（$CONFIG）"
xcodebuild \
	-project "$SCHEME.xcodeproj" \
	-scheme "$SCHEME" \
	-configuration "$CONFIG" \
	-sdk iphoneos \
	-destination "generic/platform=iOS" \
	-derivedDataPath "$DERIVED" \
	CODE_SIGN_STYLE=Automatic \
	developmentTeam="${DEVELOPMENT_TEAM:-}" \
	ONLY_ACTIVE_ARCH=NO \
	build

APP="$DERIVED/Build/Products/$CONFIG-iphoneos/$SCHEME.app"
[ -d "$APP" ] || { echo "编译产物缺失：$APP" >&2; exit 1; }
echo "✓ 已生成 $APP"
codesign -dv --entitlements - "$APP" 2>&1 | sed -n '1,24p'

# 6) 可选：直接装到真机（等价 adb install -r）
if [ "${1:-}" = "--ip" ]; then
	UDID=${2:?用法: ./build_ios.sh --ip <设备 UDID>（xcrun devicectl list devices 可查）}
	echo "→ 安装到 $UDID"
	xcrun devicectl device install app --device "$UDID" "$APP"
	xcrun devicectl device process launch --device "$UDID" "$BUNDLE_ID" || true
fi
