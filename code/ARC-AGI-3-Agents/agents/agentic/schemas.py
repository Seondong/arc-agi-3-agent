# [Mar 29] Created by SD with GPT-5.4.

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ObjectSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int
    char: str
    cell_count: int
    row_min: int
    row_max: int
    col_min: int
    col_max: int
    label: str | None = None
    # P1-1: Persistent identity across steps
    persistent_id: str | None = None
    # P1-2: Role candidate scores (0.0 to 1.0)
    controllable_score: float = 0.0
    goal_score: float = 0.0
    blocker_score: float = 0.0
    click_score: float = 0.0


class ObservationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: str
    step_index: int
    state: str
    levels_completed: int = 0
    grid_rows: int
    grid_cols: int
    available_actions: list[str] = Field(default_factory=list)
    diff_summary: str = "INITIAL"
    action_history: list[Any] = Field(default_factory=list)
    value_histogram: dict[str, int] = Field(default_factory=dict)
    objects: list[ObjectSummary] = Field(default_factory=list)
    compressed_grid: str | None = None
    map2d: str | None = None
    notes: list[str] = Field(default_factory=list)


class MotifBelief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class HypothesisEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    summary: str
    confidence: float = 0.0
    status: Literal["active", "provisional", "discarded", "confirmed"] = "provisional"
    predicted_observations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class GoalBelief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ActionSemanticsBelief(BaseModel):
    """B2-2: Structured action semantics with confidence tracking."""
    model_config = ConfigDict(extra="forbid")

    action_name: str
    # What we think this action does
    description: str = ""
    confidence: float = 0.1
    # Evidence: how many times used, consistent outcomes?
    times_used: int = 0
    avg_cells_changed: float = 0.0
    consistent_streak: int = 0  # consecutive times result matched expectation
    last_cells_changed: int = 0
    # Discovered properties
    is_noop: bool = False               # consistently 0 cells changed
    is_directional: bool = False        # consistently moves objects
    is_reversible_with: str | None = None  # e.g. ACTION1 <-> ACTION2
    affected_pids: list[str] = Field(default_factory=list)  # persistent IDs commonly affected


class DynamicsRule(BaseModel):
    """Executable rule: 'when condition, action produces effect.'

    This is the core unit of the world model that narratives describe as
    Python pseudocode.  Not game-specific — every game produces these.
    Examples:
      - "ACTION1 moves agent up by 1 cell when not blocked by wall"
      - "ACTION5 toggles the color of the cell under the agent"
      - "When energy reaches 0, GAME_OVER"
    """
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    action_name: str | None = None     # None for passive rules (e.g. gravity)
    condition: str = ""                # natural language or structured condition
    effect: str = ""                   # what happens
    confidence: float = 0.3
    times_verified: int = 0
    times_violated: int = 0
    discovered_at_step: int = 0


class InteractionRule(BaseModel):
    """Causal relationship between objects.

    Captures 'A does X to B' — push, block, trigger, connect, etc.
    Examples:
      - "agent pushes block when moving into it"
      - "switch activates door when clicked"
      - "rope connects block_A and block_B (move together)"
    """
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    trigger_pid: str                   # persistent ID of the cause object
    affected_pid: str                  # persistent ID of the affected object
    trigger_action: str = ""           # action or event that activates
    effect: str = ""                   # what happens to affected
    rule_type: Literal[
        "push", "block", "trigger", "connect", "destroy",
        "transform", "contain", "unknown",
    ] = "unknown"
    confidence: float = 0.3
    times_observed: int = 0
    discovered_at_step: int = 0


class Region(BaseModel):
    """Spatial region — higher-level than individual objects.

    Captures 'play area', 'reference zone', 'corridor', 'wall barrier'.
    Examples:
      - Region(name="play_area", role="traversable", bbox=(25,49,10,49))
      - Region(name="reference_box", role="goal_display", bbox=(8,16,28,36))
      - Region(name="corridor", role="connector", connected_to=["play_area","reference_box"])
    """
    model_config = ConfigDict(extra="forbid")

    region_id: str
    name: str = ""
    role: Literal[
        "play_area", "reference", "corridor", "barrier",
        "energy_display", "status_display", "unknown",
    ] = "unknown"
    row_min: int = 0
    row_max: int = 0
    col_min: int = 0
    col_max: int = 0
    dominant_value: int | None = None  # most common cell value in region
    traversable: bool = True
    connected_to: list[str] = Field(default_factory=list)  # other region_ids


