#!/bin/sh
# Install the quant-paper / quant-agent local client on macOS (Apple Silicon or Intel) for the current user.
# Writes two small wrappers into ~/.local/bin that run this folder's Python files with the system python3.
# No sudo, no Homebrew, no third-party package; the system OpenSSH does the transport.
#
#   sh install_macos.sh              install, check python3 / ssh / scp, print the PATH line if it is missing
#   sh install_macos.sh --add-path   also append the PATH line to ~/.zshrc (only if not present yet)
set -eu

HERE=$(cd "$(dirname "$0")" && pwd -P)
BIN="$HOME/.local/bin"

PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "找不到 python3。请先运行：xcode-select --install（安装 Apple 命令行工具，自带 python3），然后重新运行本脚本。" >&2
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "python3 版本过低（需要 3.9 或更新）：$("$PY" --version 2>&1)" >&2
  exit 1
fi
for t in ssh scp; do
  if ! command -v "$t" >/dev/null 2>&1; then
    echo "找不到 $t（macOS 自带 OpenSSH，位于 /usr/bin）。请检查 PATH：echo \$PATH" >&2
    exit 1
  fi
done
for f in quant_paper.py quant_agent.py; do
  if [ ! -f "$HERE/$f" ]; then
    echo "缺少文件：$HERE/$f（请把整个 quant_paper 文件夹复制到本机）" >&2
    exit 1
  fi
done

mkdir -p "$BIN"
write_wrapper() {   # $1 = command name, $2 = python file
  cat > "$BIN/$1" <<EOF
#!/bin/sh
# $1 local client wrapper (written by install_macos.sh; source folder: $HERE)
exec "$PY" "$HERE/$2" "\$@"
EOF
  chmod 755 "$BIN/$1"
}
write_wrapper quant-paper quant_paper.py
write_wrapper quant-agent quant_agent.py

echo "已安装：$BIN/quant-paper、$BIN/quant-agent（python3：$("$PY" --version 2>&1)，$(uname -m)）"
case ":$PATH:" in
  *":$BIN:"*) echo "PATH 已包含 $BIN。" ;;
  *)
    LINE='export PATH="$HOME/.local/bin:$PATH"'
    if [ "${1:-}" = "--add-path" ]; then
      if ! grep -qsF "$LINE" "$HOME/.zshrc"; then
        printf '\n# quant-paper / quant-agent\n%s\n' "$LINE" >> "$HOME/.zshrc"
      fi
      echo "已把 PATH 设置写入 ~/.zshrc。请运行：source ~/.zshrc（或重新打开终端）。"
    else
      echo "PATH 里还没有 $BIN。请运行下面一行，或重新运行本脚本并加 --add-path："
      echo "  echo '$LINE' >> ~/.zshrc && source ~/.zshrc"
    fi
    ;;
esac
echo "下一步：quant-paper setup --host <主机> --port <端口> --user <用户> --identity ~/.ssh/<私钥文件>"
