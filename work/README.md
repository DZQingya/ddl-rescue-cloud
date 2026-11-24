# DDL 急救站开发说明

## 入口

- `work/app.py`：本地与云端 Streamlit 主入口；
- `work/app_guided.py`：同内容的兼容入口；
- `work/mock_engine.py`：规则解析、任务拆解和计划生成；
- `work/model_provider.py`：大模型调用与降级；
- `work/workspace_store.py`：本地任务与状态持久化；
- `work/team_scheduler/`：确定性排期、冲突和容量规则。

## 启动

```powershell
python -m streamlit run work\app.py
```

Windows 发布包使用根目录的 `一键部署.bat` 和 `启动.bat`。

## 测试

```powershell
python tests\test_sync_v09.py
```

## 边界

默认规则模式完全本地运行。配置云端大模型后，通知原文会发送到所选服务商。应用不登录学习通、不代交作业；本地数据库与大模型 Key 不进入版本库。