# 协同审阅平台

面向导演/制作审阅流程的桌面工具，支持录屏录音、OCR、FunASR 中文语音转写、AI 整理反馈、Excel/视频导出、网页预览和 CGTeamWork 同步。

## 本地运行

1. 准备 Python 虚拟环境 `director_tool_env`。
2. 安装依赖：

```bat
director_tool_env\Scripts\python.exe -m pip install -r requirements.txt
```

3. 准备本地运行资产：

- `external_files\ffmpeg.exe`
- `Tesseract-OCR\`
- `FunASR-main\`
- `FunASR_models\`
- 可选本地 AI：`Qwen3-VL-8B\` 和 `llama-cpp\`

4. 启动：

```bat
启动.bat
```

## 打包

生成非单文件 exe（one-folder，可看到外部运行文件）的方式：

```bat
build_all_in_one.bat
```

产物目录：

```text
dist\协同审阅平台_完整版\
```

该目录适合作为 GitHub Release 附件上传。仓库本身不提交模型、虚拟环境、Tesseract、FFmpeg、构建产物和 `old` 归档。

## 语音模型

当前只保留 FunASR 转写链路：

- `funasr-paraformer-zh`
- `fsmn-vad`
- `ct-punc`

旧的 Faster-Whisper / `large-v3-ct2` 模型已不再作为打包依赖。

