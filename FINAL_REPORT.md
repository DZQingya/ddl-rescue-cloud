# DDL 急救站 · 最终交付报告

- 发布版本：`v0.9.2-auto-takeover`
- 日期：2026-11-24
- PC / Web 入口：`work/app.py`
- 发布仓库：https://github.com/DZQingya/ddl-rescue-cloud
- Android：`v1.2.0`（包名 `com.ddl.rescue`）

## 1. 本轮交付结论

软件整合、版本冻结、PC 一键包、自动化回归和发布文档已完成。当前没有由自动化回归确认的阻断项。

本轮新增并确认：

- `work/app.py` 与 `work/app_guided.py` 的 `APP_VERSION` 已统一为 `v0.9.2-auto-takeover`；
- 启动脚本可识别旧版 8501 实例并自动接管；
- PC 一键包已按最终源码重建；
- 包内不包含 `workspace.db`、`llm_settings.json`、`.venv` 或 `.git`；
- 包内启动文件、源码、测试和大模型配置模块齐全；
- 本地服务健康检查返回 `HTTP 200 / ok`。

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

原始回归日志：

`release-evidence\regression-20261124.log`

日志 SHA256：

`D41A00A376B5D0BD62BE74C244E24172B989EC39A7F0CE51FE4253FCA8BFF44A`

## 3. 交付物校验

### PC 一键部署包

文件：`D:\Downloads\DDL-guided-oneclick-v2-20261122.zip`

- 大小：131,597 字节
- ZIP 条目：34
- 包含 `一键部署.bat`、`启动.bat`、`launch_local.ps1`、最终源码和测试
- 禁止项检查：`workspace.db=0`、`llm_settings.json=0`、`.venv=0`、`.git=0`
- SHA256：`43829AD50576736A4FA21D90D8F06D48CF2C3B0B71E40AED9AC017C1ADBD72AB`

### Android APK

文件：`D:\Downloads\DDL急救站-v1.2.0-android.apk`

- 包名：`com.ddl.rescue`
- versionName：`1.2.0`
- versionCode：`3`
- minSdk：`26`
- targetSdk：`34`
- INTERNET 权限：有
- 签名 v2：有
- 大小：74,347 字节
- SHA256：`6321462CF33537C83BB291BA4E88B4D840A263641088A49C0FE5AAF70773745A`

APK 结构为 Android WebView + 本地网页资源，入口资源为 `assets/www/index.html`，不是 React Native 原生界面。

## 4. 使用方式

### PC

解压 PC 一键包，双击 `一键部署.bat`。首次运行会创建运行环境、安装依赖、生成桌面快捷方式并启动。以后使用桌面“DDL急救站”或包内 `启动.bat`。

本地地址：`http://localhost:8501`

### Android

把 APK 传到安卓手机安装。规则模式可离线使用；使用云端大模型时需要网络并配置 API Key。Ollama / LM Studio 适合本机或局域网模型。

## 5. 验证边界

以下内容没有被自动化测试冒充为已验证：

- 本轮完成了 APK 元数据、签名、权限、资源结构校验，但没有把它写成“实体安卓真机已验收”。真机安装、启动、返回键、键盘遮挡和弱网仍需由负责 APK 的组员在实体手机上完成最终冒烟；
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

**自动化与打包判定：PASS。**

**发布前唯一外部动作：在实体安卓手机上安装 APK，完成一次真实打开和核心流程冒烟，并保留截图/录屏。**