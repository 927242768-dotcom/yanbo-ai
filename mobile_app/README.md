# 彦博 AI 原生手机客户端

本目录包含彦博-v3的 Android 与 iOS 原生客户端工程。

客户端只展示一个 AI 身份：**彦博-v3**。`彦博-快速`、`彦博-思考`、`彦博-专家` 是同一个彦博-v3的三种运行参数，不是不同模型。

## 当前版本

```text
应用版本：1.1.10
Android包名：com.yanbo.ai
最低Android：6.0
目标Android：15
```

当前发布文件：

```text
..\releases\Yanbo-AI-Android-v1.1.10.apk
..\releases\Yanbo-AI-Android-v1.1.10.aab
..\releases\Yanbo-AI-iOS-Project-v1.1.10.zip
..\releases\Yanbo-Mobile-Release-v1.1.10.zip
```

## 目录

```text
android/    Android Studio与Gradle工程
ios/        Xcode工程
www/        Android和iOS共享界面
tools/      构建、补丁、图标、打包和更新工具
```

## 已实现能力

- 多会话新建、切换、搜索、重命名、清空和删除；
- 彦博-快速、彦博-思考、彦博-专家三种模式；
- 流式文字聊天和即时状态反馈；
- 拍照与相册图片上传；
- OCR结果展示和图片做题；
- Markdown、代码块、复制和重新生成；
- 固定服务器自动连接；
- 主地址与备用地址自动切换；
- 网络中断自动重试；
- 后台期间电脑端继续生成；
- 页面或应用重载后自动接回任务；
- 请求编号去重，避免重复生成；
- 应用内更新弹窗、下载进度和安装引导。

## Android

重新构建当前版本：

```text
..\08_build_android_app.bat
```

发布下一个版本：

```text
..\09_publish_mobile_update.bat
```

固定发布签名：

```text
android\signing
```

签名目录不能公开，也不能丢失；后续版本必须继续使用同一签名才能覆盖安装。

## iOS

当前 iOS 工程包：

```text
..\releases\Yanbo-AI-iOS-Project-v1.1.10.zip
```

工程已经包含相机、相册、局域网和网络访问说明。最终签名与 IPA 发布需要在 macOS/Xcode 中完成。

## 服务地址

标准公网地址：

```text
https://laptop-m4o3b2hb.tail692923.ts.net/yanbo
```

电脑端模型主体保持为 `yanbo-v3:latest`。手机只是客户端，因此模型升级、知识库升级和服务端逻辑升级通常不需要重新安装应用。

## 手动同步工程

```text
npm install
npx cap sync
python tools/patch_android_project.py
python tools/inject_remote_config.py
```

## 自动测试

在项目根目录运行：

```text
python verify_identity.py
python evaluate_mobile_app.py
```

测试覆盖多会话、三模式、紧凑布局、文字聊天、图片识别、断线重连、任务流、旧服务兼容、后台生成、重载续接、应用内更新和服务端去重。

当前完整手机端回归结果：

```text
15/15 通过
```
