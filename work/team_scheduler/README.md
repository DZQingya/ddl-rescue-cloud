# Team Scheduler 规则层

这是组员2的确定性排期模块，已接入 DDL 急救站主程序。

## 文件

- `scheduler.py`：容量、优先级、依赖、层级闸门、冲突检测、Rescue Mode；
- `adapter.py`：把主程序的“任务 + 保底/进阶/挑战”转换成规则层输入；
- `test_scheduler.py`：12 条自动回归测试；
- `cases/`：测试案例；
- `business_rule.md`：业务规则；
- `json_schema.md`：数据结构；
- `test_results.md`：12/12 测试结果。

## 运行测试

```powershell
python work\team_scheduler\test_scheduler.py
```

期望：`Ran 12 tests ... OK`。

## MVP 集成约定

- 主程序的 `mock_engine.build_plan()` 调用 `adapter.schedule_plan()`；
- 当前只把每个任务的 **保底层** 送进排期；
- 进阶/挑战是可选加练，不进入基础容量计算；
- 没有截止时间时，回退到轻量模拟排期；
- 界面会显示“排期引擎：团队确定性规则”。
