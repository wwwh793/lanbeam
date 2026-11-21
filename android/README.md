# LanBeam · 安卓端

LanBeam 是一个局域网文件互传工具：同一 Wi-Fi 下自动发现、直接收发，不过任何服务器。
这是安卓客户端（Windows 端源码在仓库根目录的 `src/`，协议见 `PROTOCOL.md`）。

- 包名：`com.moyuli.lanbeam`
- 最低支持：Android 7.0（API 24），目标 API 35
- 许可：MIT

## 功能

- **发现**：UDP 47820 广播，收到广播立刻单播回执；掉线判定按对端节奏自适应（3×间隔，钳 8–30 秒）。
- **接收**：HTTP 47821，逐个确认或自动接收；端口被占用会自动换，并在广播里带真实端口。
- **发送**：系统文件选择器多选、文件夹（保留子目录与空目录）、系统相册。
- **断点续传**：文件指纹按协议用 sha256，与 Windows 端同口径，跨端能续上。
- **收件箱**：接收落应用内收件箱，可打开、导出到系统「下载/LanBeam」（MediaStore，不申请存储权限）或删除。
- **界面**：深色 / 浅色 / 跟随系统；前台服务保持后台接收。

## 结构

```
android/
├── app/src/main/
│   ├── AndroidManifest.xml
│   ├── java/com/moyuli/lanbeam/
│   │   ├── core/          # 纯 Java，不依赖任何 Android API（可在桌面 JVM 上跑）
│   │   │   ├── Json.java        # 极简 JSON
│   │   │   ├── Types.java       # 协议常量、Peer
│   │   │   ├── Net.java         # 网卡与广播地址
│   │   │   ├── Paths.java       # 路径清洗、重名、越界防护
│   │   │   ├── Discovery.java   # UDP 发现
│   │   │   ├── BeamServer.java  # 手写 HTTP/1.1 接收服务
│   │   │   ├── Sender.java      # /hello → /offer → /status → /upload
│   │   │   ├── Core.java        # 组装
│   │   │   └── Human.java
│   │   ├── ui/            # 自绘控件（不引 AndroidX）
│   │   ├── App.java  BeamService.java  MainActivity.java
│   │   ├── SettingsActivity.java  LogsActivity.java  InboxActivity.java
│   │   ├── SendPlan.java  Exports.java  InboxProvider.java  Files.java  Texts.java
│   └── res/
├── 测试/                  # 桌面 JVM 对拍（Java 核心 ↔ Python 端）
├── build.ps1
└── README.md
```

核心层刻意不碰安卓 API：这样能直接在桌面 JVM 上跑，和 Python 实现对照测试，协议问题在出包前就发现。

## 构建

不依赖 Gradle，命令行直出 APK：

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:ANDROID_SDK = "$env:LOCALAPPDATA\Android\Sdk"
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

依赖：

- JDK 17+（需要 javac；构建脚本用 javac 编译）
- Android SDK：`platforms;android-35`、`build-tools;35.0.0`

流程：复制到临时目录（aapt2 不认非 ASCII 路径）→ aapt2 compile/link → javac → 打包 classes → d8 →
塞 classes.dex → zipalign → apksigner。产物在 `dist/LanBeam-<版本>.apk`。

首次构建会在 `签名/lanbeam.jks` 生成一个自用签名（口令 `lanbeam`）。**以后升级必须用同一个密钥**，
否则手机上装不上去（要先卸载）。`签名/` 已在 .gitignore 里，不会提交。

改版本号：`-Version 1.0.2 -VersionCode 1000002`，同时改 `Texts.java` 的 `VERSION`。

也可以直接用 Android Studio 打开本目录（附带 Gradle 配置，不含第三方依赖）。

## 测试

`测试/CoreHarness.java` 在桌面 JVM 上跑核心层，`测试/驱动.py` 拉 Python 端（仓库 `src/lanbeam_core.py`）对拍：

```bash
javac -encoding UTF-8 -d android/_build/classes android/app/src/main/java/com/moyuli/lanbeam/core/*.java android/测试/CoreHarness.java
python android/测试/驱动.py
```

覆盖：双向收发、断点续传（含 fid 口径）、路径穿越拒绝、UDP 发现。

## 已知限制

- 明文传输（协议现状），只在可信网络使用；公共 Wi-Fi 建议关掉「自动接收」。
- 不支持 0 字节空文件（与 Windows 端一致）。
- 国产 ROM 会冻结后台应用（ColorOS 实测约 2 分钟）：长时间后台接收需要在系统设置里允许 LanBeam 后台运行。
- 一次只能发一个文件夹，或一批文件。

## License

MIT，见仓库根目录的 LICENSE。
