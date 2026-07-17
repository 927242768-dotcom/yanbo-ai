# 彦博 AI 原生手机客户端

本目录包含彦博 AI 的 Android 与 iOS 原生客户端工程。

手机端负责：

- 多会话新建、切换、搜索、重命名、清空和删除
- 流式聊天与即时思考状态
- 拍照做题
- 相册图片上传
- 图片识别与解题
- 固定服务器自动连接
- 应用内更新弹窗、下载进度与安装引导
- 彦博-思考与彦博-快速双模式切换
- 流式心跳、网络切换监听和断线自动恢复

模型主体继续运行在电脑或服务器上，因此不会因手机硬件限制而降低当前彦博-v3的能力。

## 目录

```text
android/    Android Studio/Gradle工程
ios/        Xcode工程
www/        两端共享的手机界面
tools/      构建、补丁、图标、打包和更新工具
```

## Android

当前正式包：

```text
..\releases\Yanbo-AI-Android-v1.1.3.apk
```

重新构建当前版本：

```text
..\08_build_android_app.bat
```

发布下一个版本：

```text
..\09_publish_mobile_update.bat
```

Android固定发布签名：

```text
android\signing
```

必须安全备份整个签名目录，不要公开其中的密码配置。

## iOS

当前工程包：

```text
..\releases\Yanbo-AI-iOS-Project-v1.1.3.zip
```

工程已加入相机、相册、局域网和HTTP/HTTPS连接说明。最终签名与IPA发布需要在macOS/Xcode中选择自己的Apple开发团队。

苹果设备也可以使用公网HTTPS地址安装PWA。

## 服务地址

应用默认服务器：

```text
https://laptop-m4o3b2hb.tail692923.ts.net:8443
```

该地址由 Tailscale Funnel 提供公网访问。电脑登录 Windows 后会自动在后台启动服务并持续检查运行状态。Android 正式包已内置地址与访问凭据，没有服务器设置页面，打开应用即可直接使用。

## 手动同步工程

```bash
npm install
npx cap sync
python tools/patch_android_project.py
python tools/inject_remote_config.py
```

补丁工具会恢复：

- 国内构建镜像
- Java 17兼容
- Android局域网HTTP访问
- Gradle下载镜像

## 自动测试

根目录运行：

```bash
python evaluate_mobile_app.py
```

当前模拟手机测试结果：5/5通过。
