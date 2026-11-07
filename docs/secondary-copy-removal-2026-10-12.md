# 页面次要文字清理（2026-10-12）

按用户要求删除登录演示账号区块，以及各页重复的品牌小字、装饰口号和无需重复说明的提示。仅修改界面显示，账号和既有功能保留。

保留：首次使用教程、输入格式、错误原因、得分与核验状态、项目开放状态、班级项目选择说明、教师安排、隐私与分享说明、AI用量及证据。保留销售图表的「项目示意」标记，避免将装饰示意图误认成学生实际结果。

## 删除清单

| 页面文件 | 删除文字／内容 | 处数 |
| --- | --- | --- |
| App.tsx | 品牌旁重复的小字：AI 岗位实训 | 2 |
| Registration.tsx | 品牌旁重复的小字：AI 岗位实训 | 1 |
| TrainingUI.tsx | 品牌旁重复的小字：AI 岗位实训 | 1 |
| ProjectLibrary.tsx | 品牌旁重复的小字：AI 岗位实训 | 1 |
| TeacherWorkspace.tsx | 品牌旁重复的小字：AI 岗位实训 | 1 |
| App.tsx | AI 岗位实战训练营 | 1 |
| App.tsx | 学生主导 · 一人工作室 · 有证据的教育服务 | 1 |
| App.tsx | 进入你的实训空间 | 1 |
| Registration.tsx | AI 岗位实战训练营 | 1 |
| Registration.tsx | 学生主导 · 一人工作室 · 有证据的教育服务 | 1 |
| Registration.tsx | 创建你的实训空间 | 1 |
| App.tsx | 本机演示账号；学生 student / 演示密码；教师 teacher / 演示密码；创业者 founder / 演示密码；切换学生 / 创业者账号（整个区块） | 1 |
| App.tsx | 个性化 AI 教练已启用／基础训练可用 · 个性化 AI 教练待启用 | 1 |
| Registration.tsx | 新账号为学生账号，实训进度从零开始。 | 1 |
| App.tsx | 阶段标题上重复的「运营数据分析 · 校园文创店」；创业者页的「创业者工作台」小字 | 1 |
| App.tsx | 依据数据与明确口径 | 1 |
| App.tsx | 每次改进都被记录 | 1 |
| App.tsx | 反馈与行动分别记录 | 1 |
| App.tsx | 已与当前证据分开保存 | 1 |
| App.tsx | 每一步，都有依据 | 1 |
| App.tsx | 创业者空间／我的实训空间（侧栏重复小标题） | 1 |
| TrainingUI.tsx | 我的实训空间（侧栏重复小标题） | 1 |
| TeacherWorkspace.tsx | 我的教学空间（侧栏重复小标题） | 1 |
| TeacherWorkspace.tsx | 本班教学（导航已有明确名称） | 1 |
| App.tsx | AI + 教育 · 岗位实战（顶部标语） | 1 |
| TrainingUI.tsx | AI + 教育 · 岗位实战（顶部标语） | 1 |
| TrainingUI.tsx | AI 协作 · 每次行动可查看 | 1 |
| TrainingUI.tsx | 你的实训工作室 | 1 |
| TrainingUI.tsx | 一次岗位实战，一份属于你的作品。今天，从下一步开始。 | 1 |
| TrainingUI.tsx | 完成当前任务，逐步走向独立交付。 | 1 |
| ProjectLibrary.tsx | AI 岗位实战训练营 · 项目库 | 1 |
| ProjectLibrary.tsx | 选择专业方向（筛选按钮和教程保留） | 1 |
| ProjectLibrary.tsx | 中途离开后，可以回到这里继续已保存的进度。 | 1 |
| ProjectLibrary.tsx | 仅展示方向，尚未开放内容（卡片与按钮已标示筹备中） | 1 |
| Engineering.tsx | 当前源码与修改标题旁的源码哈希片段（版本和检查结果保留） | 1 |
| App.tsx | 个性化学习支持／标准学习支持（AI状态在侧栏保留） | 1 |
| Engineering.tsx | 个性化学习支持／标准学习支持（AI状态在侧栏保留） | 1 |
| App.tsx | 数字有核验，判断有依据。每次练习，都为独立完成做准备。 | 1 |
| Engineering.tsx | 遇到问题，点右下角「问AI教练」。每次练习，都为独立完成做准备。（重复提示；侧栏和问AI入口保留） | 1 |
| App.tsx | 我要实习 · 学生主导的实训工作室；模拟数据 · 过程可追溯 · 成果可交付（整个页尾） | 1 |
| Engineering.tsx | 我要实习 · 学生主导的实训工作室；模拟任务 · 过程可追溯 · 成果可交付（整个页尾） | 1 |
| ProjectLibrary.tsx | 我要实习 · 学生主导的实训工作室；选方向 → 做任务 → 交作品（整个页尾） | 1 |
| PersonalizedLearning.tsx | 从错题走到独立完成 | 1 |
| TeacherWorkspace.tsx | 教师工作台 · 从证据到教学行动 | 1 |
| TeacherWorkspace.tsx | 按当前查看项目的实际记录（当前查看项目已在上方说明） | 1 |
| TeacherWorkspace.tsx | 打开学生详情查看各项理由（查看与指导按钮保留） | 1 |

补充：移除登录表单预填的演示学生账号与密码，登录时自行输入账号。既有演示账号仍可正常登录。移除登录故事区的页尾小字后，主介绍保持垂直居中。

## 验证

TypeScript／Vite构建通过（1602模块）。最终产物：index-3nymZcab.js、index-Cf2FAtzO.css。本机服务按请求读取更新后的dist，纯前端修改无需重启。未执行行为测试、浏览器自动化或模型调用。
