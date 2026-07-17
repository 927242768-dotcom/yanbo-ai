# 彦博项目清理报告

清理日期：2026-07-13

## 已保留

- `models/`：当前兼容模型本体
- `adapters/`：彦博微调参数、适配器和训练断点
- `data/`：当前训练集、验证集、导师数据和轮次记录
- 推理、流式输出、图片识别、训练、评估与版本发布脚本
- `mobile/`：Android/iPhone 可安装网页应用资源
- `mobile_app/android/`：Android 原生工程与固定签名
- `mobile_app/ios/`：iOS 原生工程
- `mobile_app/tools/`：Android构建、工程补丁、图标和更新发布工具
- `releases/`：正式 APK、AAB、iOS工程包、二维码和完整手机发布包
- 启动脚本、依赖清单和说明文档
- `mobile_app/node_modules/`：后续同步和发布应用更新所需的构建依赖

## 已删除

- 第一代从零训练的百万参数模型源码：`model.py`、`tokenizer.py`、`dataset.py`、`train.py`、`build_dataset.py`
- 第一代模型检查点：`checkpoints/`
- 第一代训练数据：`data/train.jsonl`、`data/val.jsonl`
- Python字节码缓存：所有 `__pycache__/`
- 开发调试截图：`.devspace-computer/`
- Windows误生成空文件：`NUL`
- Android临时编译目录：`.gradle/`、`app/build/`、各子工程 `build/`
- 已废弃的SVG网页图标
- 模型下载缓存中的非运行文件

## 当前清理原则

不会删除模型本体、微调参数、训练断点、签名文件、发布包或手机应用源码。Android构建缓存可以随时重新生成，因此每次正式发布后可双击 `10_cleanup_cache.bat` 清理。

## 重要备份

必须备份：

```text
mobile_app\android\signing
```

该目录中的固定签名决定后续Android版本能否覆盖安装旧版本，不能丢失，也不应公开发送其中的密码配置。
