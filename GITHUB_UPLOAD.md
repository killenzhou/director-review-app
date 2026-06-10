# GitHub 上传准备说明

## 仓库提交内容

仓库只提交源码、脚本和说明文件，不提交以下大文件/本地文件：

- `director_tool_env/`
- `FunASR_models/`
- `FunASR-main/`
- `Tesseract-OCR/`
- `external_files/`
- `Qwen3-VL-8B/`
- `llama-cpp/`
- `build/`
- `dist/`
- `old/`
- `settings.json`

这些内容已经写入 `.gitignore`。

## 当前 exe 产物

已生成 one-folder 形式的非单文件 exe：

```text
dist\协同审阅平台_完整版\协同审阅平台.exe
```

整个目录需要一起分发，不能只拷贝 exe。

## GitHub Release 注意

当前完整版目录约 16 GB。GitHub Release 支持一个 Release 关联多个附件，但单个附件必须小于 2 GiB。

建议：

1. 源码推送到 GitHub 仓库。
2. `dist\协同审阅平台_完整版\` 作为 Release 附件上传。
3. 上传前用 7-Zip 分卷压缩，分卷大小建议 `1900m`：

```bat
7z a -t7z -mx=3 -v1900m 协同审阅平台_完整版.7z dist\协同审阅平台_完整版
```

上传生成的所有分卷，例如：

```text
协同审阅平台_完整版.7z.001
协同审阅平台_完整版.7z.002
...
```

用户下载全部分卷后，解压第一个 `.001` 文件即可还原完整目录。

