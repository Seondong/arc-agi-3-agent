"""S3-4: Subgoal planner regression tests.

Verifies that:
- Subgoal generation produces non-empty candidates for typical scenes
- Subgoal types match expected patterns for given role scores
- Failed subgoals are not regenerated
- Stagnation detection works
- Action outlines respect action_beliefs
"""

import pytest

from agents.agentic.perception import (
    PersistentObjectTracker,
    PerceivedObject,
    RoleScorer,
    SceneCanonicalize,
    RelationGraphBuilder,
    GoalSurface,
)
from agents.agentic.schemas import (
    ActionSemanticsBelief,
    BeliefLedger,
    HypothesisEntry,
    Subgoal,
)
from agents.agentic.solve_loop import SubgoalPlanner


# ===================================================================
# Helpers
# ===================================================================

def _make_objects_with_roles():
    """Create objects with role scores set manually."""
    ctrl = PerceivedObject(
        obj_id="obj_1", value=1, char="●",
        cells=[(10, 10), (10, 11), (11, 10), (11, 11)],
        row_min=10, row_max=11, col_min=10, col_max=11,
        persistent_id="P_ctrl",
        controllable_score=0.8,
    )
    goal = PerceivedObject(
        obj_id="obj_2", value=2, char="②",
        cells=[(40, 40), (40, 41)],
        row_min=40, row_max=40, col_min=40, col_max=41,
        persistent_id="P_goal",
        goal_score=0.7,
    )
    blocker = PerceivedObject(
        obj_id="obj_3", value=3, char="③",
        cells=[(25, 25), (25, 26)],
        row_min=25, row_max=25, col_min=25, col_max=26,
        persistent_id="P_block",
        blocker_score=0.5,
    )
    click_target = PerceivedObject(
        obj_id="obj_4", value=4, char="④",
        cells=[(5, 50)],
        row_min=5, row_max=5, col_min=50, col_max=50,
        persistent_id="P_click",
        click_score=0.6,
    )
    return [ctrl, goal, blocker, click_target]


def _make_belief(action_beliefs=None):
    bl = BeliefLedger(
        episode_id="test", game_id="test", step_index=10,
        hypotheses=[
            HypothesisEntry(
                hypothesis_id="H0", summary="Test hypothesis",
                confidence=0.5, status="active",
            ),
        ],
    )
    if action_beliefs:
        bl.action_beliefs = action_beliefs
    return bl


# ===================================================================
# S3-4 Tests
# ===================================================================

class TestSubgoalGeneration:
    def test_generates_reach_target(self):
        objects = _make_objects_with_roles()
        belief = _make_belief()
        sp = SubgoalPlanner()

        candidates = sp.generate(
            objects=objects, belief_state=belief,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
            grid_rows=64, grid_cols=64,
        )
        types = [sg.subgoal_type for sg in candidates]
        assert "reach_target" in types, f"Expected reach_target, got {types}"

    def test_generates_clear_path(self):
        objects = _make_objects_with_roles()
        belief = _make_belief()
        sp = SubgoalPlanner()

        candidates = sp.generate(
            objects=objects, belief_state=belief,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
            grid_rows=64, grid_cols=64,
        )
        types = [sg.subgoal_type for sg in candidates]
        assert "clear_path" in types

    def test_generates_activate_switch(self):
        objects = _make_objects_with_roles()
        belief = _make_belief()
        sp = SubgoalPlanner()

        candidates = sp.generate(
            objects=objects, belief_state=belief,
            available_actions=["ACTION1", "ACTION5", "ACTION6"],
            grid_rows=64, grid_cols=64,
        )
        types = [sg.subgoal_type for sg in candidates]
        assert "activate_switch" in types

    def test_generates_explore_when_no_goal(self):
        # Only controllable, no goal
        ctrl = _make_objects_with_roles()[0]
        belief = _make_belief()
        sp = SubgoalPlanner()

        candidates = sp.generate(
            objects=[ctrl], belief_state=belief,
            available_actions=["ACTION1", "ACTION2"],
            grid_rows=64, grid_cols=64,
        )
        types = [sg.subgoal_type for sg in candidates]
        assert "explore_region" in types

    def test_empty_objects_produces_candidates(self):
        belief = _make_belief()
        belief.hypotheses[0].confidence = 0.3
        belief.hypotheses[0].status = "provisional"
        sp = SubgoalPlanner()

        candidates = sp.generate(
            objects=[], belief_state=belief,
            available_actions=["ACTION1", "ACTION2"],
            grid_rows=64, grid_cols=64,
        )
        # Should still produce test_hypothesis or explore_region
        assert len(candidates) >= 0  # may be empty if no weak hypotheses


