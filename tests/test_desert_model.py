import unittest
from collections import deque

from desert_model.config import load_levels
from desert_model.models import LevelConfig, PlayerState, ResourceSpec, RuleConfig, WEATHER_SUNNY, WEATHER_HOT, WEATHER_STORM
from desert_model.multiplayer import multiplayer_strategy_summary, compute_effect_table
from desert_model.rules import carried_weight, daily_consumption, purchase_options, resource_cost, terminal_value
from desert_model.solver import solve_deterministic_level
from desert_model.validate import validate_level, validate_trace


def tiny_level() -> LevelConfig:
    resources = {
        "water": ResourceSpec(
            name="water",
            mass_kg=1,
            base_price=1,
            base_consumption={WEATHER_SUNNY: 1, "高温": 1, "沙暴": 1},
        ),
        "food": ResourceSpec(
            name="food",
            mass_kg=1,
            base_price=1,
            base_consumption={WEATHER_SUNNY: 1, "高温": 1, "沙暴": 1},
        ),
    }
    return LevelConfig(
        level_id=99,
        name="tiny",
        deadline=2,
        carry_limit_kg=20,
        initial_cash=100,
        base_income=0,
        resources=resources,
        start_node=1,
        goal_node=3,
        weather=(WEATHER_SUNNY, WEATHER_SUNNY),
        adjacency={1: (2,), 2: (1, 3), 3: (2,)},
        rules=RuleConfig(move_multiplier=1.0, mine_multiplier=2.0),
        review_required=False,
    )


class ConfigTests(unittest.TestCase):
    def test_default_config_loads(self) -> None:
        levels = load_levels()
        self.assertEqual(len(levels), 6)
        self.assertEqual(levels[0].name, "第一关")
        self.assertFalse(levels[0].review_required)
        self.assertEqual(levels[4].players, 2)  # Level 5: n=2 from OLE extraction
        self.assertEqual(levels[5].players, 3)  # Level 6: n=3 from OLE extraction

    def test_level_validation_passes_after_review(self) -> None:
        levels = load_levels()
        for level in levels:
            issues = validate_level(level, require_graph=True)
            self.assertEqual(issues, [], f"Level {level.level_id} has issues: {issues}")

    def test_resource_params_match_attachment(self) -> None:
        """Verify resource parameters match the Word attachment tables."""
        levels = load_levels()
        # Level 1 (Table 0): water(3kg, 5元, 5/8/10), food(2kg, 10元, 7/6/10)
        l1 = levels[0]
        self.assertEqual(l1.resources["water"].mass_kg, 3)
        self.assertEqual(l1.resources["water"].base_price, 5)
        self.assertEqual(l1.resources["water"].base_consumption, {"晴朗": 5, "高温": 8, "沙暴": 10})
        self.assertEqual(l1.resources["food"].mass_kg, 2)
        self.assertEqual(l1.resources["food"].base_price, 10)
        self.assertEqual(l1.resources["food"].base_consumption, {"晴朗": 7, "高温": 6, "沙暴": 10})
        self.assertEqual(l1.deadline, 30)
        self.assertEqual(l1.carry_limit_kg, 1200)
        self.assertEqual(l1.initial_cash, 10000)
        self.assertEqual(l1.base_income, 1000)

    def test_level3_params_match_attachment(self) -> None:
        """Level 3 (Table 4): water(3kg, 5元, 3/9/10), food(2kg, 10元, 4/9/10)"""
        levels = load_levels()
        l3 = levels[2]
        self.assertEqual(l3.resources["water"].base_consumption, {"晴朗": 3, "高温": 9, "沙暴": 10})
        self.assertEqual(l3.resources["food"].base_consumption, {"晴朗": 4, "高温": 9, "沙暴": 10})
        self.assertEqual(l3.deadline, 10)
        self.assertEqual(l3.base_income, 200)

    def test_weather_sequences_match_attachment(self) -> None:
        """Verify weather sequences match the Word attachment tables."""
        levels = load_levels()
        # Level 1 weather (Table 1)
        expected_l1 = ["高温", "高温", "晴朗", "沙暴", "晴朗", "高温", "沙暴", "晴朗", "高温", "高温",
                       "沙暴", "高温", "晴朗", "高温", "高温", "高温", "沙暴", "沙暴", "高温", "高温",
                       "晴朗", "晴朗", "高温", "晴朗", "沙暴", "高温", "晴朗", "晴朗", "高温", "高温"]
        self.assertEqual(list(levels[0].weather), expected_l1)
        # Level 5 weather (Table 7)
        expected_l5 = ["晴朗", "高温", "晴朗", "晴朗", "晴朗", "晴朗", "高温", "高温", "高温", "高温"]
        self.assertEqual(list(levels[4].weather), expected_l5)

    def test_start_goal_mines_villages(self) -> None:
        """Verify start, goal, mines, villages match attachment."""
        levels = load_levels()
        self.assertEqual(levels[0].start_node, 1)
        self.assertEqual(levels[0].goal_node, 27)
        self.assertEqual(levels[0].mines, (12,))
        self.assertEqual(levels[0].villages, (15,))
        self.assertEqual(levels[1].goal_node, 64)
        self.assertEqual(levels[1].mines, (30, 55))
        self.assertEqual(levels[1].villages, (39, 62))
        self.assertEqual(levels[2].goal_node, 13)
        self.assertEqual(levels[2].mines, (9,))
        self.assertEqual(levels[3].goal_node, 25)
        self.assertEqual(levels[3].mines, (18,))
        self.assertEqual(levels[3].villages, (14,))


