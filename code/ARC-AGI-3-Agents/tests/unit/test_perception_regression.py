"""P1-4: Perception regression fixtures.

Verifies that perception changes don't break core invariants:
- Object detection count is stable
- Persistent IDs survive across frames
- Role scores are non-empty for interactive scenes
- Relation graph uses stable IDs
"""

import pytest

from agents.agentic.perception import (
    GoalSurface,
    PersistentObjectTracker,
    PerceivedObject,
    RelationGraphBuilder,
    RoleScorer,
    SceneCanonicalize,
    SpatialRelation,
    run_perception,
)


# ===================================================================
# Shared fixtures
# ===================================================================

def _make_grid_pair():
    """Two 10x10 frames: frame1 has 4 objects, frame2 has object A moved + D new."""
    grid1 = [[0] * 10 for _ in range(10)]
    # Object A: value 1, L-shape
    grid1[1][1] = 1; grid1[2][1] = 1; grid1[2][2] = 1
    # Object B: value 2, 2x2 block
    grid1[4][4] = 2; grid1[4][5] = 2; grid1[5][4] = 2; grid1[5][5] = 2
    # Object C: value 6, single cell
    grid1[3][8] = 6
    # Border box: value 5
    for c in range(6, 10):
        grid1[6][c] = 5; grid1[9][c] = 5
    for r in range(6, 10):
        grid1[r][6] = 5; grid1[r][9] = 5

    grid2 = [[0] * 10 for _ in range(10)]
    # Object A moved down by 2
    grid2[3][1] = 1; grid2[4][1] = 1; grid2[4][2] = 1
    # Object B unchanged
    grid2[4][4] = 2; grid2[4][5] = 2; grid2[5][4] = 2; grid2[5][5] = 2
    # Object C gone
    # Border box same
    for c in range(6, 10):
        grid2[6][c] = 5; grid2[9][c] = 5
    for r in range(6, 10):
        grid2[r][6] = 5; grid2[r][9] = 5
    # New object D
    grid2[0][0] = 9

    return grid1, grid2


# ===================================================================
# P1-4 Tests
# ===================================================================

class TestSceneCanonicalize:
    def test_min_object_count(self):
        grid, _ = _make_grid_pair()
        scene = SceneCanonicalize()
        bg, objs = scene.run(grid)
        assert 0 in bg, "value 0 should be background"
        assert len(objs) >= 3, "should detect at least 3 foreground objects"

    def test_background_threshold(self):
        grid, _ = _make_grid_pair()
        scene = SceneCanonicalize(bg_threshold=0.5)
        bg, objs = scene.run(grid)
        assert 0 in bg
        # With higher threshold, fewer values are background
        assert len(objs) >= 3

    def test_empty_grid(self):
        scene = SceneCanonicalize()
        bg, objs = scene.run([])
        assert len(bg) == 0
        assert len(objs) == 0

    def test_uniform_grid(self):
        grid = [[5] * 8 for _ in range(8)]
        scene = SceneCanonicalize()
        bg, objs = scene.run(grid)
        assert 5 in bg
        assert len(objs) == 0


class TestPersistentObjectTracker:
    def test_ids_assigned_to_all(self):
        grid, _ = _make_grid_pair()
        scene = SceneCanonicalize()
        _, objs = scene.run(grid)
        pot = PersistentObjectTracker()
        pot.update(objs)
        for obj in objs:
            assert obj.persistent_id is not None
            assert obj.persistent_id.startswith("P_")

    def test_id_stability_across_frames(self):
        grid1, grid2 = _make_grid_pair()
        scene = SceneCanonicalize()
        pot = PersistentObjectTracker()

        _, objs1 = scene.run(grid1)
        pot.update(objs1)
        pids_by_val = {o.value: o.persistent_id for o in objs1}

        _, objs2 = scene.run(grid2)
        pot.update(objs2)

        # Object B (val 2) didn't move → same pid
        val2 = [o for o in objs2 if o.value == 2]
        assert val2 and val2[0].persistent_id == pids_by_val[2]

        # Object A (val 1) moved → should still match
        val1 = [o for o in objs2 if o.value == 1]
        assert val1 and val1[0].persistent_id == pids_by_val[1]

        # Object D (val 9) is new → new pid
        val9 = [o for o in objs2 if o.value == 9]
        assert val9 and val9[0].persistent_id not in pids_by_val.values()

    def test_reset_clears_state(self):
        grid, _ = _make_grid_pair()
        scene = SceneCanonicalize()
        pot = PersistentObjectTracker()
        _, objs = scene.run(grid)
        pot.update(objs)
        assert len(pot._active) > 0
        pot.reset()
        assert len(pot._active) == 0
        assert len(pot._disappeared) == 0

    def test_disappeared_memory(self):
        """Disappeared objects should be remembered for MEMORY_STEPS."""
        grid1, grid2 = _make_grid_pair()
        scene = SceneCanonicalize()
        pot = PersistentObjectTracker()
        _, objs1 = scene.run(grid1)
        pot.update(objs1)

        # Object C (val 6) exists in grid1
        val6_pid = [o for o in objs1 if o.value == 6][0].persistent_id

        # grid2 has no val 6 → it disappears
        _, objs2 = scene.run(grid2)
        pot.update(objs2)
        assert val6_pid in pot._disappeared


