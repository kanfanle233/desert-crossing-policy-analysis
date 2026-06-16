# 高级算法对比摘要

| 关卡 | 算法 | 可行 | 目标值 | 到达日 | 用时秒 | 状态 |
|---|---|---:|---:|---:|---:|---|
| 1 | current_dp | True | 11212.50 | 30 | 0.0009 | current_dp |
| 1 | astar_dp | True | 11212.50 | 30 | 0.0005 | astar_dp |
| 1 | rcsp_label | True | 11212.50 | 30 | 0.0006 | rcsp_label |
| 1 | milp_exact | True | 11212.50 | 30 | 8.3771 | milp_time_limit_incumbent |
| 2 | current_dp | True | 12317.50 | 30 | 0.0007 | current_dp |
| 2 | astar_dp | True | 12317.50 | 30 | 0.0005 | astar_dp |
| 2 | rcsp_label | True | 12317.50 | 30 | 0.0005 | rcsp_label |
| 2 | milp_exact | True | 12317.50 | 30 | 8.2009 | milp_time_limit_incumbent |
| 3 | robust_rcsp | True | 9670.00 | 3 | 0.0012 | robust_rcsp |
| 3 | mcts_rollout | True | 9670.00 | 3 | 0.0022 | mcts_rollout |
| 3 | ga_search | True | 9670.00 | 3 | 0.0010 | ga_search |
| 3 | sa_search | True | 9670.00 | 3 | 0.0014 | sa_search |
| 4 | robust_rcsp | True | 9120.00 | 8 | 0.0015 | robust_rcsp |
| 4 | mcts_rollout | True | 9120.00 | 8 | 0.0035 | mcts_rollout |
| 4 | ga_search | True | 9120.00 | 8 | 0.0018 | ga_search |
| 4 | sa_search | True | 9120.00 | 8 | 0.0042 | sa_search |
| 5 | coalition_search | False | 9392.50 |  | 0.3952 | coalition_search |
| 5 | best_response_check | False | 9392.50 |  | 0.4133 | best_response_check |
| 6 | coalition_search | False | 9120.00 |  | 0.0212 | coalition_search |
| 6 | best_response_check | False | 9120.00 |  | 0.0109 | best_response_check |

说明：`current_dp` 为现有提交求解器；`milp_exact` 为时间扩展网络 MILP 校验；若状态为 `milp_time_limit_incumbent`，表示大实例达到 MILP 时间上限，表中目标值引用正式 DP incumbent；智能优化算法使用固定随机种子，作为论文对照组。