class GraphTests(unittest.TestCase):
    def test_adjacency_symmetric(self) -> None:
        """All adjacency lists must be symmetric: if A->B then B->A."""
        levels = load_levels()
        for level in levels:
            for node, nbrs in level.adjacency.items():
                for nbr in nbrs:
                    self.assertIn(node, level.adjacency.get(nbr, ()),
                                  f"Level {level.level_id}: {node}->{nbr} but not {nbr}->{node}")

    def test_no_self_loops(self) -> None:
        """No node should be its own neighbor."""
        levels = load_levels()
        for level in levels:
            for node, nbrs in level.adjacency.items():
                self.assertNotIn(node, nbrs, f"Level {level.level_id}: self-loop at node {node}")

    def test_graph_connected_from_start_to_goal(self) -> None:
        """BFS from start must reach goal."""
        levels = load_levels()
        for level in levels:
            visited = set()
            queue = deque([level.start_node])
            visited.add(level.start_node)
            while queue:
                node = queue.popleft()
                for nbr in level.neighbors(node):
                    if nbr not in visited:
                        visited.add(nbr)
                        queue.append(nbr)
            self.assertIn(level.goal_node, visited,
                          f"Level {level.level_id}: goal {level.goal_node} unreachable from start {level.start_node}")
            for mine in level.mines:
                self.assertIn(mine, visited, f"Level {level.level_id}: mine {mine} unreachable")
            for village in level.villages:
                self.assertIn(village, visited, f"Level {level.level_id}: village {village} unreachable")

    def test_key_nodes_have_neighbors(self) -> None:
        """Start, goal, mines, villages must have at least one neighbor."""
        levels = load_levels()
        for level in levels:
            for node in [level.start_node, level.goal_node] + list(level.mines) + list(level.villages):
                self.assertGreater(len(level.neighbors(node)), 0,
                                   f"Level {level.level_id}: node {node} has no neighbors")

    def test_level2_hex_grid_structure(self) -> None:
        """Level 2 (8x8 hex grid): interior nodes should have 5-6 neighbors."""
        levels = load_levels()
        l2 = levels[1]
        # Node 10 (row 1, col 1) should have 6 neighbors in a hex grid
        nbrs_10 = l2.neighbors(10)
        self.assertGreaterEqual(len(nbrs_10), 5, "Interior hex node should have >= 5 neighbors")