class ReferencePatternSummary(BaseModel):
    """Canonical shared representation of a reference/goal surface's content.

    Separates spatial location (Region) from semantic content (this).
    A Region tells you WHERE the reference box is; this tells you
    WHAT'S INSIDE IT — the target pattern the agent must reproduce,
    match, or reach.

    Examples:
      - reference_box containing a 3x3 diamond of value 9
      - energy_bar showing 42/64 remaining
      - target_marker: single ◆ cell at boundary
    """
    model_config = ConfigDict(extra="forbid")

    surface_id: str
    kind: Literal["reference_box", "target_marker", "energy_bar", "unknown"] = "unknown"
    row_min: int = 0
    row_max: int = 0
    col_min: int = 0
    col_max: int = 0
    # Compact pattern rows: each string is one row of values.
    # Only for small patterns (≤8x8). E.g. ["5955", "5995", "5955"]
    pattern_rows: list[str] = Field(default_factory=list)
    # Human-readable description of the pattern structure.
    # E.g. "3x3 diamond of ◆(9) on ▓(5) background"
    pattern_description: str = ""
    # How confident we are this is a meaningful reference
    confidence: float = 0.5


class BeliefDiffSummary(BaseModel):
    """B2-3: Structured belief diff exported from the solve loop."""
    model_config = ConfigDict(extra="forbid")

    hypotheses_strengthened: int = 0
    hypotheses_weakened: int = 0
    hypotheses_discarded: int = 0
    hypotheses_suggested: int = 0
    motifs_updated: int = 0
    anchoring_alerts: int = 0
    max_confidence_delta: float = 0.0
    summary: str = ""


class Subgoal(BaseModel):
    """S3-1: Explicit intermediate objective for instrumental planning."""
    model_config = ConfigDict(extra="forbid")

    subgoal_id: str
    subgoal_type: Literal[
        "reach_target",       # move controllable to goal region
        "clear_path",         # remove or bypass blocker
        "activate_switch",    # interact with click/toggle target
        "align_objects",      # arrange objects into pattern
        "test_hypothesis",    # probe to confirm/deny a belief
        "explore_region",     # visit unvisited area
    ]
    target_pid: str | None = None     # persistent ID of target object
    target_region: tuple[int, int, int, int] | None = None  # (r0, r1, c0, c1)
    priority: float = 0.5            # 0..1
    confidence: float = 0.5          # how sure we are this is the right subgoal
    rationale: str = ""
    action_outline: list[str] = Field(default_factory=list)  # planned action sequence
    status: Literal["pending", "active", "achieved", "failed", "abandoned"] = "pending"
    steps_spent: int = 0


class BeliefLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    game_id: str
    step_index: int
    mode: Literal["epistemic", "instrumental", "recovery"] = "epistemic"
    top_motifs: list[MotifBelief] = Field(default_factory=list)
    hypotheses: list[HypothesisEntry] = Field(default_factory=list)
    goal_beliefs: list[GoalBelief] = Field(default_factory=list)
    action_semantics: dict[str, list[str]] = Field(default_factory=dict)
    # B2-2: Structured action semantics (replaces plain string list over time)
    action_beliefs: dict[str, ActionSemanticsBelief] = Field(default_factory=dict)
    # S3-1: Active subgoals for instrumental planning
    active_subgoals: list[Subgoal] = Field(default_factory=list)
    # Dynamics rules: executable world model ("action X does Y when Z")
    dynamics_rules: list[DynamicsRule] = Field(default_factory=list)
    # Interaction rules: causal object relationships ("A pushes B")
    interaction_rules: list[InteractionRule] = Field(default_factory=list)
    # Spatial regions: higher-level map structure
    regions: list[Region] = Field(default_factory=list)
    # Reference pattern summaries (goal surface content)
    reference_patterns: list[ReferencePatternSummary] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    game_id: str
    step_index: int
    mode: Literal["epistemic", "instrumental", "recovery"]
    chosen_action: Any
    rationale: str
    expected_outcome: str | None = None
    expected_information_gain: float | None = None
    next_probe_action: Any | None = None
    next_probe_rationale: str | None = None
    next_probe_expected_outcome: str | None = None
    next_probe_expected_information_gain: float | None = None
    belief_diff: BeliefDiffSummary | None = None
    belief_revision_summary: list[str] = Field(default_factory=list)
    suggested_hypotheses: list[str] = Field(default_factory=list)
    motif_updates: list[str] = Field(default_factory=list)
    anchoring_alerts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ===================================================================
