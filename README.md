# 彦博-v3

彦博-v3 是由用户命名、在本机运行的个人多模态 AI 助手项目，项目目录为 `D:\LLM`。

项目统一身份只有一个：**彦博-v3**。`彦博-快速`、`彦博-思考`、`彦博-专家` 是同一个彦博-v3的三种能力模式，不是三个不同模型，也不会在界面、回答、文档或发布包中展示其他模型品牌。

## 当前状态

- 统一运行模型：`yanbo-v3:latest`
- 本地核心别名：`yanbo-v3-core:latest`
- Android、iOS 工程包和完整手机发布包：`1.1.10`
- 兼容训练累计：正式适配器保持 700 步；第4轮两个候选均尝试到 720 步，因独立任务低于基线而拒绝发布
- 正式引擎第4轮主泛化评测：`21/48 → 48/48`；发布前新留出集：`28/28`
- Git 主分支：`main`
- 手机端支持后台继续生成、断线恢复、任务去重和重新打开后续接
- 图片默认采用增强、OCR、校验、彦博-v3分析流程

## 三种能力模式

| 模式 | 运行模型 | 上下文 | 最大文字输出 | 适用场景 |
|---|---|---:|---:|---|
| 彦博-快速 | `yanbo-v3:latest` | 8192 | 4096 tokens | 普通问答、快速解释、简短代码 |
| 彦博-思考 | `yanbo-v3:latest` | 12288 | 8192 tokens | 课程题、代码分析、多步骤问题 |
| 彦博-专家 | `yanbo-v3:latest` | 16384 | 12288 tokens | 长代码、专业资料、复杂推理 |

三种模式只调整上下文、输出预算和生成参数，身份与运行模型永久保持为彦博-v3。

## 快速入口

| 文件 | 用途 |
|---|---|
| `00_setup.bat` | 安装依赖、检查兼容训练模型并构建彦博-v3 |
| `01_train.bat` | 从当前断点继续普通训练 |
| `02_chat.bat` | 命令行流式聊天 |
| `03_web_chat.bat` | 电脑网页聊天 |
| `04_deep_train.bat` | 长时间深度训练 |
| `05_mobile_server.bat` | 同一 Wi-Fi 下启动手机服务 |
| `07_secure_mobile_access.bat` | 检查或修复公网服务 |
| `08_build_android_app.bat` | 构建当前 Android APK/AAB |
| `09_publish_mobile_update.bat` | 增加版本并发布手机更新 |
| `10_cleanup_cache.bat` | 清理缓存和构建中间产物 |
| `11_enable_auto_start.bat` | 注册登录后后台自启动 |
| `12_disable_auto_start.bat` | 关闭后台自启动 |
| `13_import_knowledge.bat` | 导入本地知识资料 |

## 当前发布包

```text
D:\LLM\releases\Yanbo-AI-Android-v1.1.10.apk
D:\LLM\releases\Yanbo-AI-Android-v1.1.10.aab
D:\LLM\releases\Yanbo-AI-iOS-Project-v1.1.10.zip
D:\LLM\releases\Yanbo-Mobile-Release-v1.1.10.zip
D:\LLM\releases\彦博手机访问二维码.png
```

Android 正式包继续使用固定签名，可以覆盖安装旧版本。签名目录为：

```text
mobile_app\android\signing
```

该目录和 `remote_access.json` 必须单独安全备份，不能提交到公开仓库。

## 手机连接

### 公网 HTTPS

```text
https://laptop-m4o3b2hb.tail692923.ts.net/yanbo
```

Android 正式包已经内置服务器配置。电脑需要保持开机、联网，并让彦博后台服务正常运行。

### 同一 Wi-Fi

运行：

```text
05_mobile_server.bat
```

手机与电脑连接同一 Wi-Fi 后，打开终端显示的局域网地址。

## 核心架构

```text
命令行 / 电脑网页 / Android / iOS / PWA
                    ↓
                web_chat.py
                    ↓
             AssistantEngine
       ┌────────────┼────────────┐
       ↓            ↓            ↓
   彦博-v3运行   本地知识库   数学/OCR/格式工具
                    ↓
          会话记忆、训练示例与输出校正
```

### 主要模块

