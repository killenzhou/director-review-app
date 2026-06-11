# DaVinci CGT 审核插件

## 启动方式

1. 将 `DaVinci_CGT_Review_Launcher.py` 复制到 DaVinci Resolve 脚本目录：
   `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility`
2. 如项目目录不在默认路径，先设置环境变量：
   `DAVINCI_CGT_REVIEW_ROOT=F:\alienbrainWork\killen\协同审阅平台\director_review_app-原文件\director_review_app`
3. 在 Resolve 菜单 `Workspace > Scripts > Utility` 中运行脚本。

## 功能

- 通过：读取播放头下当前片段名，解析镜头号，写入 CGT `task.supervise_status=审核通过`。
- 返修：录屏/录音，支持截图批注、AI 整理、部门选择、参考文件拖拽，确认后同步 CGT。
- 待 Check 列表：按当前播放头镜头解析本集，查询 CGT 中待审核/待Check 的视效任务。
- 状态查询：查看当前镜头全部 CGT 环节状态。