class TestRoleScorer:
    def test_controllable_after_action(self):
        grid1, grid2 = _make_grid_pair()
        scene = SceneCanonicalize()
        pot = PersistentObjectTracker()
        rs = RoleScorer()

        _, objs1 = scene.run(grid1)
        pot.update(objs1)
        _, objs2 = scene.run(grid2)
        pot.update(objs2)

        rs.record_action("ACTION1", objs1, objs2, cells_changed=6, step_index=1)
        rels = RelationGraphBuilder().run(objs2)
        rs.score(objs2, grid2, rels, [])

        # Object A moved → should have controllable > 0
        val1 = [o for o in objs2 if o.value == 1][0]
        assert val1.controllable_score > 0

    def test_goal_score_for_boundary_object(self):
        grid1, _ = _make_grid_pair()
        scene = SceneCanonicalize()
        pot = PersistentObjectTracker()
        rs = RoleScorer()

        _, objs = scene.run(grid1)
        pot.update(objs)
        rels = RelationGraphBuilder().run(objs)
        gs = [GoalSurface(kind="reference_box", row_min=6, row_max=9, col_min=6, col_max=9)]
        rs.score(objs, grid1, rels, gs)

        # Border box (val 5) is at boundary + inside reference box → goal > 0
        val5 = [o for o in objs if o.value == 5][0]
        assert val5.goal_score > 0

    def test_scores_in_object_summary(self):
        grid1, grid2 = _make_grid_pair()
        scene = SceneCanonicalize()
        pot = PersistentObjectTracker()
        rs = RoleScorer()

        _, objs1 = scene.run(grid1)
        pot.update(objs1)
        _, objs2 = scene.run(grid2)
        pot.update(objs2)
        rs.record_action("ACTION1", objs1, objs2, cells_changed=6, step_index=1)
        rs.score(objs2, grid2, RelationGraphBuilder().run(objs2), [])

        for obj in objs2:
            summary = obj.to_object_summary()
            assert summary.persistent_id is not None
            assert hasattr(summary, "controllable_score")
            assert hasattr(summary, "goal_score")

    def test_reset_clears_evidence(self):
        rs = RoleScorer()
        rs._ctrl_evidence["P_1"] = 0.9
        rs.reset()
        assert len(rs._ctrl_evidence) == 0


class TestRelationGraphStableIds:
    """P1-3: Relation graph should use persistent_id when available."""

    def test_uses_persistent_id(self):
        grid, _ = _make_grid_pair()
        scene = SceneCanonicalize()
        pot = PersistentObjectTracker()
        _, objs = scene.run(grid)
        pot.update(objs)

        rels = RelationGraphBuilder().run(objs)
        assert len(rels) > 0
        for a_id, _, b_id in rels:
            assert a_id.startswith("P_"), f"relation should use persistent_id, got {a_id}"
            assert b_id.startswith("P_"), f"relation should use persistent_id, got {b_id}"

    def test_without_persistent_id_falls_back(self):
        """Objects without persistent_id should still produce relations."""
        grid, _ = _make_grid_pair()
        scene = SceneCanonicalize()
        _, objs = scene.run(grid)
        # Don't run tracker → no persistent_id
        rels = RelationGraphBuilder().run(objs)
        assert len(rels) > 0
        for a_id, _, b_id in rels:
            assert a_id.startswith("obj_")


class TestRunPerceptionPipeline:
    def test_full_pipeline_returns_all_keys(self):
        grid, _ = _make_grid_pair()
        result = run_perception(grid=grid)
        assert "objects" in result
        assert "transitions" in result
        assert "relations" in result
        assert "affordances" in result
        assert "goal_surfaces" in result
        assert "object_summaries" in result
        assert len(result["objects"]) > 0
        assert len(result["object_summaries"]) == len(result["objects"])

    def test_pipeline_with_trackers(self):
        grid1, grid2 = _make_grid_pair()
        pot = PersistentObjectTracker()
        rs = RoleScorer()

        r1 = run_perception(grid=grid1, persistent_tracker=pot, role_scorer=rs)
        assert all(o.persistent_id is not None for o in r1["objects"])

        r2 = run_perception(
            grid=grid2, prev_grid=grid1, prev_objects=r1["objects"],
            persistent_tracker=pot, role_scorer=rs, last_action="ACTION1",
        )
        assert all(o.persistent_id is not None for o in r2["objects"])
        assert all(s.persistent_id is not None for s in r2["object_summaries"])