| 文件或目录 | 作用 |
|---|---|
| `assistant_engine.py` | 彦博-v3推理、流式输出、工具、记忆和视觉路由 |
| `web_chat.py` | 网页服务、手机 API、任务续接和应用下载 |
| `capability_config.json` | 快速、思考、专家三模式参数 |
| `response_contract.py` | 数量、句数、简洁和成品输出约束 |
| `behavior_examples.py` | 从训练数据检索相似行为示例 |
| `knowledge_base.py` | 本地资料切块、索引和检索 |
| `import_knowledge.py` | PDF、Word、图片、文本和代码导入 |
| `image_understanding.py` | 图片增强、OCR 和阅读顺序恢复 |
| `models/yanbo-v3-compat` | 彦博-v3兼容训练模型 |
| `adapters/yanbo-v3-compat-lora` | 彦博-v3兼容训练参数和断点 |
| `mobile_app/` | Android、iOS 和共享前端工程 |
| `releases/` | APK、AAB、iOS 工程包和完整发布包 |

## 图片能力

默认图片流程：

```text
图片格式检查
→ 方向修正与缩放
→ 灰度、对比度和锐化增强
→ OCR文字识别
→ 公式与文字校验
→ 彦博-v3分析并流式回答
```

支持 JPG、PNG、WEBP、BMP，单张图片最大 15 MB。识别结果有歧义或缺少条件时，彦博-v3必须明确说明，不得自行补造题目。

## 本地知识库

把资料拖到 `13_import_knowledge.bat`，或运行：

```text
python import_knowledge.py "D:\课程资料" "D:\项目文档\说明书.pdf"
```

资料会转换到 `knowledge\generated\`，下次提问时自动检索，无需重新训练或重启服务。私人知识资料默认不进入 Git。

## 继续训练

普通训练：

```text
01_train.bat
```

深度训练：

```text
04_deep_train.bat
```

当前兼容训练状态：

- 已完成 4 个训练与能力升级轮次
- 正式适配器累计 700 步，训练断点仍为 `adapters\yanbo-v3-compat-lora`
- 第4轮广覆盖数据：训练集 2358 条、验证集 19 条
- 第4轮失败簇专项数据：训练集 3003 条、验证集 12 条
- 两套数据均为零重复样本、零空样本、零不可用答案、零训练/验证完整样本泄漏
- 广覆盖候选尝试到 720 步，最佳检查点 710 步，独立得分 `17/48`，拒绝发布
- 失败簇候选训练到 720 步，验证损失 `2.0666 → 2.0257`，独立得分 `17/48`，拒绝发布
- 正式 700 步兼容模型基线为 `18/48`，因此本轮没有用退化候选覆盖正式适配器
- 正式运行引擎通过思考预算、格式契约、真实性和确定性能力链升级，由 `21/48` 提升到 `48/48`
- 发布前使用全新数字、实体和措辞建立 28 题留出集，结果 `28/28`
- 旧正式适配器备份继续保存在 `adapters\backups\`

兼容训练主要用于表达风格、固定格式、小范围能力补强和正式服务不可用时的回退。日常运行的快速、思考和专家模式始终使用统一的 `yanbo-v3:latest`。第4轮完整过程见 `training_reports/ROUND4_TRAINING_REPORT_2026-07-25.md`。

## 测试

```text
python verify_identity.py
python evaluate.py
python evaluate_multimodal.py
python evaluate_web_upload.py
python evaluate_mobile_app.py
python evaluate_capability_upgrade.py
python evaluate_model_upgrade.py --full
python evaluate_round4_generalization.py --execution engine --engine-backend native
python evaluate_round4_release_holdout.py
```

`verify_identity.py` 会检查：

- 项目名称必须是彦博-v3
- 三种模式必须全部使用 `yanbo-v3:latest`
- Git 公开文本不得出现外部模型品牌

第4轮训练与正式引擎升级实际回归结果：

```text
广覆盖训练数据：2358条；验证数据：19条
失败簇训练数据：3003条；验证数据：12条
数据审计：零重复样本、零空样本、零不可用答案、零训练/验证完整样本泄漏
正式兼容模型基线：18/48
广覆盖LoRA候选：17/48，拒绝发布
失败簇LoRA候选：17/48，拒绝发布
正式运行引擎：21/48 → 48/48
发布前新留出集：28/28
旧18题专项：18/18
模型升级完整评测：10/10
完整基础与代码质量：12/12
数学工具：7/7
OCR识别：2/2；图片做题：通过；网页上传入口：通过
手机端端到端：15/15
身份统一与公网远程访问：通过
```

## 身份规则

1. AI 的唯一正式名称是 **彦博-v3**。
2. 快速、思考、专家只是同一彦博-v3的能力档位。
3. 回答中不得披露或猜测底层实现、供应商或内部组件。
4. 代码、界面、文档、更新信息和发布包统一使用彦博命名。
5. 提交 Git 前必须运行 `python verify_identity.py`。

详细手机说明见 `手机应用安装与更新说明.md`，能力分层说明见 `能力升级与专家模式说明.md`。
