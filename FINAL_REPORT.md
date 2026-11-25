# DDL 急救站 · 最终交付报告（Android v1.3.2 更新）

- 发布版本：`v0.9.2-auto-takeover`
- 更新日期：2026-11-25
- PC / Web 入口：`work/app.py`
- 发布仓库：https://github.com/DZQingya/ddl-rescue-cloud
- Android：`v1.3.2`（versionCode 6，包名 `com.ddl.rescue`）

## 1. 本轮更新结论

本次更新以 Android APK v1.3.2 为主，同时同步了下载入口、发布文档、PC 一键包引用和最终提交包。

Android v1.3.2 的新增与修复：

- 点“就按这个做”后，把缩小结果固化为跨页面可见的聚焦卡片，直到用户点“知道了”；
- 卡住结果改为局部刷新，滑动剩余分钟数时不再整页重绘；
- 删除通知、清空数据改用 App 内自绘确认弹层，修复 WebView 中系统 `window.confirm` 不弹出的问题；
- 保留 v1.3.0 的全局“卡住”弹层、按单个 DDL 缩小范围和跨月日期修复；
- APK 包名保持 `com.ddl.rescue`，versionCode 从 4 升到 6；
- 签名 DER SHA256 与前版完全一致，属于同一签名证书，正常情况下可覆盖安装。

## 2. 自动化验证

### v0.9 同步回归

```text
71/71 通过
exit 0
```

覆盖内容：模型服务商预设、地址补全、API Key 校验、本地模型、截止时间归一、多 DDL 解析、降级路径、设置持久化、日历选时、手动确认截止时间、计划生成。

### 7 项核心 UI 回归（串行）

```text
7/7 PASS
exit 0
```

覆盖内容：

1. 急救流程进入“我的任务”后积分到账；
2. 工作台完成任务积分到账；
3. 只删除单个任务，不删除整条通知；
4. 卡住后重置不触发 Streamlit widget 异常；
5. 载入编辑后的强度与奖励正确；
6. “今天做”和目标强度双向同步；
7. 重新进入流程后任务状态与奖励正确。

测试数据已改为相对未来日期，所有 Streamlit 交互统一使用 30 秒超时，避免日期滚动或机器变慢时误报。

原始回归日志：

`release-evidence\regression-20261125-v132.log`

日志 SHA256：

`22C4BC3BFFB0514C6473D0ABB83656D68A5068874943F4EB3A6FAF74E94E9E16`

## 3. 交付物校验

### PC 一键部署包

文件：`D:\Downloads\DDL-guided-oneclick-v2-20261122.zip`

- 大小：131,890 字节
- ZIP 条目：34
- 包含 `一键部署.bat`、`启动.bat`、`launch_local.ps1`、最终源码和测试
- 禁止项检查：`workspace.db=0`、`llm_settings.json=0`、`.venv=0`、`.git=0`
- 源码中的 APK 下载引用：`DDL-rescue-v1.3.2-android.apk`
- SHA256：`7D0BDC5102F587A85BB6DB03C7A521BEF0131F3F42380206C66A92D210546C9B`

### Android APK

文件：`D:\Downloads\DDL急救站-v1.3.2-android.apk`

- 包名：`com.ddl.rescue`
- versionName：`1.3.2`
- versionCode：`6`
- minSdk：`26`
- targetSdk：`34`
- INTERNET 权限：有
- 签名 v2：有
- 签名证书 DER SHA256：`331276C9A70A98177F7E1B48C03427779D5CDAFFBD2A7611DAD392FFFFEC8A64`
- 大小：76,511 字节
- SHA256：`7B9B1266D0159EAA64770361360500AC2C10C501B00B82B8016F914011FD8985`

APK 结构为 Android WebView + 本地网页资源，入口资源为 `assets/www/index.html`，不是 React Native 原生界面。

## 4. 使用方式

### PC

解压 PC 一键包，双击 `一键部署.bat`。首次运行会创建运行环境、安装依赖、生成桌面快捷方式并启动。以后使用桌面“DDL急救站”或包内 `启动.bat`。

本地地址：`http://localhost:8501`

### Android

把 APK 传到安卓手机安装。规则模式可离线使用；使用云端大模型时需要网络并配置 API Key。Ollama / LM Studio 适合本机或局域网模型。

## 5. 验证边界

以下内容没有被自动化测试冒充为已验证：

- 本轮完成了 APK 元数据、签名、权限、资源结构和同证书连续性校验，但没有把它写成“实体安卓真机已验收”；真机安装、启动、返回键、键盘遮挡和弱网仍需在实体手机上完成最终冒烟；
- 71 项大模型测试使用 mock / 本地假服务，不证明所有真实服务商和全部网络环境下的准确率；
- 云端与本地数据不会自动同步；
- 应用不登录学习通、不读取私人账号、不代交作业；
- Android 本地规则模式与 PC 版能力一致，但配置 Key、页面保存和 WebView 行为要以真机结果为准。

## 6. 复现命令

```powershell
cd D:\Downloads\DDL-cloud-deploy-20261122
.\.venv\Scripts\python.exe tests\test_sync_v09.py
```

7 项 UI 回归位于：

`D:\Documents\Codex\2026-10-25\aigc-ddl-rescue\work\qa`

## 7. 最终发布判定

**自动化、签名连续性和打包判定：PASS。**

**发布前唯一外部动作：在实体安卓手机上安装 `D:\Downloads\DDL急救站-v1.3.2-android.apk`，完成一次真实打开和核心流程冒烟，并保留截图/录屏。**