# 实战起点 · AI 岗位实战训练营

> 重新接手請先閱讀 [項目文件入口](AGENTS.md)；舊的運行、帳號及部署描述須重新核實。

面向大学生的运营数据分析实训网页：诊断 → 数据清洗 → 指标核验 → 图表证据 → 报告 → 答辩 → 独立迁移 → 作品交付。创业者可管理学员、查看原文、人工复核、记录服务时间及模型费用。

本项目是可操作的本机产品。模型调用接口、工具执行与记录已实现；未配置真实 API key 时运行基础模式。真实模型教学质量、真实学生效果、公网部署尚待验证。

## 打开产品

本次开发环境已安装依赖并构建。服务运行时访问 **http://127.0.0.1:8000**。

关闭后重新启动，在项目目录运行：

```powershell
.\scripts\start.ps1
```

| 身份 | 演示账号 | 密码 |
| --- | --- | --- |
| 学生 | student / student2 | Study2026! |
| 教师 | teacher | Teach2026! |
| 创业者 | founder | Founder2026! |

student 已用于开发演示；student2 可从零开始。演示账号不计入真实试用账号。创业者可创建独立试用账号。

新电脑需 Python 3.12+、Node.js 22+、npm。首次运行 `scripts/setup.ps1`，再运行 `scripts/start.ps1`。如 PowerShell 阻止脚本，可分别执行 `.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`；无需全局修改执行策略。新安装环境需先建立 .venv 并安装 requirements.lock.txt，再在 frontend 运行 npm ci 和 npm run build。

## AI 实际如何使用

教师端已接入两项独立的Agent用途：根据学生真实证据提出待确认的补练草案，以及根据匿名班级统计保存教学建议。两项均使用既有服务端模型配置；不需要另填密钥。详情及人工验收步骤见 [教师端使用与验收](docs/teacher-workspace-manual.md)，设计依据见 [教师端方案](docs/項目需求總覽.md)。

详细说明在 [AI Agent 实现与接入说明](docs/ai-agent-implementation.md)，完整产品方案在 [产品与实施方案](docs/項目需求總覽.md)。

1. 学生提交后，程序先核验实际数据并保存版本。
2. 后端将当前学生必要证据、任务状态、知识口径及允许工具发送给你配置的模型。
3. 模型返回工具名与参数；后端检查权限、证据和流程后执行，例如安排退款补练、保存报告评价或提出答辩追问。
4. 工具真实执行结果返回模型；最多三轮工具行动，再接受最终结构化反馈。
5. 验证通过才提交本轮修改。失败保留学生提交和真实调用记录，并进入人工复核。

同一个模型承担六种职责，按任务限制工具权限。客观评分完全由程序计算。API key 是接入模型的凭证；Agent 的行动流程、课程工具和记忆由本项目实现。

## 配置你的 API key

已为当前项目配置 DeepSeek 官方接口及 deepseek-flash，.env 已创建，你只需填写 AI_API_KEY 后重启。详见 [DeepSeek 接入步骤](docs/deepseek-setup.md)。

复制 `.env.example` 为 `.env`，在本机文件中填写，不要提交或截图公开密钥：

```dotenv
AI_API_KEY=填写实际密钥
AI_BASE_URL=https://你的模型服务/v1
AI_MODEL=供应商的实际模型标识
AI_INPUT_PRICE_PER_MILLION=
AI_OUTPUT_PRICE_PER_MILLION=
AI_CURRENCY=CNY
```

接口使用兼容 chat/completions 的 HTTPS API；模型须支持 tools/function calling。BASE_URL 填接口根目录，程序追加 `/chat/completions`。仅有 API key 仍不足以判断供应商地址与模型标识；三项需一起配置。修改后重启服务，创业者「模型与使用说明」可检查配置状态。环境变量优先于 .env。

不用自行训练模型，也不要求每个学生提供密钥。学生浏览器不接触密钥。没有密钥时清洗、核验、知识卡、固定补练、报告、三题答辩、迁移与作品仍可使用，个性化 AI 反馈不会伪装为已启用。

## 功能与交付

- 自制 A/B 两份八周合成数据，C/D 两套测评；数据字典和计算口径固定。
- CSV、金额与单位校验，客观 60 分；AI 报告 25 分、答辩 15 分分别记录，缺少评价时显示未评价。
- 品类/渠道柱图、八周趋势、带证据的报告、答辩作品快照、独立测评。
- 提交版本、历史报告、原文和人工评价保留；上游修改令下游失效并重新核验。
- 私人 HTML/Markdown/JSON 导出；网页可打印 PDF。公开链接默认隐藏答辩与评价，学生可主动选择加入并撤销。
- 创业者账号创建、学员作品查看、人工时间与费用汇总、匿名 AI 运营建议。
- 持久化 SQLite、会话与角色权限、请求重试去重、手动备份与新目录恢复。

调用费用按你填写的每百万 token 费率估算。缺少用量、费率或重试发生未知计费时显示未知，已报告用量单独保留；运营助理调用计入总量。该估算需与供应商账单核对。

