# AI-Education Clean GitHub Copy

创建日期（UTC）：2026-11-07
来源：`/workspace/AI-Education`
目标：为独立私有 GitHub 仓库准备的源代码副本。

## 保留

- `backend/`、`frontend/` 源码及前端构建配置。
- `tests/`、`training/java-practice/`（不含 reference）、`training/java-shop/`（不含 reference）、`training/software-engineering/` 的 starter、grader-fixtures 和 checker。
- 第五至第七阶段架构文档、PRD 对照、人工验收和技术债文档。
- 7.1 Python Executor、Student Runner、Trusted Checker、测试和 Dockerfile。
- `.env.example`、依赖清单和必要脚本。

## 排除

- 原始 `.git/` 和全部历史提交。
- `deliverables/cloud-migration-20261014/training.sqlite` 及任何 SQLite/数据库快照。
- `runtime/`、用户上传、会话、缓存、虚拟环境、node_modules、dist、output、tmp。
- `deliverables/reference-answers/`、Java reference zip、软件工程 reference、视频录制/编辑素材。
- 本机迁移文档和部署迁移资料，其中可能包含本机路径或凭据示例。

## 注意

- 副本没有初始化 Git，没有提交，也没有推送。
- 测试和演示代码中可能仍有虚构的 fixture 账号/密码字符串；它们不是生产凭据，但新仓库必须保持私有并在发布前单独复核。
- 本副本未运行测试；当前环境不能据此宣称构建或测试通过。
- `docs/項目進度與交接.md` 等技术文档保留，因为它们记录第五至第七阶段进度；本机迁移文档被排除。

补充：`training/software-engineering/starter.zip` 已保留，因为 `backend/projects.py` 在运行时提供该起始包。仅用于生成内部参考答案的 `scripts/make_engineering_materials.py` 已从安全副本排除。

- Internal `reference/` directories were excluded from the safe copy because they may contain answer keys or trusted checker fixtures. The original project retains them unchanged.
