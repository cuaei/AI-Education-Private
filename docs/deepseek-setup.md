# DeepSeek 接入与测试账号

项目根目录已创建 .env；服务地址和模型已填好，你只需要填写密钥：

```dotenv
AI_API_KEY=你的实际DeepSeek_API_key
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-flash
```

保留其余配置即可。费率字段暂时留空，费用显示未知，之后依据你的实际计费设置填写。

应用发送 POST https://api.deepseek.com/chat/completions，HTTPS 默认端口 443；不用另填端口或把路径重复写进 AI_BASE_URL。本机产品地址仍为 http://127.0.0.1:8000，两者用途不同。

当前官方文档列出 deepseek-flash 与 deepseek-v4-pro。默认选择 deepseek-flash；本项目对 DeepSeek 官方地址发送 thinking.type=disabled，采用非思考模式执行当前工具循环。参考 [官方工具调用说明](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/) 和 [API 参数](https://api-docs.deepseek.com/api/create-chat-completion/)。若密钥来自其他服务商，应改为该服务商的地址与模型标识。

保存 .env 后需重新启动后端。若原服务在你自己的终端运行，先 Ctrl+C 停止，再运行 scripts/start.ps1。如果原服务由本次 Codex 会话运行，告诉我「密钥填好了」，由我停止原服务、重新启动并进行真实调用联调。

检查步骤：登录 founder，打开「模型与使用说明」，确认服务端配置；然后使用新学生账号完成诊断。默认开启「提交后自动获得 AI 反馈」，也可手动点击「让教练解释诊断」。主画面显示实际反馈、已执行动作和协作历史。配置存在不等于密钥有效，只有实际收到模型反馈并留下调用记录才证明接入成功。出现无法连接时检查密钥、API 账户余额和网络，再保留失败记录排查。

已创建 test01、test02、test03，初始密码均为 Study2026!，各自保存独立进度，均标记为测试账号，不计入真实学生试用人数。建议分别测试基础流程、错误补练、报告与答辩；不会互相覆盖。

2026-10-12 已使用用户填写的密钥真实接入 DeepSeek，并重新启动本机服务。六类 Agent 任务及网页自动诊断均完成实际调试，记录见 [真实接入验收](live-ai-verification.md)。费用字段未填，仍显示未知。
