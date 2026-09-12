# 开发说明

## 代码结构

```text
backend/app/
  api.py              API 路由装配及兼容的依赖导出
  routes/             按业务拆分的 HTTP 接口与公共依赖
  orchestrator.py     确定性创作流程
  schemas.py          请求与结构化产物合同
  models.py           数据库模型
backend/migrations/   Alembic 数据库迁移
backend/prompts/      版本化 Prompt Registry
backend/plugins/      内置 Provider 清单
backend/tests/        业务、安装、发布与回归测试
frontend/src/
  App.tsx             应用状态、导航和页面延迟加载
  pages/              工作台、内容库、设置、风格、创作、复盘
  components/         编辑器、封面、热点、规则比较等组件
  lib/                请求处理和内容辅助函数
  types.ts            共享 API 数据类型
scripts/              安装、计划任务和源码发布整理
```

后端路由按系统、插件、热点、OCR、内容、封面、风格、复盘、评论分组。保留 `/api` 路径与既有业务数据格式；健康接口增加不包含明文路径的 `instance_id`，用于区分不同项目副本。

## 安装与开发服务

先运行 README 中的安装脚本。Python 使用 `pyproject.toml` 中的直接依赖及 `requirements.lock.txt` 约束；前端使用 `npm ci` 安装锁文件中的版本。

在两个终端分别执行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

```powershell
cd frontend
npm.cmd run dev
```

开发页在 5173，代理 `/api` 到 8765。更改开发后端端口时同时修改 Vite 代理；日常启动器则读取 `XR_PORT`。

`local_access.py` 校验 Host 和 Origin。允许本机主机名、localhost、私有/回环 IP，以及同源请求和固定 5173 开发来源；无 Origin 的正常命令行调用仍可使用。该校验用于拦截跨站浏览器请求，不能替代局域网身份验证。自定义代理或域名需审阅并同步调整访问规则。

图像配置与凭据分别保存在 SQLite 和系统凭据管理器。`image_credential_binding` 保存地址与密钥的组合摘要；更换密钥前先落盘保护记录，最终配置写入失败时生图会因摘要不一致而停止，用户重新填写服务密钥即可修复。摘要和密钥均不由设置接口返回。

## 检查

在项目根目录执行后端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

前端检查：

```powershell
cd frontend
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

测试使用独立的 `backend/tests/.test_data/`，不针对日常数据库。外部服务通过假 Provider 或模拟响应测试。Windows 安装器测试还检查安装失败中止和只读环境检查。GitHub Actions 配置 Windows Python 3.11/3.13 后端测试及 Linux Node.js 22 前端检查；远端运行结果以仓库 Actions 页面为准。

## 数据库迁移

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

迁移与服务使用同一 `XR_DATA_DIR` 配置，重复升级到 head 不会重建数据。验证迁移时将 `XR_DATA_DIR`、`XR_LOG_DIR`、`XR_UPLOAD_DIR`、`XR_EXPORT_DIR` 全部指向隔离目录。不要用现有个人数据库做自动测试。

## Docker 辅助运行

```powershell
docker compose up --build
```

复制 `.env.example` 为 `.env` 后配置环境密钥。Compose 默认仅把端口暴露到本机；`.dockerignore` 排除个人数据和依赖目录。默认容器内端口保持 8765；不要在 Compose 的 `.env` 中改动 `XR_PORT`。Docker 在本次本机环境未实测，Windows OCR、Windows 凭据管理器与任务计划程序在 Linux 容器内不可用。

## 整理公开源码

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_release.py --output .\release\chaoshi-yuji
```

脚本按源码目录与文件类型白名单复制，生成 ZIP 和 SHA-256 文件清单；排除个人数据、密钥文件、日志、依赖和原 Git 历史。疑似密钥或个人绝对路径会阻断整理，仅输出文件名。此扫描不能替代人工审阅，公开前还需检查截图和自定义内容。

复制使用扫描时读取的原始字节，避免源文件在扫描后变动导致清单与发布内容不一致。文件清单位于 `RELEASE_MANIFEST.json`。重复生成时使用新的输出名称，例如 `release/chaoshi-yuji-reviewed-20260912`。

目标已存在时会拒绝覆盖，请选择新目录。该脚本不会创建 GitHub 仓库或上传。发布副本不带 `.git`；确认验收和上传范围后再初始化新历史。`RELEASE_MANIFEST.json` 属于整理出的 ZIP，其摘要针对打包时的文件字节，不跟踪进 Git；Git 会按 `.gitattributes` 规范文本换行。
