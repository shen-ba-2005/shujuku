# 屿账 · 个人数字资产与订阅服务管理系统

数据库课程大作业，第 8 周阶段版本。MySQL 8 / FastAPI / PyMySQL 原生 SQL / 原生 HTML、CSS、JavaScript，前后端分离，无 ORM。全部业务数据虚构。

## 快速启动（Windows PowerShell）

需要 Python 3.13、本机 MySQL 8.0.16+ 的 `mysqld` 在 PATH 中。当前开发机器为 MySQL 8.0.46。无需安装 Node 前端依赖。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe scripts/dev.py init-db
.\.venv\Scripts\python.exe scripts/dev.py seed
.\.venv\Scripts\python.exe scripts/dev.py serve
```

打开 <http://127.0.0.1:5173>，API 文档 <http://127.0.0.1:8000/docs>。

第二次启动只运行 `init-db` 和 `serve`；**seed 只用于空开发库**，遇到已有表会拒绝，不覆盖数据。实例正在运行或服务端口已占用时，按提示检查，不重复启动。初始化数据位于 `.runtime/mysql/`，密码配置位于 `.runtime/db.json`，均不提交 Git。不要删除该目录来解决普通启动问题，先检查日志。

停止本项目进程：

```powershell
.\.venv\Scripts\python.exe scripts/dev.py stop
```

停止命令核对进程命令行和项目数据目录内记录的 MySQL server UUID，只停止本项目拥有的实例。现有 MySQL80（3306）及 PostgreSQL 服务不受影响。

## 当前可用功能

- 支付方式新增/查询/误建删除；订阅新增/查询/修改/误建删除。
- 仪表盘：月实际支出、活跃订阅、月折算金额、闲置续费资产数。
- 扣费日历及点击明细、分类支出、预算进度、资产闲置饼图、未完成提醒。
- 全部展示查询真实 MySQL；无图表模拟数据。初始月 2026-11，演示基准日 2026-11-10。
- 8 张表、约束与索引、种子数据、JOIN/GROUP BY/EXISTS 代表性查询。

**未实现**：取消业务事务、两个触发器、月汇总存储过程、模拟时间任务、资产/预算/提醒写界面、登录与密码库功能、最终 Word 报告和答辩材料。对应设计已经整理，不能把本阶段当成最终完整系统。

## 验证

在项目 MySQL、API 和前端启动后：

```powershell
.\.venv\Scripts\python.exe tests/verify_week8.py
.\.venv\Scripts\python.exe tests/browser_week8.py
```

浏览器验收需要本机 Chrome（当前脚本使用 Playwright 的 chrome channel）。没有 Chrome 时，可安装兼容 Chromium 并相应调整启动设置。依赖已经包含在 lock 中。

集成脚本创建随机命名 `subscription_verify_*` 临时库，在其中重建和验证约束，最后仅移除该临时库；API/浏览器检查会新增专用测试记录并通过 API 清理，不移除种子数据。默认种子基线应保持 4 个活跃订阅、175 元当月实际支出；若自行添加数据，固定基线验收需要在单独空开发环境运行，不能为了通过测试清空个人已有成果。

证据：`docs/evidence/` 中 JSON 结果和桌面/手机截图。验收结论与范围见 [第8周验收记录](docs/第8周验收记录.md)。

## 文件导航

```text
backend/           FastAPI 接口，显式原生 SQL
frontend/          页面、样式及接口调用，无外部 CDN
database/          建表、种子数据、代表性查询
scripts/dev.py     独立 MySQL 初始化、启动/停止、导入
tests/             真实 MySQL/HTTP/浏览器验收
docs/              需求、DFD、E-R、3NF、架构、方案和证据
AGENTS.md          长期总体约束
任务交接.md        接手入口
```

三角色责任和实际贡献分别记录在 [协作记录](docs/协作记录.md)，A/B/C 为组织标签，不伪造三位成员的参与历史。
