#!/bin/zsh
# PYVoiceAgent Mac signer / importer. No third-party tools or installation.
set -euo pipefail
echo "PYVoiceAgent · 一键签名并导入快捷指令"
if ! command -v shortcuts >/dev/null 2>&1; then
  echo "错误：当前 macOS 没有 shortcuts 命令。请检查系统更新。"
  read -r "?按回车关闭..."
  exit 1
fi
INPUT=$(osascript -e 'set f to choose file with prompt "选择从 iPhone 分享来的 .unsigned.shortcut 文件"' -e 'return POSIX path of f')
if [[ "$INPUT" != *.unsigned.shortcut ]]; then
  echo "必须选择 PYVoiceAgent 生成的 .unsigned.shortcut 文件。"
  read -r "?按回车关闭..."
  exit 1
fi
OUTPUT="${INPUT%.unsigned.shortcut}.shortcut"
if [[ -e "$OUTPUT" ]]; then
  echo "已存在同名签名文件，为安全起见不覆盖：$OUTPUT"
  open -R "$OUTPUT"
  read -r "?按回车关闭..."
  exit 1
fi
echo "苹果签名中（可能需要 Mac 登录 iCloud）..."
if shortcuts sign --input "$INPUT" --output "$OUTPUT" --mode anyone; then
  echo "签名完成：$OUTPUT"
  echo "即将打开苹果快捷指令，请在 Mac 上确认添加。"
  echo "完成后，启用 iCloud 的快捷指令同步，iPhone 会收到新快捷指令。"
  open "$OUTPUT"
else
  echo "签名失败：请检查 Mac iCloud 账户及快捷指令 App。"
  read -r "?按回车关闭..."
  exit 1
fi
read -r "?按回车关闭..."
