# 贡献与开发规范

## 分支约定

- `main`：始终保持可运行、可回退。
- `feature/<name>`：新增功能。
- `fix/<name>`：缺陷修复。
- `docs/<name>`：文档调整。
- `release/<version>`：版本发布准备。

不要直接在 `main` 上进行未经验证的大范围修改。

## 提交约定

提交信息采用以下格式：

```text
<type>: <简明说明>
```

常用类型：

- `feat`：新增功能
- `fix`：修复问题
- `refactor`：重构但不改变外部行为
- `test`：测试相关
- `docs`：文档相关
- `chore`：构建、依赖或维护工作

每个提交应只完成一个明确目标，避免把功能修改、格式化和生成文件混在同一个提交中。

## 提交前检查

至少执行：

```bash
python -m compileall -q .
python evaluate_capability_upgrade.py
```

涉及特定模块时，还应运行对应测试：

```bash
python evaluate.py
python evaluate_multimodal.py
python evaluate_web_upload.py
python evaluate_mobile_app.py
```

## 安全要求

严禁提交以下内容：

- `remote_access.json`
- API 密钥、访问令牌和密码
- Android 发布签名及密码配置
- 私人知识库资料
- 模型本体、LoRA 断点和训练缓存
- APK、AAB、IPA、ZIP 等发布产物

提交前必须检查 `git status` 和 `git diff --cached`，确认暂存区中没有敏感信息、模型文件或生成物。
