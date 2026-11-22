# DDL 急救站 · v0.9.1 Cloud + APK

组员 v0.9-sync-mobile 合并版，保留桌面快捷方式、一键部署、拖拽排序、积分奖励和任务级删除。

## 功能

- 三步急救：粘贴通知 → 生成计划 → 今天做；
- 多 DDL 工作台与任务级状态；
- 大卡片直接拖动排序；
- 保底 / 进阶 / 挑战与积分奖励；
- 删除单个任务，保留同通知其他任务；
- LLM 设置页：DeepSeek / 通义千问 / 智谱 GLM / Kimi / OpenAI / 硅基流动 / Ollama / LM Studio；
- 日历选时、手动确认截止时间；
- PC 一键部署包与 Android APK 应用内下载。

## 运行

```powershell
python -m pip install -r requirements.txt
python -m streamlit run work\app.py
```

Windows 一键部署：解压 ZIP 后双击 `一键部署.bat`。首次部署会创建桌面快捷方式，包内可用 `启动.bat` 重新打开。

## 数据边界

- 默认关闭大模型时纯本地规则，不联网；
- 开启大模型后通知原文会发送到配置的模型服务；
- `data/workspace.db` 和 `data/llm_settings.json` 属于本地运行数据，不进入 Git 仓库；
- 云端与本地数据不会自动同步。

## 回归

```powershell
python tests\test_sync_v09.py
```
