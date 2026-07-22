# 彦博-v3

彦博-v3 是由你命名并在本机运行的多模态语言模型项目，目录为 `D:\LLM`。

当前能力包括：

- 流式中文聊天
- 数学做题与精确计算
- Python、C、C++、JavaScript、SQL 等代码辅助
- 图片文字识别与拍照做题
- 本地专业知识库自动检索
- 训练样本相似示例检索，让主力模型直接复用已训练能力
- 数量、句数、简洁和成品输出等硬约束校正
- 多轮长上下文记忆
- 多会话新建、切换、搜索、重命名与删除
- 彦博-快速、彦博-思考与彦博-专家三种能力模式
- 可配置更强本地模型或远程专家模型
- 流式心跳、断线自动恢复与请求去重
- Android 原生应用
- iPhone/iPad 可安装网页应用
- 应用版本检查与更新
- 断点续训与自动评估

## 快速入口

| 文件 | 用途 |
|---|---|
| `01_train.bat` | 从现有断点继续训练，每轮增加新数据 |
| `02_chat.bat` | 命令行流式聊天 |
| `03_web_chat.bat` | 电脑网页聊天 |
| `04_deep_train.bat` | 长时间深度训练 |
| `05_mobile_server.bat` | 同一 Wi-Fi 下启动手机服务 |
| `07_secure_mobile_access.bat` | 手动检查或修复公网服务 |
| `08_build_android_app.bat` | 重新构建当前 Android 正式包 |
| `09_publish_mobile_update.bat` | 自动增加应用版本并发布更新 |
| `11_enable_auto_start.bat` | 重新注册开机后台自启动 |
| `12_disable_auto_start.bat` | 关闭开机后台自启动 |
| `13_import_knowledge.bat` | 导入 PDF、Word、图片、文本和代码资料到本地知识库 |

第一次补装运行环境时使用：

```text
00_setup.bat
```

## 手机应用

Android 正式安装包：

```text
D:\LLM\releases\Yanbo-AI-Android-v1.1.9.apk
```

Android 应用商店包：

```text
D:\LLM\releases\Yanbo-AI-Android-v1.1.3.aab
```

iOS 原生工程包：

```text
D:\LLM\releases\Yanbo-AI-iOS-Project-v1.1.3.zip
```

完整手机发布包：

```text
D:\LLM\releases\Yanbo-Mobile-Release-v1.1.3.zip
```

公网访问二维码：

```text
D:\LLM\releases\彦博手机访问二维码.png
```

详细安装步骤见：

```text
手机应用安装与更新说明.md
```

## 手机连接方式

### 公网 HTTPS

已注册为 Windows 登录后后台自启动，无需每次手动点击 BAT。后台守护程序会自动恢复意外退出的本地服务。

当前公网地址：

```text
https://laptop-m4o3b2hb.tail692923.ts.net/yanbo
```

该地址由 Tailscale Funnel 转发到本机服务。安卓正式应用已内置服务器地址和访问凭据，没有服务器设置入口，打开即可使用移动数据、其他 Wi-Fi 或异地网络连接。

### 同一 Wi-Fi

双击：

```text
05_mobile_server.bat
```

终端会显示类似：

```text
http://192.168.1.10:7860
```

手机与电脑连接同一个 Wi-Fi 后打开该地址。

## Android 应用信息

```text
应用名：彦博 AI
包名：com.yanbo.ai
应用版本：1.1.9
最低系统：Android 6.0
目标系统：Android 15
正式签名：已生成并验证
```

固定签名位于：

```text
mobile_app\android\signing
```

必须备份这个目录。后续 APK 只有继续使用同一签名，才能直接覆盖安装旧版本。

## iPhone 与 iPad

苹果设备当前有两种使用方式：

1. 使用 Safari 打开公网 HTTPS 地址，并在网页端配置访问令牌后添加到主屏幕；
2. 使用 `releases\Yanbo-AI-iOS-Project-v1.1.3.zip` 中的原生工程，在 macOS/Xcode 中选择自己的开发团队后签名安装。

