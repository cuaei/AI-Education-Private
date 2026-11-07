# PRD—代码—测试对照表

本表为第四批验收记录，日期 2026-11-05。状态依据当前工作区代码和本批实际执行结果；“通过”仅表示对应自动或 API 检查通过，不表示浏览器或真人验收通过。

| 需求编号 | 需求内容 | 实现状态 | 代码位置 | 测试情况 | 实测结果 | 遗留问题 | 后续建议 |
|---|---|---|---|---|---|---|---|
| JAVA-01 | 九个 Java 学习主题 | 已实现 | `backend/java_route.py` `TOPICS`；`frontend/src/JavaRoute.tsx` | `tests/test_java_route.py` | API 返回 9 个主题；端到端通过 | 资源可访问性未逐项核实 | 进行人工资源链接验收 |
| JAVA-02 | 学习资源可自由浏览、跳过并保存进度 | 已实现 | `java_progress`；`/api/java-route/progress` | `test_java_progress_and_daily_quota`；隔离 E2E A | 刷新、退出再登录后保留；student2 隔离 | 未做浏览器操作 | 浏览器验收页面提示和刷新 |
| JAVA-03 | 隐藏旧实训入口、保留旧数据 | 部分实现 | `JavaRoute.tsx`、项目路由 | 静态检查；数据库隔离副本 | 当前 Java 页面无旧入口；旧代码仍保留 | 无浏览器实测；旧数据仅做结构核验 | 人工检查项目库和旧账号 |
| JAVA-04 | AI 仅主动提问，每日 10 次服务端限制 | 已实现 | `reserve_ai_quota`、`/api/java-route/ask` | Java 路由测试及并发额度测试 | 额度上限和中国日期重置通过；无 AI 时返回 503 | 真实模型和费用未验收 | 使用模拟模型做 UI 验收 |
| PRACTICE-01 | 下载起始 ZIP、上传 ZIP 安全校验 | 已实现 | `starter`、`validate_archive` | `test_upload_validation_and_fixed_files`；E2E B | 下载、坏 ZIP、缺文件、固定文件保护通过 | 未覆盖浏览器下载体验 | 补充浏览器验收 |
| PRACTICE-02 | Docker、无网络、只读、非特权、资源限制执行 | 已实现 | `run_check`、`flags` | 真实 JDK 17 容器测试 | 参考实现真实容器通过；Docker 配置含 `--network none`、UID 10001、资源限制 | 当前环境课程文件权限需可读 | 发布环境后复验镜像和权限 |
| PRACTICE-03 | 识别正确代码、错误代码和三类故障 | 已实现 | `training/java-practice/checks` | `test_java_course.py` 伪检查及真实参考实现 | 64 项后端测试全部通过 | 真实错误版本覆盖仍有限 | 增加真实错误版本容器案例 |
| PRACTICE-04 | 核心、学生测试、结构检查和必要条件 | 已实现 | `grade_practice`、Java harness | Java 课程测试 | 核心/测试必要条件、结构评分通过 | 结构规则不代表完整可维护性 | 保持规则与 PRD 同步 |
| PRACTICE-05 | 设计解释必须评分，70 分门槛 | 已实现 | `grade_practice`、人工评分路由 | `test_passing_gate...`、教师评分测试、E2E B | 未评分不能通过；评分后按 70 分和必要条件判断 | 真人评分质量未验收 | 进行教师界面人工验收 |
| PRACTICE-06 | 三次有效检查，环境故障不扣次 | 已实现 | `attempts_used`、`counted` | `test_three_attempts_environment_failure...` | 环境失败不计次，业务失败计次并锁定 | 超时真实 Docker 场景未覆盖 | 增加超时集成测试 |
| PRACTICE-07 | 教师/管理员按权限重置 | 已实现 | `/api/teacher/java/reset`、`/api/java/reset` | 权限和班级测试 | 非本班教师、学生越权均被拒；重置保留历史 | 浏览器操作未验收 | 补充教师面板人工案例 |
| SHOP-01 | 先通过综合实作，再依序解锁三项任务 | 已实现 | `shop_unlocked` | `test_shop_requires_previous_task...`；E2E C | 顺序解锁和最终完成通过 | 未做浏览器验收 | 人工检查三个任务状态 |
| SHOP-02 | 商品、订单创建、订单查看检查 | 已实现 | `training/java-shop`、`run_check` | Java 商店测试及隔离 E2E | 模拟结果流程通过 | 真实三个任务容器全链路未单独记录 | 增加参考实现真实三任务测试 |
| SHOP-03 | 每项检查独立计次、不可跳过或篡改状态 | 已实现 | 各 scope 的 `java_work_states` | Java 课程测试 | 任务状态和权限隔离通过 | 并发容量未验证 | 保持单学生容量声明 |
| ADMIN-01 | 教师只操作自己班级学生 | 已实现 | `teacher_learners`、`teacher_design` | 教师班级权限测试 | 非本班查询、评分、重置均拒绝 | 浏览器界面未验收 | 人工验证教师视图 |
| ADMIN-02 | 人工评分、管理员评分、历史与重评 | 已实现 | `save_manual_design`、`design.history` | Java 课程测试 | 评分来源、历史、重评状态通过 | 真人评分流程未验收 | 做教师和管理员 UI 验收 |
| DATA-01 | SQLite Backup API 隔离副本和新表兼容 | 已实现 | `backend/storage.py`、各 mount 的 `CREATE TABLE IF NOT EXISTS` | `/tmp/ai-education-fourth-batch` 隔离脚本 | Backup 前后 4 用户、17 张表及计数一致；新表存在 | 未操作真实生产库，按要求未迁移原库 | 发布前再做只读备份演练 |
| UI-01 | 桌面、笔记本、手机实际页面验收 | 无法验证 | React 页面已构建 | 当前环境无浏览器自动化工具 | 未执行，不能以构建代替浏览器验收 | 375/1366/1920 视口待验 | 在带浏览器环境完成人工验收 |

## 本批执行记录

- `pytest tests -q`：64 passed，1 个 Starlette/httpx 弃用警告。
- `npm test`：3 passed。
- `npx tsc -b --force`：通过。
- `npm run build`：通过，Vite 1606 modules。
- 端到端隔离 API A-D：通过。
- Docker JDK 17 参考实现检查：通过。
- 未调用真实 AI、未重启 8000、未修改真实数据库、未部署远程服务器。
