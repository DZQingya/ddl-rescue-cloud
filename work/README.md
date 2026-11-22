# DDL 急救站 MVP

## 运行

把压缩包解压后，在包根目录运行：

```powershell
.\run.ps1
```

如果 PowerShell 提示执行策略限制：

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

脚本会自动创建 `.venv` 并安装依赖，然后打开 `http://localhost:8501`。

如果虚拟环境已存在，也可以：

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run work\app.py
```

浏览器会打开 `http://localhost:8501`。

## 当前能做什么

- 选择三种模拟通知：清晰 / 模糊 / 冲突；
- 模拟抽取截止时间、交付物、材料、风险；
- 人工复核字段；
- 生成任务拆解、容量检查、今日最小交付、启动动作、保底/进阶/挑战三层目标；
- 使用组员2的确定性排期规则（容量、优先级、依赖、冲突、Rescue Mode）；
- 打卡：开始 / 完成 / 卡住；
- 下载 `.ics` 日历文件。

## 当前不能做什么

- 还不能真实调用多模态大模型；
- 还不能上传截图/PDF；
- 还不能真实发钉钉提醒；
- 还没有登录、数据库、教师端。

## 今天的目标

只验证一件事：

> 用户看到“今日最小交付”后，是否知道今天要完成什么；启动动作只是帮助开始，不是交付本身。

如果“今日最小交付”仍然太虚，或把“打开文件”当成交付，先改 Prompt 和任务拆解规则，不要急着做界面美化。

## 团队规则测试

```powershell
python work\team_scheduler\test_scheduler.py
```

## 下一步替换点

1. 把 `work/mock_engine.py` 里的 `parse_notice()` 替换为真实 LLM 抽取；
2. 把 `build_plan()` 中的任务模板替换为 LLM 任务拆解 + 确定性调度；
3. 加截图上传；
4. 加钉钉 webhook；
5. 加 15 条案例评测。
