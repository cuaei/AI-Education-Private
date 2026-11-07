# 校园活动报名系统 · 原创模拟实训

需 Python 3.12、Node.js 22。安装 fastapi==0.115.12、uvicorn==0.34.0、httpx==0.28.1。

先在frontend执行npm install、npm run build，再在源码根目录运行：

`python -m uvicorn backend.app:app --host 127.0.0.1 --port 8080`

Windows本地启动前设置环境变量TRAINING_DB为一个可写的本地SQLite文件路径。

虚构账号：student1、student2、student3、student4、organizer、organizer2。密码均为Demo2026!。
固定训练时钟：2099-10-01T00:00:00+00:00，可用COURSE_CLOCK覆盖进行本地实验。

提交ZIP必须含backend/app.py、frontend/package.json、frontend/src/main.tsx、frontend/index.html、frontend/tsconfig.json、student_checks.py。
平台固定依赖，不接受任意安装脚本或新增外部库。不提交node_modules、dist、虚拟环境、数据库或.env。
student_checks.py通过BASE_URL连接一个预设的虚构应用；退出0表示学生测试通过，断言失败返回非0。
平台会在正常版本与预设故障版本分别执行它，确认至少有测试且能发现缺陷。

公开契约：POST /api/auth/login；GET/POST /api/activities；GET /api/activities/{id}；POST /api/activities/{id}/register（JSON含可选waitlist）；GET /api/registrations/mine；POST /api/registrations/{id}/cancel；GET /api/activities/{id}/roster。
活动字段title、capacity、deadline、starts_at；报名字段id、activity_id、student_id、status、sequence；活动响应另含registered、remaining、closed。
完整业务验收规则见平台任务页。私有验收只检查已公开规则，不要求指定内部代码写法。