class SolverTests(unittest.TestCase):
    def test_tiny_solver_finds_route(self) -> None:
        level = tiny_level()
        trace = solve_deterministic_level(level, purchase_step=1)
        self.assertTrue(trace.feasible, trace.message)
        self.assertEqual(trace.final_state().node, 3)
        self.assertEqual(trace.final_state().day, 2)
        self.assertEqual(validate_trace(level, trace), [])

    def test_tiny_solver_blocks_illegal_storm_move(self) -> None:
        level = tiny_level()
        storm_level = LevelConfig(
            **{
                **level.__dict__,
                "weather": ("沙暴", "沙暴"),
            }
        )
        trace = solve_deterministic_level(storm_level, purchase_step=1)
        self.assertFalse(trace.feasible)

    def test_no_storm_scenario_feasible(self) -> None:
        """Level 3 has no storms; should always be feasible."""
        levels = load_levels()
        l3 = levels[2]
        weather = tuple(["晴朗"] * 10)
        trace = solve_deterministic_level(l3, weather_sequence=weather, ignore_review=True,
                                          max_states_per_bucket=200, max_purchase_options=100, purchase_step=5)
        self.assertTrue(trace.feasible, f"No-storm scenario should be feasible: {trace.message}")

    def test_extreme_storm_scenario(self) -> None:
        """Level 4 with many storms should still find a feasible solution."""
        levels = load_levels()
        l4 = levels[3]
        weather = ["晴朗"] * 30
        weather[5] = "沙暴"
        weather[15] = "沙暴"
        weather[25] = "沙暴"
        trace = solve_deterministic_level(l4, weather_sequence=tuple(weather), ignore_review=True,
                                          max_states_per_bucket=200, max_purchase_options=100, purchase_step=25)
        self.assertTrue(trace.feasible, f"3-storm scenario should be feasible: {trace.message}")

    def test_resource_non_negative_throughout_trace(self) -> None:
        """Water and food must never go negative in a feasible trace."""
        level = tiny_level()
        trace = solve_deterministic_level(level, purchase_step=1)
        self.assertTrue(trace.feasible)
        for step in trace.steps:
            self.assertGreaterEqual(step.state.water, 0)
            self.assertGreaterEqual(step.state.food, 0)

    def test_cash_non_negative_throughout_trace(self) -> None:
        """Cash must never go negative in a feasible trace."""
        level = tiny_level()
        trace = solve_deterministic_level(level, purchase_step=1)
        self.assertTrue(trace.feasible)
        for step in trace.steps:
            self.assertGreaterEqual(step.state.cash, 0)

    def test_carry_limit_enforced(self) -> None:
        """Weight must never exceed carry limit in a feasible trace."""
        level = tiny_level()
        trace = solve_deterministic_level(level, purchase_step=1)
        self.assertTrue(trace.feasible)
        for step in trace.steps:
            wt = carried_weight(level, step.state.water, step.state.food)
            self.assertLessEqual(wt, level.carry_limit_kg)

    def test_no_move_on_storm_day(self) -> None:
        """No move actions should occur on storm days."""
        level = tiny_level()
        storm_level = LevelConfig(**{**level.__dict__, "weather": (WEATHER_SUNNY, WEATHER_STORM)})
        # Give enough resources to survive 2 days
        trace = solve_deterministic_level(storm_level, purchase_step=1)
        if trace.feasible:
            for step in trace.steps:
                if step.action and step.action.kind == "move":
                    day_idx = step.state.day - 1
                    if 0 <= day_idx < len(storm_level.weather):
                        self.assertNotEqual(storm_level.weather[day_idx], "沙暴")

    def test_no_mining_on_arrival_day(self) -> None:
        """Mining should not happen on the day of arriving at a mine."""
        level = tiny_level()
        # Create a level with a mine
        mine_level = LevelConfig(
            **{**level.__dict__, "mines": (2,), "deadline": 3,
               "weather": (WEATHER_SUNNY, WEATHER_SUNNY, WEATHER_SUNNY),
               "base_income": 10}
        )
        trace = solve_deterministic_level(mine_level, purchase_step=1)
        if trace.feasible:
            for i, step in enumerate(trace.steps):
                if step.action and step.action.kind == "mine":
                    if i > 0:
                        prev = trace.steps[i-1]
                        # Mining should only happen if already at the mine
                        self.assertEqual(prev.state.node, step.state.node)

    def test_village_purchase_price_correct(self) -> None:
        """Village purchase price should be 2x base price."""
        levels = load_levels()
        level = levels[0]
        self.assertEqual(level.rules.village_price_multiplier, 2.0)
        # Verify resource_cost uses the multiplier
        cost_1_water = resource_cost(level, 1, 0, level.rules.village_price_multiplier)
        self.assertEqual(cost_1_water, 5 * 2)  # 5元 * 2倍 = 10元

    def test_terminal_refund_correct(self) -> None:
        """Terminal refund should be 0.5x base price."""
        levels = load_levels()
        level = levels[0]
        self.assertEqual(level.rules.refund_multiplier, 0.5)
        refund = terminal_value(level, PlayerState(30, 27, 10000, 10, 5, True))
        expected = 10000 + 10 * 5 * 0.5 + 5 * 10 * 0.5  # cash + water refund + food refund
        self.assertEqual(refund, expected)

    def test_stay_consumption_multiplier(self) -> None:
        """Stay consumption should use base multiplier (1x)."""
        levels = load_levels()
        level = levels[0]
        water, food = daily_consumption(level, "晴朗", level.rules.stay_multiplier)
        self.assertEqual(water, 5)  # base consumption for 晴朗
        self.assertEqual(food, 7)

    def test_move_consumption_multiplier(self) -> None:
        """Move consumption should use 2x multiplier."""
        levels = load_levels()
        level = levels[0]
        water, food = daily_consumption(level, "晴朗", level.rules.move_multiplier)
        self.assertEqual(water, 10)  # 5 * 2
        self.assertEqual(food, 14)   # 7 * 2

    def test_mine_consumption_multiplier(self) -> None:
        """Mine consumption should use 3x multiplier."""
        levels = load_levels()
        level = levels[0]
        water, food = daily_consumption(level, "晴朗", level.rules.mine_multiplier)
        self.assertEqual(water, 15)  # 5 * 3
        self.assertEqual(food, 21)   # 7 * 3


