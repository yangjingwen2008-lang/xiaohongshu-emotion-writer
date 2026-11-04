---
name: 潮湿雨季
description: 安静、清晰的中文随笔写作工作台
colors:
  primary: "#284d40"
  primary-hover: "#3b6150"
  background: "#f6f7f5"
  paper: "#ffffff"
  ink: "#263832"
  muted: "#65716b"
  border: "#dce2dd"
  selected: "#dce5dd"
  success-background: "#dceade"
  success-ink: "#244c34"
typography:
  display:
    fontFamily: "Rain Serif, Noto Serif CJK SC, Songti SC, SimSun, serif"
    fontSize: "32px"
    fontWeight: 500
    lineHeight: 1.45
  body:
    fontFamily: "Rain Sans, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.65
  prose:
    fontFamily: "Rain Serif, Noto Serif CJK SC, Songti SC, SimSun, serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 2.1
rounded:
  control: "6px"
  panel: "8px"
  writing-sheet: "10px"
spacing:
  small: "8px"
  medium: "16px"
  large: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-success:
    backgroundColor: "{colors.success-background}"
    textColor: "{colors.success-ink}"
    rounded: "{rounded.control}"
---

# Design System: 潮湿雨季

## Overview

主界面优先呈现开始创作、继续草稿和实际记录。宋体用于标题和文章，黑体用于操作和辅助说明。底色采用浅灰白和灰绿，主按钮使用墨绿。

## Colors

背景、纸面与侧栏依靠轻微色差划分区域。正文使用 ink，提示使用 muted，边线使用 border。错误反馈保留暗红语义色。成功按钮无论鼠标是否悬停，均使用浅绿底、深绿字。

## Typography

`Rain Serif` 是本地 Noto Serif SC 的 500 字重子集；`Rain Sans` 是本地 Noto Sans SC 的 400–650 可变字重子集。字体、许可位于 `frontend/public/fonts`。覆盖 GB2312 常用字、标点及项目文案，其余字符由系统中文字体补充。`font-display: swap`，预加载操作字体。

常规页面标题 32px；工作台标题随屏幕在 28–38px 内变化；首次引导标题为 31–53px。工作台区域标题 14–15px，操作文字 12–14px，辅助说明 11–12px。编辑正文 17px、2.1 行高、最大 75ch。不要在操作区重新引入未加载的独立展示字体。

## Layout

桌面侧栏 212px，内容容器最大 1228px（含左右内边距）。工作台主体采用 12 栏网格，新稿区占 8 栏、草稿区占 4 栏。651–950px 使用 82px 图标侧栏与 7/5 栏主体；650px 以下改为单列和底部导航。移动端正文留足底部导航及安全区域。

## Elevation & Depth

纸面与编辑器仅使用很淡的软阴影，普通按钮保持平面。焦点使用清晰的绿色描边；异步等待通过状态文字与图标说明，不靠阴影传达。

## Shapes

按钮圆角 6px，普通面板 8px，新稿纸面 10px。首次引导使用拱形雨纹图形；日常工作台以文字和真实内容为主。

## Components

`ActionButton` 统一保存、连接测试、建稿、生成、检查和导出时的状态：默认图标、等待文案和转圈、完成勾选。等待期间阻止重复提交；失败显示具体错误并恢复可操作状态。编辑器保存期间暂时锁定正文与标题，保存完成后恢复编辑；用户再次改动时退出“已保存”状态。

按钮按下反馈 80ms，松开和颜色变化 180ms。导航指示背景 300ms 移动，页面切换 200ms，表单展开 260ms。启动欢迎页播放雨滴落下、五圈涟漪展开和“欢迎”逐字显现，停留 2200ms 后用 360ms 退出；首次引导后的欢迎页等待用户进入。欢迎文字不带句号，支持跳过和重播。减少动态效果模式跳过自动开场，并同时清除动画时长与延迟，保留状态文字和颜色。

## Do's and Don'ts

- 使用真实数据和诚实的空状态。
- 每个关键操作提供 hover、press、focus、disabled、busy、success 或 error 状态。
- 使用现有 Lucide 图标系统，避免用字符模拟工具图标。
- 保留真实流程步骤，避免在标题上方叠加装饰性步骤标签。
- 字体资产必须随发布包提供，不能只在本机可见。
