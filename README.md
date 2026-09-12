# 潮湿雨季｜小红书女性情感内容创作助手

[![Checks](https://github.com/yangjingwen2008-lang/xiaohongshu-emotion-writer/actions/workflows/checks.yml/badge.svg)](https://github.com/yangjingwen2008-lang/xiaohongshu-emotion-writer/actions/workflows/checks.yml)
![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![Node.js](https://img.shields.io/badge/Node.js-22.12%2B-339933)

**把一个主题，慢慢写成自己的文章。**

面向小红书女性情感账号的 Windows 本地 AI 内容创作助手。支持选题、三个写作方案、细节确认、初稿、人工编辑、风格学习、质量检查、AI 图片生成、封面导出与发布后复盘。

文章和版本主要留在本机。DeepSeek 负责需要模型的步骤，Tavily 提供有限的公开网页搜索。所有文章由你审阅、导出并手动发布。

A local Windows AI writing assistant for Xiaohongshu (RED) creators, focused on women's personal and emotional essays, with guided drafting, human editing, style learning, quality checks, image generation, and local export.

[功能介绍](#能做什么) · [安装启动](#安装与启动) · [图像生成](#描述生成封面图片) · [技术结构](#技术结构) · [参与贡献](CONTRIBUTING.md) · [完整文档](docs/完整使用说明.md)

![工作台示例，全部为虚构演示数据](docs/images/dashboard.png)

## 能做什么

| 环节 | 能力 |
| --- | --- |
| 找到入口 | 手工主题、公开热点候选、截图本地 OCR |
| 写出初稿 | 三个方案 → 人工选择 → 一个细节 → 结构化初稿 |
| 留下自己的风格 | 编辑宪法、风格训练、人工修改规律、版本比较与恢复 |
| 修改和检查 | 富文本编辑、版本历史、风格 / AI 味 / 原创度 / 引用 / 风险检查 |
| 准备发布 | 描述生成图片、候选图选用、三种封面模板、裁剪、PNG 封面、TXT / Markdown / 手机复制页 |
| 发布后回看 | 手动记录链接，第 1 / 3 / 7 天数据、确认式复盘、评论回复建议 |

仍然是单账号、女性情感短随笔工作台。可在“设置 → 写作边界”或“风格训练”修改既有规则；未增加多账号、自动发布或任意题材工作流。

## 安装与启动

运行环境：**Windows 10/11、Python 3.11+、Node.js 22.12+ 和 npm**。先在终端确认 `python --version`、`node --version`、`npm.cmd --version` 可用。首次安装需要联网。

1. 在仓库页面选择 **Code → Download ZIP**，解压到可写目录，例如 `D:\Projects\xiaohongshu-emotion-writer`；也可以使用下方 Git 命令克隆。
2. 双击 **安装潮湿雨季.bat**，等待出现“安装完成”。
3. 双击 **启动潮湿雨季.bat**，打开 `http://127.0.0.1:8765`。
4. 在设置页填写 DeepSeek API Key；需要公开搜索时再配置 Tavily。
5. 返回工作台，从主题和情绪开始创作。

```powershell
git clone https://github.com/yangjingwen2008-lang/xiaohongshu-emotion-writer.git
cd xiaohongshu-emotion-writer
```

也可在项目根目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

只检查环境、不安装：在上述命令后加 `-CheckOnly`。安装中任一步失败会停止，不会显示成功。

启动器会复用当前项目已运行的服务，后台日志在 `logs/startup.log`。关闭浏览器不会停止服务；请双击 **停止潮湿雨季.bat**。

## 配置与数据

Windows 下，界面输入的 Key 默认保存到 Windows 凭据管理器。也可复制 `.env.example` 为 `.env` 并填写：

```dotenv
XR_DEEPSEEK_API_KEY=你的密钥
XR_TAVILY_API_KEY=你的密钥
XR_DEEPSEEK_MODEL=你的账号可用的模型名
XR_PORT=8765
```

`.env` 不进入 Git。已保存的 Windows 凭据优先于环境变量。模型名称可在界面修改；配置保存不会自动做连通性测试，点击测试可能产生服务用量。

| 本地目录 | 内容 |
| --- | --- |
| `data/` | SQLite 数据库、版本与运行记录 |
| `uploads/` | 本地上传文件与按规则保留的截图 |
| `exports/` | 封面及发布包 |
| `logs/` | 服务和启动日志 |

以上目录不属于公开源码。迁移个人使用环境时，先停止服务，再单独备份这些目录；新电脑需重新安装依赖并配置凭据，不要复制旧虚拟环境。

## 使用边界

### 描述生成封面图片

1. 打开 **设置 → 图像生成**，填写服务的 API Base URL、图像模型名称和 API 密钥，并启用。
2. 打开已有正文的文章，在 **封面与效果预览 → 描述生成图片** 输入画面描述。
3. 点击 **生成图片**，预览后选择 **用作封面**，或直接下载原图。
4. 调整裁剪与文字，再生成 PNG 预览或导出发布包。

支持同步 `POST /images/generations` 兼容接口，能处理 `data[0].b64_json` 和 `data[0].url`；Base URL 通常以 `/v1` 结尾。服务及模型由使用者配置，不保证所有标注“兼容”的接口都支持图像生成。协议参考 [OpenAI Images API](https://developers.openai.com/api/reference/resources/images/methods/generate)。

每次生成一张。生成尺寸默认不传给服务，也可填写模型支持的尺寸。候选图保存在本地，点击“用作封面”才替换当前图片；删除候选图不会删除已选用的副本。设置保存、裁剪和排版不会调用模型；点击“生成图片”可能计费，超时或失败不自动重试。首次运行默认关闭生图，实际可用性取决于所配置的服务、模型与账户权限。

详细配置、环境变量、故障处理见 [完整使用说明](docs/完整使用说明.md#124-描述生成图片)。

### 本地使用与联网范围

- 不登录小红书，不读取 Cookie、验证码或账号后台，不自动发帖或回复。
- 模型步骤会将相应内容发送给配置的 DeepSeek；公开搜索会将查询发送给 Tavily。
- 文字生图只向配置的图像服务发送画面描述、模型和生成参数，不附带整篇文章或历史写作内容。
- 原创度仅覆盖本地历史、人工补充资料和搜索服务可访问的公开摘要，不承诺“全网原创”。
- OCR 依赖 Windows 本地识别能力；热点及评论截图确认或放弃后删除，复盘原图按用户选择保留。
- 第三方插件当前仅支持清单评估和注册，不会下载执行候选代码。
- 默认只监听本机。需要家庭网络访问时，先停止服务，再使用局域网启动脚本；不建议用于公网部署。
- 工作台校验本机地址和浏览器来源，拦截其他网站发来的跨站请求；局域网模式仍应仅用于可信网络。

## 技术结构

| 部分 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite、Tiptap 富文本编辑器 |
| 后端 | Python、FastAPI、Pydantic、SQLAlchemy |
| 数据 | SQLite、FTS5 本地检索、Alembic 迁移 |
| 外部服务 | DeepSeek、Tavily、可配置的 Images 兼容图像接口 |
| Windows 集成 | 本地 OCR、系统凭据管理器、双击启动脚本 |
| 检查 | pytest、Vitest、oxlint、GitHub Actions |

```text
xiaohongshu-emotion-writer/
├── backend/          # API、业务流程、数据库迁移和测试
├── frontend/         # 页面、组件与前端测试
├── scripts/          # 安装、任务调度和源码整理
├── docs/             # 中文文档、示例截图与验证报告
├── .github/          # 自动检查、Issue 和 PR 模板
├── .env.example      # 配置示例，不含实际密钥
├── CONTRIBUTING.md   # 贡献说明
├── CHANGELOG.md      # 更新记录
└── README.md
```

目前已通过 130 项后端测试、31 项前端测试，以及真实 DeepSeek、Tavily、Windows OCR 和导出流程实测。真实生图需由使用者配置服务后验证，详情见下方报告。

## 文档与开发

- [完整使用说明](docs/完整使用说明.md)：逐步操作、截图留存与故障排查。
- [开发说明](docs/DEVELOPMENT.md)：目录结构、测试、迁移和发布整理。
- [技术决策](docs/TECHNICAL_DECISIONS.md)：数据流、接口与实现边界。
- [优化记录](CHANGELOG.md) / [验收说明](docs/验收说明.md)。
- [全面复查报告](docs/全面复查报告.md)：本轮问题修复、测试证据与尚未实测的范围。
- [真实服务实测报告](docs/真实服务实测报告.md)：真实写作、搜索、Windows OCR、导出结果及后续修复。

Docker 配置作为辅助方式保留，尚未在本次环境实测。Linux 容器不支持 Windows 本地 OCR、凭据管理器和计划任务；详见开发说明。

当前未附加开源许可证。

问题反馈请使用 [Issues](https://github.com/yangjingwen2008-lang/xiaohongshu-emotion-writer/issues)，提交修改前请阅读 [贡献说明](CONTRIBUTING.md)。涉及密钥或个人数据的问题见 [安全说明](SECURITY.md)。