class MultiplayerTests(unittest.TestCase):
    def test_multiplayer_summary_ready_with_formulas(self) -> None:
        levels = load_levels()
        summary = multiplayer_strategy_summary(levels[4])
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["issues"], [])
        table = summary["effect_table"]
        self.assertEqual(len(table), levels[4].players)
        self.assertEqual(table[0]["move_multiplier"], 2.0)
        self.assertEqual(table[1]["move_multiplier"], 4.0)
        self.assertEqual(table[0]["income_multiplier"], 1.0)
        self.assertAlmostEqual(table[1]["income_multiplier"], 0.5)

    def test_multiplayer_level6_ready(self) -> None:
        levels = load_levels()
        summary = multiplayer_strategy_summary(levels[5])
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["issues"], [])
        table = summary["effect_table"]
        self.assertEqual(len(table), levels[5].players)
        self.assertEqual(table[-1]["same_group_count"], levels[5].players)

    def test_multiplayer_move_formula_2k(self) -> None:
        """Move multiplier should be 2k for k players."""
        levels = load_levels()
        level = levels[4]  # Level 5, n=2
        table = compute_effect_table(level)
        self.assertEqual(table[0].move_multiplier, 2.0)   # k=1: 2*1
        self.assertEqual(table[1].move_multiplier, 4.0)   # k=2: 2*2

    def test_multiplayer_mine_formula(self) -> None:
        """Mine multiplier should stay at 3x base consumption for any k."""
        levels = load_levels()
        level = levels[4]
        table = compute_effect_table(level)
        self.assertEqual(table[0].mine_multiplier, 3.0)
        self.assertEqual(table[1].mine_multiplier, 3.0)

    def test_multiplayer_income_formula(self) -> None:
        """Income should be 1/k for k players."""
        levels = load_levels()
        level = levels[5]  # Level 6, n=3
        table = compute_effect_table(level)
        self.assertEqual(table[0].income_multiplier, 1.0)        # k=1: 1/1
        self.assertAlmostEqual(table[1].income_multiplier, 0.5)   # k=2: 1/2
        self.assertAlmostEqual(table[2].income_multiplier, 1/3)   # k=3: 1/3

    def test_multiplayer_village_price_formula(self) -> None:
        """Village price should be 4x base for any k."""
        levels = load_levels()
        level = levels[4]
        table = compute_effect_table(level)
        for row in table:
            self.assertEqual(row.village_price_multiplier, 4.0)


if __name__ == "__main__":
    unittest.main()
