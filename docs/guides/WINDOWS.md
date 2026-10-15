# Windows使用指南

## 本地计算与远程客户端是两件事

离线数值演示需要Python3.11/3.12与数值依赖；上传/远程客户端只需Python3.9+与Windows OpenSSH。先运行`python --version`、`ssh -V`，确认PowerShell中的命令来源。推荐在路径含空格或中文时用引号；不要把真实服务器信息提交到仓库。

完整离线安装见README。远程客户端可直接用`python tools/quant_paper/quant_paper.py help`，或把同目录两个cmd包装器加入个人PATH。包装器所在文件夹不能随意移动，否则应重新配置PATH。

## SSH与配置

先在自己的终端执行SSH，人工比对主机指纹，再用`setup --host ... --port ... --user ... --identity ...`保存非秘密连接参数。不要把口令写在命令行；使用私钥时保管好私钥文件。客户端默认BatchMode及StrictHostKeyChecking，身份未配好应报错而不是接受任意主机。

```powershell
python tools/quant_paper/quant_paper.py setup --host gpu.example.org --port 22 --user YOUR_LOGIN --identity C:/Keys/research_ed25519
python tools/quant_paper/quant_paper.py status
```

配置路径为当前用户APPDATA下的`quant-paper/config.json`；它不随仓库复制。项目不会自动修改全局MCP或Codex/Claude配置。

## 上传与论文库

```powershell
python tools/quant_paper/quant_paper.py upload "C:/Papers/example.pdf"
python tools/quant_paper/quant_paper.py upload "C:/Papers/a.pdf" "C:/Papers/b.pdf"
python tools/quant_paper/quant_paper.py upload "C:/Papers/*.pdf"
python tools/quant_paper/quant_paper.py list
```

同批先检查所有文件，不合格时整批不发。内容SHA去重，不按文件名判断；单篇网络错误会在汇总保留。重复上传更新最近上传指向，但不占用重复内容空间。“刚上传那篇”指本次最终成功登记的论文，批量后最好用标题或文件名点名。

## 研究、确认、恢复与报告

`python tools/quant_paper/quant_agent.py chat`启动服务器会话；隐藏输入官方Key，切勿把Key粘贴到研究问题。论文自由参数与资产替代会请求明确确认；源码批准绑定精确SHA，含糊赞同不应生效。

会话内`/session`查看ID、`/tasks`看任务、`/history`看对话、`/exit`退出；`chat --resume SESSION_ID`恢复。用`report SERVER_REPORT_PATH`下载并打开，服务器路径由实际报告返回，不可猜。文件从本机上传到服务器，研究计算与报告原件仍在服务器；本机下载件不是新研究。

## 常见故障

- Git Bash的MSYS路径重写：客户端优先Windows原生OpenSSH；检查已保存路径是否曾被改写，重新setup，不关闭安全检查。
- 中文显示密集不等于UTF-8损坏；先区分转录器分片解码、字体和终端布局，再判断Agent编码问题。
- Ctrl+C取消当前前台操作，不能保证所有远端子进程立即停止。断线不等于后台持久运行。
- 报告版本旧：先读合法最新版本，读取与刷新分开，不能用普通查询偷偷发起Test。
- 临时服务器盘可能清理，保留本地论文原件、报告备份和数据版本记录。

本次归档未向真实服务器上传，也未修改个人客户端配置。
