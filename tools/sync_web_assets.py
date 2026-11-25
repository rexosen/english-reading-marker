#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把安卓那份 Web 资源同步成 iOS 的 WebResources，保持「一套页面，两个壳」。

为什么要这个脚本而不是复制一份进 ios/ 提交：
    安卓壳的页面在 android/app/src/main/assets/，桌面版与安卓版的阅读逻辑同源。
    如果 iOS 再拷一份进仓库，三处页面会各自漂移，改一处要记着改三处。
    所以 iOS 的 bundle 资源由本脚本在构建前生成，产物目录不入库。

用法：
    python Tools/sync_web_assets.py            # 正常同步，打印差异
    python Tools/sync_web_assets.py --quiet    # 构建脚本用，只在变化时打印
    python Tools/sync_web_assets.py --check    # 只校验是否已同步（CI 用，不一致退出码 1）

注意路径：本项目在中文目录下（D:\\ChatGPT迁移\\...）。安卓的 build_android.py 用
Path.absolute() 而不是 resolve() 是为了绕开 aapt2 对中文路径的问题；这里全用
Python 的 pathlib + shutil，Windows/macOS/Linux 都安全，但 --check 输出里避免打印
带反斜杠的路径，防止日志被当成转义序列。
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 安卓壳里的页面 —— iOS 直接复用同一批文件
ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets"
TARGET = ROOT / "ios" / "WebResources"

# index.html 里按这个顺序加载三个脚本，同步顺序必须一致
PAGES = ["index.html", "sync-core.js", "learning.js", "app.js"]

# iOS 专属的桥接兼容层（不进 index.html，由原生当 user script 注入）
SHIM_CANDIDATES = [ROOT / "ios" / "Web" / "ios-shim.js", TARGET / "ios-shim.js"]

# ECDICT 离线词库：安卓放在 assets 里，iOS 放进 bundle 资源目录
DICTIONARY = ASSETS / "dictionary.sqlite3"

# 平台文案差异：只在 iOS 副本里改写，安卓原件不动
TEXT_FIXES = {
    "app.js": [
        # app.js:18 —— 原生桥不可用时的提示。iOS 上 ReaderNative 由 ios-shim.js 提供，
        # 只有 Safari 直接打开页面才会走到这句，文案得说清楚是「手机 App」而不是「安卓包」
        ("请使用安卓安装包打开", "请在手机 App 内打开本页面"),
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patched(name: str, data: bytes) -> bytes:
    for old, new in TEXT_FIXES.get(name, []):
        data = data.replace(old.encode("utf-8"), new.encode("utf-8"))
    return data


def collect() -> list[tuple[Path, Path, bytes]]:
    """返回 (源文件, 目标文件, 目标内容) —— 目标内容可能因 TEXT_FIXES 与源不同。"""
    if not ASSETS.is_dir():
        raise SystemExit(f"找不到安卓资源目录：{ASSETS}")
    plan: list[tuple[Path, Path, bytes]] = []
    for name in PAGES:
        source = ASSETS / name
        if not source.is_file():
            raise SystemExit(f"缺少页面文件：{source}")
        plan.append((source, TARGET / name, patched(name, source.read_bytes())))

    for candidate in SHIM_CANDIDATES:
        if candidate.is_file():
            plan.append((candidate, TARGET / "ios-shim.js", candidate.read_bytes()))
            break

    if DICTIONARY.is_file():
        plan.append((DICTIONARY, TARGET / DICTIONARY.name, DICTIONARY.read_bytes()))
    else:
        print(f"! 未找到离线词库 {DICTIONARY.name}，iOS 里查词将只走在线翻译", file=sys.stderr)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="同步安卓 Web 资源到 iOS WebResources")
    parser.add_argument("--quiet", action="store_true", help="只在有变化时输出")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args()

    plan = collect()
    changed: list[str] = []
    missing: list[str] = []

    for source, target, payload in plan:
        current = target.read_bytes() if target.is_file() else None
        if current == payload:
            continue
        (missing if current is None else changed).append(target.name)
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            # 词库 60 MB，写临时文件再改名，避免构建中途读到半截数据库
            temp = target.with_suffix(target.suffix + ".tmp")
            temp.write_bytes(payload)
            temp.replace(target)

    if args.check and (changed or missing):
        print("WebResources 与安卓源不一致，请先运行 Tools/sync_web_assets.py：")
        for name in missing:
            print(f"  缺失 {name}")
        for name in changed:
            print(f"  过期 {name}")
        return 1

    if not args.quiet:
        total = sum(len(payload) for _, _, payload in plan)
        if changed or missing:
            print(f"已同步 {len(plan)} 个文件 → {TARGET}")
            if missing:
                print("  新增：" + "、".join(missing))
            if changed:
                print("  更新：" + "、".join(changed))
            print(f"  bundle 内页面与词库共 {total / 1048576:.1f} MB")
        else:
            print(f"WebResources 已是最新（{len(plan)} 个文件，共 {total / 1048576:.1f} MB）")
        for name in TEXT_FIXES:
            if any(target.name == name for _, target, _ in plan):
                for old, new in TEXT_FIXES[name]:
                    print(f"  文案适配：{name} 「{old}」→「{new}」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