# Simulator schemas — track simulator evolution for SFT data
# ===================================================================


class SimulatorSnapshot(BaseModel):
    """A frozen snapshot of a simulator version."""
    model_config = ConfigDict(extra="forbid")

    version: int
    step_created: int
    mechanic_count: int
    mechanics_summary: list[str] = Field(default_factory=list)
    avg_confidence: float = 0.0
    trigger: str = "initial"  # "initial" | "surprise_update" | "level_change"


class SimulatorEvolutionEntry(BaseModel):
    """Logged each time the simulator is modified."""
    model_config = ConfigDict(extra="forbid")

    step_index: int
    version_before: int
    version_after: int
    trigger: str  # what caused the update
    rules_added: list[str] = Field(default_factory=list)
    rules_modified: list[str] = Field(default_factory=list)
    rules_removed: list[str] = Field(default_factory=list)
    prediction_that_failed: str | None = None
    actual_observation: str | None = None
    confidence_changes: dict[str, list[float]] = Field(default_factory=dict)


class TrajectoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    game_id: str
    step_index: int
    state_summary: str
    motif_beliefs: dict[str, float] = Field(default_factory=dict)
    active_hypotheses: list[str] = Field(default_factory=list)
    action_taken: Any = None
    prediction: str | None = None
    actual_diff: str | None = None
    surprise: str | None = None
    surprise_magnitude: float | None = None
    confidence_update: dict[str, str] = Field(default_factory=dict)
    belief_diff: BeliefDiffSummary | None = None
    belief_revision_summary: list[str] = Field(default_factory=list)
    suggested_hypotheses: list[str] = Field(default_factory=list)
    motif_updates: list[str] = Field(default_factory=list)
    anchoring_alerts: list[str] = Field(default_factory=list)
    dynamics_rule_summary: list[str] = Field(default_factory=list)
    interaction_rule_summary: list[str] = Field(default_factory=list)
    region_summary: list[str] = Field(default_factory=list)
    reference_pattern_summary: str | None = None
    dynamics_revision: str | None = None
    active_hypothesis_count: int = 0
    discarded_hypothesis_count: int = 0
    hypothesis_pruning_count: int = 0
    belief_revision_score: float | None = None
    belief_revision_reasons: list[str] = Field(default_factory=list)
    actual_information_gain: float | None = None
    actual_information_gain_reasons: list[str] = Field(default_factory=list)
    planning_mode: Literal["epistemic", "instrumental", "recovery"] = "epistemic"
    llm_used: bool = False
    llm_model: str = ""
    # Simulator tracking fields
    simulator_version: int | None = None
    simulator_prediction: str | None = None
    simulator_correct: bool | None = None
    # 6-stage reasoning chain (data-logging-principles.md):
    # OBSERVE (facts) -> INTERPRET (meaning) -> HYPOTHESIZE (candidate explanations)
    # -> PREDICT (expected next outcome) -> RESULT (actual vs predicted)
    # -> REVISE (updates to rules / plan). All optional; solvers that do not
    # populate a stage leave it as None.
    observe_text: str | None = None
    interpret_text: str | None = None
    hypothesize_text: str | None = None
    predict_text: str | None = None
    result_text: str | None = None
    revise_text: str | None = None
    # Numeric prediction to enable automatic RESULT verification on next step.
    predicted_diff_cells: int | None = None
    predicted_diff_low: int | None = None
    predicted_diff_high: int | None = None
    prediction_hit: bool | None = None


class EpisodeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    game_id: str
    created_at: str
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
