# Java 执行隔离架构方案 V2 审核记录

日期：2026-11-06。此次只修订架构文档，没有修改业务代码、评分规则、数据库、`.env` 或部署。

## 本次修订

1. 明确学生程序和 runner 都是不可信的，学生观察值不再被视为评分结果。
2. 统一第一版 IPC 为 Docker attach 加可信协调器内存转发，删除共享文件和 Unix socket 作为第一版方案。
3. 为每个 job 设计独立随机 HMAC key，限定在协调器和可信 checker，说明 HMAC 的边界。
4. 增加独立 Java Executor，避免公网 FastAPI 直接拥有 Docker Socket。
5. 明确有效检查次数分类：学生代码问题计次；Docker、checker、协调器基础设施问题不计次。
6. 补充 read-only rootfs、tmpfs、seccomp/AppArmor、memory-swap、输出上限、内核共享风险和 gVisor/Kata/Firecracker 选项。
7. 重新说明 PracticeHarness/ShopHarness 的迁移方式，并保持 70 分门槛、必要条件、三次有效检查、教师评分和重置逻辑。
8. 将 Practice 核心案例垂直切片作为 7.1 的唯一实施边界。

## 仍未解决的风险

- 学生自编测试天然由学生控制；在不改变现有评分含义的前提下，退出码只能作为受限观察值，不能证明测试覆盖质量。受限测试 DSL 是后续选择。
- Docker 共享宿主机内核；强对抗场景需要评估 gVisor、Kata 或 Firecracker。
- Docker attach、HMAC 密钥注入和 Executor 本地认证尚未实现或实测。
- 当前旧实现仍是同一 JVM；V2 方案完成前不能声称已达到强隔离。
- 多学生并发、Windows Docker Desktop 与 Linux worker 的性能和故障恢复尚未测量。

## 最终推荐架构

FastAPI 只访问受限本地 Java Executor；Executor 创建学生容器和可信 checker 容器，通过 attach 流在内存中转发协议消息。学生容器只挂载当前提交，可信 checker 只使用固定镜像内的检查器和 fixture，两个容器不共享文件系统或网络。所有学生输出不可信，可信 checker 重算，Python 评分层继续执行既有规则。

## 7.1 明确实施边界

只迁移 Practice 的 `CORE-NAME` 一个核心案例。交付物包括：学生容器 runner、可信 checker 容器、Docker attach 双向协议、job 独立 HMAC key、结果校验、超时/OOM/输出限制和故障分类测试。不得在 7.1 同时迁移其他核心案例、学生测试系统、Shop、数据库结构或评分规则。

## 本轮第一轮实施记录（2026-11-06）

实际新增：`backend/java_executor.py`、`tests/test_java_executor.py`、`training/java-practice/runner/CoreNameRunner.java`、`training/java-practice/runner/CoreNameContractTest.java`、`training/java-practice/runner/start-core-name.sh`、`training/java-practice/checks/core_name_checker.py`、两个 CORE-NAME 专用 Dockerfile。

纯 Python 协议、HMAC、结果重算和伪造字段测试结果为 **5 passed**；Java 合约测试因当前主机没有 `javac` 跳过；checker 脚本在本机进程级输入帧测试中返回并验证了可信结果。当前 Docker daemon 无权限访问 `/var/run/docker.sock`，真实容器集成测试未完成，未把模拟测试描述为容器安全通过。

本轮明确保持旧 `run_check` 默认路径，未迁移其他八个 CORE、学生测试系统、Shop、数据库、评分规则或三次计次逻辑。下一步必须在具有 Docker daemon 权限的隔离环境中构建两个镜像并验证实际 attach、挂载、超时、OOM、输出上限、checker 崩溃和并发 job。

## 第二轮环境阻塞记录（2026-11-06）

Docker 客户端正常但 daemon socket 对当前用户拒绝访问；主机 `javac` 不存在。因此本轮真实双容器测试和 Java 合约编译均未执行。没有使用 sudo、chmod socket、修改用户组、重建 Docker 或虚构测试结果。只完成了协议静态复核、消息数量限制的最小修正和纯 Python 测试。
