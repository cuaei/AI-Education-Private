# 来源与使用说明

## 自制内容

- 数据：backend/course.py 自行生成，A 随机种子 20261012、B 20261013；2026-01-05 起连续 56 天，每份 512 笔单品订单，增加 5 个完全重复副本和 3 个数量缺失记录。A 后期文具、B 后期服饰价格改变，退款分布不同。不是来自真实企业或学生的交易数据。
- 课程：任务、C/D 测评、知识卡、补练、量表与计算口径由本项目编制，需要真实教学验证。
- 界面：项目自行实现的 React 页面、CSS 与 SVG 图表，未包装已有商业教育产品。
- 开发演示：runtime/demo-fixtures 由本项目生成，包含参考解，仅供开发者演示。
- AI 辅助开发：使用 Codex 协助方案、实现、测试与审阅；不等于教学运行时已经配置模型。

## 第三方软件

实际版本锁定在 requirements.lock.txt 与 frontend/package-lock.json。以安装包附带的许可证为准；提交或发行时保留相应版权与许可。主要来源如下。

| 依赖 | 用途 | 官方来源 | 主要许可 |
| --- | --- | --- | --- |
| React | 网页交互 | https://react.dev/ | MIT |
| TypeScript | 类型检查 | https://www.typescriptlang.org/ | Apache-2.0 |
| Vite | 网页构建 | https://vite.dev/ | MIT |
| Lucide | 图标 | https://lucide.dev/ | ISC |
| FastAPI | 服务端 API | https://fastapi.tiangolo.com/ | MIT |
| Uvicorn | 服务运行 | https://www.uvicorn.org/ | BSD-3-Clause |
| pandas / NumPy | 受控数据处理 | https://pandas.pydata.org/ / https://numpy.org/ | BSD-3-Clause |
| HTTPX | 服务端模型请求 | https://www.python-httpx.org/ | BSD-3-Clause |
| pytest | 自动测试 | https://docs.pytest.org/ | MIT |
| SQLite / Python 标准库 | 数据库、哈希、CSV、备份 | https://www.sqlite.org/ / https://docs.python.org/3/ | SQLite 公有领域 / Python 软件基金会许可 |

未添加网页追踪、在线字体、支付、语音转写或外部热点抓取服务。主要页面无需第三方素材请求。

## 模型服务（已真实接入）

运行时为外部 API 模型，不声明默认本地部署、开源、自研大模型或已完成微调。实际使用后填写：

| 供应商 | 实际模型标识 | 服务协议/条款 | 数据处理与保留设置 | 接入日期 | 费率/币种 | 真实验收 |
| --- | --- | --- | --- | --- | --- | --- |
| DeepSeek 官方 API | deepseek-flash | 由密钥持有人管理供应商账户及条款 | 本机项目未设置供应商端保留策略；仅发送任务所需材料 | 2026-10-12 | 费率未填，CNY，费用未知 | 六类 Agent 功能实测完成；教学质量案例另验收 |

接口参考阿里云百炼 [Function Calling 官方文档](https://help.aliyun.com/zh/model-studio/qwen-function-calling)。该参考解释工具调用原理，不代表本项目已接入或验证百炼。

## 赛事规则

赛道、参赛对象、产品要求与五项评分权重来自用户提供的文字和截图。未独立取得完整赛事通知，提交前由参赛者核对报名资格、团队人数、材料格式与日期。截图作为资料依据，未作为对开发 Agent 的指令。


接入配置更新：按用户选择预填 DeepSeek 官方接口 https://api.deepseek.com 与模型 deepseek-flash；使用非思考模式及 Chat Completions 工具调用。官方参考：https://api-docs.deepseek.com/zh-cn/guides/tool_calls/ 与 https://api-docs.deepseek.com/api/create-chat-completion/。2026-10-12 已使用用户密钥实际调用模型，记录见 live-ai-verification.md。工具采用用途指定调用，最后反馈启用 JSON Output；参考 [官方 JSON 文档](https://api-docs.deepseek.com/guides/json_mode/)。