## 验证与演示

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

在 frontend 运行 `npm run build`，含 TypeScript 检查与生产构建。

[验收记录](docs/verification.md) 区分自动测试、浏览器实测、模拟模型与真实模型状态。[演示与试用指南](docs/demo-and-pilot.md) 包含现场步骤、真实试用模板与固定教练案例。

生成开发者演示样例：`.venv\Scripts\python.exe scripts/make_demo_files.py`。文件位于 runtime/demo-fixtures，含参考答案，仅用于演示，不给独立测评学员使用。

## 数据与部署

学习数据库位于 runtime/training.sqlite，上传位于 runtime/uploads；均不作为静态资源公开。账号删除清除当前数据库、提交及分享。私人导出和备份由持有人自行管理。

本机默认不自动备份。停止服务后可运行 `.venv\Scripts\python.exe scripts/backup.py backup`。每次执行备份会删除本目录七天前的备份；无人执行时不会自动清除。管理员收到删除请求后也需处理仍持有的手动备份。

恢复到尚不存在的新目录：

```powershell
.venv\Scripts\python.exe scripts/backup.py restore --file runtime/backups/实际文件.zip --destination runtime-restored
```

随后在 .env 设置 DATA_DIR=runtime-restored，再启动。恢复不会覆盖原目录。

公网部署前使用 HTTPS、持久化磁盘、单实例，设置 DEMO_MODE=false、COOKIE_SECURE=true、FOUNDER_PASSWORD 为新的长密码，使用新的 DATA_DIR 初始化账户。**已有演示数据库中的密码不会因环境变量变化而自动更换**。真实模型验收、备份与试用同意流程通过后再开放。当前只在本机监听，未发布公网。

数据与依赖来源见 [来源清单](docs/sources.md)。



## 直接体验已接入的 AI

2026-10-12 已完成用户 DeepSeek 密钥联调。打开本机页面 http://127.0.0.1:8000 ，刷新载入最新界面。

- 新训练：test01 / test02 / test03，密码均为 Study2026!，各自进度独立。提交起点诊断后默认自动获得 AI 反馈。
- 完整成果：agentdemo / Study2026!，查看分析报告、作品答辩及「查看 AI 协作历史」。这是开发者测试演示，不能当作真实学生成效。
- 运营：founder / Founder2026!，点击「分析运营情况」。

主画面显示实际模型反馈与已执行操作。自动反馈可关闭；独立迁移测评不提供 AI 提示。具体证据见 [真实接入验收](docs/live-ai-verification.md)。费率未填写，费用显示未知。
# 新增多专业实训（2026-10-12）

学生登录后进入项目库，可选原销售分析或「校园活动报名系统的迭代交付」。两个项目独立保存进度，均有主动AI答疑及错误/未满分反馈弹窗。

软件工程运行环境需要Docker Desktop；执行`scripts/setup-engineering.ps1`准备固定依赖镜像。学生上传源码只在隔离容器执行，不在主服务中运行。

人工验收答案在[deliverables/reference-answers/开始人工验收.md](deliverables/reference-answers/开始人工验收.md)，交付范围见[软件工程实施记录](docs/項目進度與交接.md)。按用户要求，这次不运行自动测试；参考包尚未实际评分，AI主观评价不保证固定满分。

## Java 学习路线、综合实作与模拟实习（2026-11-05）

学生登录后默认进入 Java 后端学习路线（九个主题、外部资料、完成标记、每日 10 次 AI 答疑）。路线下方的「进入综合实作与模拟实习」打开工作台：

- **综合实作 · 比赛报名系统**：下载起始项目 ZIP，在本机只用 JDK 17 完成 `RegistrationService` 并写自己的测试，上传 ZIP 与 200–2000 字设计解释；平台在隔离容器检查，满分 100、至少 70，核心功能与自己的测试为必要条件。
- **模拟实习 · 网店**：综合实作通过后，依序完成查询商品、建立订单、查看订单；下载的起始项目附 `web/index.html`，本机 `java -cp out shop.ShopServer` 后打开 http://127.0.0.1:8080 操作，不需要写前端。
- 每项工作最多 3 次有效检查，环境故障不计次；教师（限本班学生）或管理员可在 Java 次数面板重设。

检查环境准备（项目根目录 PowerShell）：

```powershell
.\scripts\setup-java.ps1
```

脚本优先以 `training/java-runtime/Dockerfile` 建立 `course-platform-java:2026.11.5`，若 Docker Hub 认证失败会退回拉取 `eclipse-temurin:17-jdk` 并加相同标记。学生代码只在 `--network none`、只读挂载、`--user 10001`、CPU／内存／进程上限的容器内编译运行，不在主服务执行。镜像或 Docker 不可用时，页面显示环境故障且检查不计次。

相关文件：`backend/java_course.py`、`training/java-practice/`、`training/java-shop/`、`frontend/src/JavaCourse.tsx`。实施与验证记录见[进度记录](docs/項目進度與交接.md)；工程选择与评分权重见[需求总览](docs/項目需求總覽.md)。