Windows 已生成完整 iOS 工程，但不能在 Windows 上完成苹果签名和 IPA 发布。

## 更新机制

### 模型更新

彦博模型运行在电脑或服务器上。继续训练或升级彦博版本后，手机端会自动使用新模型，不需要重新安装应用。

### Android 应用更新

双击：

```text
09_publish_mobile_update.bat
```

它会自动：

1. 把应用版本从例如 `1.0.0` 增加到 `1.0.1`；
2. 同步 Android 和 iOS 工程；
3. 沿用固定发布签名；
4. 构建新 APK 和 AAB；
5. 打包新的 iOS 工程；
6. 更新服务器中的下载地址与哈希；
7. 让旧版 Android 应用提示下载更新。

### PWA 更新

安装到安卓或苹果主屏幕的网页应用由服务工作线程管理。服务器界面更新后会自动获取新版本。

## 图片做题

网页端支持：

- 点击“＋ 上传图片”
- 直接粘贴截图
- OCR 文字与数学符号识别
- 数学算式自动校验
- 可选专家视觉后端直接分析原图
- 流式输出解题过程

命令行示例：

```text
/image "D:\作业\题目.png" 请详细解答
```

## 继续训练

普通训练：

```text
01_train.bat
```

深度训练：

```text
04_deep_train.bat
```

训练会读取当前微调断点，不会从零开始。当前兼容训练累计约 650 步，长期训练系统会按轮次生成新的数学、代码、逻辑、聊天和 OCR 纠错数据。

兼容模型和 LoRA 主要用于故障回退、固定风格与小范围能力补强。训练流程生成的高质量样本还会被主力运行模型按问题检索，作为少量相似示例参与回答，因此训练成果不再只作用于0.5B回退模型。复杂推理、长代码和专业知识仍优先通过高性能运行时、专家模型与本地知识库提升，详细见 `能力升级与专家模式说明.md`。

导师样本在进入训练集前会检查长度、代码块闭合、回答完整性和无关寒暄；截断或低质量回答会被自动跳过并重新生成，避免错误样本持续污染后续训练。

## 测试

```bash
python evaluate.py
python evaluate_multimodal.py
python evaluate_web_upload.py
python evaluate_mobile_app.py
python evaluate_capability_upgrade.py
python evaluate_model_upgrade.py --full
```

当前结果：

```text
数学工具：7/7
图片文字识别：2/2
图片做题：通过
网页上传与粘贴：通过
手机客户端：12/12
能力分层、知识检索与专家后端：5/5
主力模型数据联动与指令遵循：9/9
身份与多轮记忆：通过
```

## 目录结构

```text
models/                 兼容模型本体
adapters/               微调参数与训练断点
data/                   当前训练集、验证集和轮次记录
knowledge/              用户本地专业知识资料与导入结果
mobile/                 可安装网页应用资源
mobile_app/android/     Android 原生工程
mobile_app/ios/         iOS 原生工程
mobile_app/tools/       构建、补丁、图标和发布工具
releases/               Android APK、AAB 与 iOS 工程包
assistant_engine.py     推理、流式输出、工具、知识检索和视觉路由
capability_config.json  快速、思考和专家模式配置
knowledge_base.py       本地知识库索引与检索
import_knowledge.py     PDF、Word、图片和文本资料导入
image_understanding.py  图片增强与文字识别
web_chat.py             网页、手机服务和应用下载接口
train_yanbo.py          长期训练编排
```

## 重要说明

手机应用是彦博的客户端，模型主体继续在电脑或服务器运行。这样可以保留当前高性能能力，避免把大型模型强行塞入手机后造成体积过大、速度下降和内存不足。

因此使用手机时，电脑或部署彦博的服务器需要保持开机，并运行手机服务。当前主要本地后端约为 8B 参数模型，0.5B LoRA 模型仅作为兼容回退；更高难度任务可以在专家模式中配置更强模型。重要题目、代码和事实仍应进行必要核验。
