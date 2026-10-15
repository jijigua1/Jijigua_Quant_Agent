# macOS使用指南

## 两类Python要求

客户端使用Python3.9+和系统SSH/SCP，Intel/Apple Silicon共用Python核心。离线Agent数值环境使用Python3.11/3.12，不要把客户端最低版本误读成整个研究引擎支持Python3.9。

```bash
python3 --version
command -v ssh scp
sh tools/quant_paper/install_macos.sh
```

安装脚本只给当前用户`~/.local/bin`写两个包装器；默认不改`.zshrc`。需要时显式使用`--add-path`，检查其追加行。先人工SSH核验服务器指纹，才运行setup。macOS真机验收本次未进行，跨平台模拟测试及未来CI不等于真机证据。

```bash
quant-paper setup --host gpu.example.org --port 22 --user YOUR_LOGIN --identity ~/.ssh/research_ed25519
quant-paper upload "$HOME/Documents/Papers/example.pdf"
quant-paper upload "$HOME/Documents/Papers/"
quant-paper list
quant-agent chat
```

zsh会展开未加引号通配符；若希望由Python展开，可给整个通配路径加引号。空格和中文路径要加引号。引用中使用`$HOME`可明确展开，避免将某个私人Windows盘符写入配置。

客户端配置位于`~/.config/quant-paper/config.json`，权限应仅当前用户可读写；不包含密码。API Key在服务端隐藏输入。不要把私钥、Key、config.json或论文全文提交GitHub。

上传去重、最近论文、参数批准、恢复、报告下载及临时盘备份语义与Windows相同，见[Windows指南](WINDOWS.md)。`quant-agent chat --resume SESSION_ID`恢复当前有权访问的会话；普通新会话不应自动获得所有人的研究。

## 离线引擎

按README使用Python3.12创建venv并安装core/research锁文件。只做客户端不必安装NumPy/Pandas或PDF依赖。需要PDF解析时先阅读PyMuPDF许可；本仓库不附带商业字体或受限PDF。

## 故障边界

Keychain/SSH agent是否有可用私钥由用户管理；不要用自动接受主机指纹解决认证错误。Ctrl+C或SSH断线后远程任务是否停止需要服务端合同，当前不保证后台持续或全部子进程回收。本次没有运行macOS真实SSH、安装器修改或真机研究，相关结论保留UNVERIFIED。
