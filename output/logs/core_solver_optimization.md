# 核心最优求解器优化记录

## 本次保留的优化

- 将 `prune_dominated_states` 从逐个比较幸存状态的 O(n^2) 支配剪枝，改为同一 `(day, node, finished)` 桶内的 Fenwick 前缀最大查询。
- 将 `solver._prune_bucket` 复用统一 Pareto 剪枝逻辑，避免维护两套支配判断。
- 为高频搜索对象 `PlayerState`、`Action`、`TraceStep` 增加 `slots=True`，降低海量状态搜索时的对象开销。
- 修复 `write_solve_status` 对 `PlayerState.__dict__` 的依赖，使 slots 状态对象可以正常写出日志。

## tuple 精确引擎优化 (v2)

- 新增 tuple 状态引擎 `_solve_tuple_engine`：内部状态使用 `(day, node, cash, water, food, finished)` tuple，避免海量 `PlayerState` dataclass 创建。
- 新增 tuple 版快速补给生成器 `_tuple_purchase_options`：等价 `rules.purchase_options`，但操作 tuple 而非 `PlayerState`。
- 新增 tuple 版 Fenwick 剪枝 `_tuple_prune_dominated`、`_tuple_prune_bucket`、`_tuple_prune_all`：逻辑与原版完全等价，但直接操作 tuple。
- 预计算每日动作消耗表 `_precompute_consumption_table`：`action_table[day] = {kind: (water, food)}`，避免每个状态重复调用 `daily_consumption`。
- 内联 terminal value 计算：`cash + water * water_refund + food * food_refund`，避免为每次比较创建 `PlayerState`。
- 补给后状态去重：在 `_tuple_prune_all` 前先去重，减少重复剪枝计算。
- 公开接口 `solve_deterministic_level(...)` 不变；`SolutionTrace`、Excel 输出、JSON/CSV trace 格式不变。
- `metadata` 增加 `solver_engine="tuple_exact_v2"`、`visited_states`、`max_states_per_bucket`、`purchase_step`。

## 已尝试但撤回的优化

- 行动表预计算、村庄补给缓存、补给生成器内联：在一二关端到端实测中没有稳定收益，部分情况下变慢，因此已撤回。
- `purchase_options` 候选生成裁剪：有扩大搜索耗时的风险，已撤回，仅保留 Pareto 剪枝优化。

## 当前实测

运行命令：

```bash
/usr/bin/time -p /opt/miniconda3/envs/pytorch_env/bin/python run_desert_model.py solve --levels 1,2
```

### 优化前 (dataclass 引擎)

```text
Level 1 solved: objective 11212.50
Level 2 solved: objective 12317.50
Result workbook: output/result/Result_solved.xlsx
real 53.21
user 53.15
sys 0.89
```

### 优化后 (tuple_exact_v2 引擎)

```text
Level 1 solved: objective 11212.50
Level 2 solved: objective 12317.50
Result workbook: output/result/Result_solved.xlsx
real 41.67
user 35.67
sys 1.35
```

纯求解函数计时，不含 CLI、JSON/CSV、Excel 写出：

```text
Level 1: 11.808s, objective 11212.50, visited_states 403837
Level 2: 21.708s, objective 12317.50, visited_states 715763
Total pure solver: 33.516s
```

### 性能对比

| 指标 | 优化前 | 优化后 | 改善 |
|------|--------|--------|------|
| 端到端耗时 | 53.21s | 41.67s | -22% |
| 纯求解耗时 | 约 61.35s | 33.52s | -45% |
| Level 1 objective | 11212.50 | 11212.50 | 不变 |
| Level 2 objective | 12317.50 | 12317.50 | 不变 |
| 测试套件 | 34 tests OK | 37 tests OK | 增加 tuple 等价回归 |

验证：

```text
37 tests OK
validate --levels all: all OK
solve_status.json final_state 正常
Result_solved.xlsx 正常写出
```