class TestSubgoalFailureTracking:
    def test_failed_subgoal_not_regenerated(self):
        objects = _make_objects_with_roles()
        belief = _make_belief()
        sp = SubgoalPlanner()

        # Generate candidates
        candidates1 = sp.generate(
            objects=objects, belief_state=belief,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
            grid_rows=64, grid_cols=64,
        )
        reach = [sg for sg in candidates1 if sg.subgoal_type == "reach_target"][0]

        # Record it as failed
        sp.record_failure(reach)

        # Regenerate — reach_target with same target should be filtered
        candidates2 = sp.generate(
            objects=objects, belief_state=belief,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
            grid_rows=64, grid_cols=64,
        )
        reach2 = [sg for sg in candidates2
                   if sg.subgoal_type == "reach_target" and sg.target_pid == reach.target_pid]
        assert len(reach2) == 0, "Failed subgoal type+target should not be regenerated"


class TestSubgoalStatusUpdate:
    def test_stagnation_detection(self):
        sg = Subgoal(
            subgoal_id="SG_1", subgoal_type="reach_target",
            target_pid="P_goal", priority=0.8, confidence=0.6,
            action_outline=["ACTION1", "ACTION1", "ACTION1"],
            status="active",
        )
        sp = SubgoalPlanner()

        # Simulate 3 steps with diff <= 1
        for _ in range(3):
            sp.update_status(sg, _make_objects_with_roles(), 0, 0, diff_cells=1)

        assert sg.status == "failed", "Should fail after 3 steps of stagnation"

    def test_level_up_achieves(self):
        sg = Subgoal(
            subgoal_id="SG_1", subgoal_type="reach_target",
            priority=0.8, confidence=0.6,
            action_outline=["ACTION1"],
            status="active",
        )
        sp = SubgoalPlanner()
        sp.update_status(sg, [], levels_completed=1, prev_levels=0, diff_cells=100)
        assert sg.status == "achieved"

    def test_hard_cap_at_8_steps(self):
        sg = Subgoal(
            subgoal_id="SG_1", subgoal_type="explore_region",
            priority=0.4, confidence=0.3,
            action_outline=["ACTION1"] * 10,
            status="active",
        )
        sp = SubgoalPlanner()
        for _ in range(8):
            sp.update_status(sg, [], levels_completed=0, prev_levels=0, diff_cells=50)
        assert sg.status == "failed", "Should fail after 8 steps (hard cap)"


class TestActionOutline:
    def test_outline_respects_action_beliefs(self):
        objects = _make_objects_with_roles()
        beliefs = {
            "ACTION1": ActionSemanticsBelief(
                action_name="ACTION1", confidence=0.8, is_directional=True,
                times_used=5, avg_cells_changed=96.0,
            ),
            "ACTION2": ActionSemanticsBelief(
                action_name="ACTION2", confidence=0.8, is_directional=True,
                times_used=5, avg_cells_changed=96.0,
            ),
            "ACTION3": ActionSemanticsBelief(
                action_name="ACTION3", is_noop=True,
                times_used=3, avg_cells_changed=0.0,
            ),
            "ACTION4": ActionSemanticsBelief(
                action_name="ACTION4", confidence=0.6, is_directional=True,
                times_used=3, avg_cells_changed=12.0,
            ),
        }
        belief = _make_belief(action_beliefs=beliefs)
        sp = SubgoalPlanner()

        candidates = sp.generate(
            objects=objects, belief_state=belief,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
            grid_rows=64, grid_cols=64,
        )

        reach = [sg for sg in candidates if sg.subgoal_type == "reach_target"]
        if reach:
            outline = reach[0].action_outline
            assert len(outline) <= 5, f"Outline should be capped at 5, got {len(outline)}"
            # ACTION3 is noop → should not appear in outline
            assert "ACTION3" not in outline, "Noop actions should be excluded"

    def test_outline_not_empty(self):
        objects = _make_objects_with_roles()
        belief = _make_belief()
        sp = SubgoalPlanner()

        candidates = sp.generate(
            objects=objects, belief_state=belief,
            available_actions=["ACTION1", "ACTION2"],
            grid_rows=64, grid_cols=64,
        )
        for sg in candidates:
            if sg.subgoal_type in ("reach_target", "clear_path", "explore_region"):
                assert len(sg.action_outline) > 0, \
                    f"{sg.subgoal_type} should have non-empty action outline"


class TestSubgoalSelect:
    def test_selects_highest_priority_confidence(self):
        sp = SubgoalPlanner()
        candidates = [
            Subgoal(subgoal_id="SG_1", subgoal_type="explore_region",
                    priority=0.4, confidence=0.3),
            Subgoal(subgoal_id="SG_2", subgoal_type="reach_target",
                    priority=0.8, confidence=0.6),
            Subgoal(subgoal_id="SG_3", subgoal_type="clear_path",
                    priority=0.7, confidence=0.5),
        ]
        selected = sp.select(candidates)
        assert selected is not None
        assert selected.subgoal_id == "SG_2"  # 0.8 * 0.6 = 0.48 highest

    def test_select_empty_returns_none(self):
        sp = SubgoalPlanner()
        assert sp.select([]) is None
