# 本地中文字体

界面使用 Noto Sans SC 与 Noto Serif SC，来源为 Google Fonts 官方仓库的 `ofl/notosanssc`、`ofl/notoserifsc`。

- `RainSans-SC.woff2`：Noto Sans SC，400–650 字重范围，用于操作与说明。
- `RainSerif-SC.woff2`：Noto Serif SC，500 字重，用于标题与文章。

两者均按 GB2312 常用字符、ASCII、中文标点和项目文案进行子集化。字体随 `frontend/public/fonts` 打包，缺少的生僻字符由系统字体回退。没有外部字体请求。

对应的完整 SIL Open Font License 在同一目录的 `NotoSans-LICENSE.md` 和 `NotoSerif-LICENSE.md` 中。分发时必须保留许可文件。
