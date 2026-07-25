"""SolveLoop — the outer control loop.

    observe -> deliberate (theorize -> certify -> plan) -> execute -> record

Enforced invariants (the three Schema constraints, made concrete):
  1. The world model is an executable program the brain authors each round.
  2. It is certified against the FULL recorded history before it is trusted to
     plan (`run_backtest` must be green).
  3. Reality outranks the model: a single mispredicted transition during
     execution voids the current plan and forces re-deliberation.

Only real `env.step` calls cost actions; backtest and BFS are free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .backtest import BacktestReport, reconstruct_current_state, run_backtest
from .brain import Brain
from .core import (
    Action,
    Status,
    Timeline,
    Transition,
    WorldModel,
    diff_cells,
    frames_equal,
    ignored_cells,
)
from .env import Environment
from .planner import Plan, run_bfs
from .trace import ReasoningChain, TraceRecord, TraceWriter, sparse_frame


@dataclass
class _ActivePlan:
    model: WorldModel
    actions: list[Action]
    cursor: int = 0
    pred_state: object = None  # model state just before the next planned action


@dataclass
class EpisodeResult:
    status: str
    steps: int
    levels_completed: int
    solved: bool
    mispredictions: int
    final_backtest: Optional[str]
    trace_path: Optional[str]
    trace_records: list[dict] = field(default_factory=list)


class SolveLoop:
    def __init__(self, *, max_steps: int = 200):
        self.max_steps = max_steps

    def run(
        self,
        env: Environment,
        brain: Brain,
        *,
        trace_path: Optional[str] = None,
    ) -> EpisodeResult:
        actions = [Action(a) for a in env.available_actions]
        frame = env.reset()
        timeline = Timeline(frame)
        writer = TraceWriter(trace_path)

        prev_model: Optional[WorldModel] = None
        last_report: Optional[BacktestReport] = None
        active: Optional[_ActivePlan] = None
        mispredictions = 0
        levels = 0
        steps = 0

        while steps < self.max_steps:
            phase = "instrumental"
            reasoning = ReasoningChain()
            strategy_change = None

            # ---- DELIBERATE (only when we have no live certified plan) ----
            if active is None:
                model = brain.propose(timeline, prev_model, last_report)
                report = run_backtest(model, timeline)
                prev_model, last_report = model, report
                reasoning.observe = _observe_text(timeline)
                reasoning.hypothesize = model.notes or "world model proposed"
                reasoning.result = report.summary()

                if report.ok:
                    cur = reconstruct_current_state(model, timeline)
                    plan = run_bfs(model, cur, actions)
                    reasoning.revise = plan.summary()
                    if plan.found and plan.actions:
                        active = _ActivePlan(model=model, actions=plan.actions,
                                             pred_state=cur)
                        phase = "instrumental"
                    elif plan.found and not plan.actions:
                        # already at goal per model — nothing to do
                        phase = "instrumental"
                    else:
                        phase = "epistemic"  # certified but goal not yet reachable
                else:
                    phase = "recovery" if last_report and last_report.first_mismatch \
                        else "epistemic"
                    strategy_change = {
                        "reason": "world model failed certification",
                        "counterexample": report.summary(),
                    }

            # ---- CHOOSE the next real action ----
            if active is not None:
                action = active.actions[active.cursor]
                predicted_state, predicted_status = active.model.step(
                    active.pred_state, action)
                predicted_frame = active.model.render(predicted_state)
                confidence = active.model.confidence
                pred_model = active.model
            else:
                action = _explore(timeline, actions)
                predicted_state = predicted_status = predicted_frame = None
                confidence = 0.0
                pred_model = None

            reasoning.predict = (
                f"{action} -> {predicted_status}" if predicted_status
                else f"{action} (exploratory probe, no certified prediction)"
            )

            # ---- EXECUTE (the only real cost) ----
            result = env.step(action)
            steps += 1
            transition = Transition(
                step_index=steps,
                action=action,
                before_frame=timeline.current_frame,
                after_frame=result.frame,
                status=result.status,
                changed_cells=result.changed_cells,
            )
            timeline.record(transition)

            # ---- reality outranks the model ----
            prediction_match: Optional[bool] = None
            surprise = "none"
            if predicted_frame is not None:
                ignore = ignored_cells(pred_model, result.frame)
                frame_ok = frames_equal(predicted_frame, result.frame, ignore)
                status_ok = predicted_status == result.status
                prediction_match = frame_ok and status_ok
                if not prediction_match:
                    mispredictions += 1
                    surprise = (
                        f"misprediction: predicted {predicted_status}/"
                        f"{diff_cells(predicted_frame, result.frame, ignore)}-cell-off"
                    )
                    active = None  # void the plan; re-deliberate next round
                else:
                    active.pred_state = predicted_state
                    active.cursor += 1
                    if active.cursor >= len(active.actions):
                        active = None  # plan consumed

            reasoning.result = (reasoning.result + " | " if reasoning.result else "") + \
                f"executed {action}: {result.status}, {result.changed_cells} cells"

            # ---- RECORD trace ----
            writer.write(TraceRecord(
                step_index=steps,
                phase=phase,
                action=action.to_dict(),
                predicted_status=predicted_status,
                confidence=confidence,
                actual_status=result.status,
                actual_changed_cells=result.changed_cells,
                prediction_match=prediction_match,
                surprise=surprise,
                world_model_version=prev_model.version if prev_model else 0,
                world_model_confidence=prev_model.confidence if prev_model else 0.0,
                backtest=last_report.summary() if last_report else "",
                backtest_ok=bool(last_report and last_report.ok),
                plan=(f"{len(active.actions)} actions, "
                      f"cursor {active.cursor}") if active else "none",
                reasoning=reasoning,
                strategy_change=strategy_change,
            ))

            # ---- handle terminal status ----
            if result.status == Status.LEVEL_COMPLETED:
                levels += 1
                return EpisodeResult(
                    status=Status.LEVEL_COMPLETED, steps=steps,
                    levels_completed=levels, solved=True,
                    mispredictions=mispredictions,
                    final_backtest=last_report.summary() if last_report else None,
                    trace_path=trace_path, trace_records=writer.records,
                )
            if result.status == Status.GAME_OVER:
                # Skeleton: end the attempt but KEEP the recorded transition so
                # the counterexample survives (it is what refutes a wrong model).
                # TODO(multi-attempt): retain prior attempts as history and
                # RESET for a fresh attempt (Baseline1 backtests across all
                # recorded attempts) instead of returning here.
                return EpisodeResult(
                    status=Status.GAME_OVER, steps=steps,
                    levels_completed=levels, solved=False,
                    mispredictions=mispredictions,
                    final_backtest=last_report.summary() if last_report else None,
                    trace_path=trace_path, trace_records=writer.records,
                )

        return EpisodeResult(
            status=Status.RUNNING, steps=steps, levels_completed=levels,
            solved=False, mispredictions=mispredictions,
            final_backtest=last_report.summary() if last_report else None,
            trace_path=trace_path, trace_records=writer.records,
        )


# --------------------------------------------------------------------------- #
# trivial exploration policy (placeholder for the Experiment Designer)
# --------------------------------------------------------------------------- #


def _explore(timeline: Timeline, actions: list[Action]) -> Action:
    """Round-robin over actions, biased to the least-recently-tried.

    Deliberately dumb: the real experiment designer (max information gain /
    hypothesis discrimination) slots in here later.
    """
    tried = [tr.action.name for tr in timeline.transitions]
    for a in actions:
        if a.name not in tried:
            return a
    counts = {a.name: 0 for a in actions}
    for name in tried:
        counts[name] = counts.get(name, 0) + 1
    least = min(actions, key=lambda a: counts[a.name])
    return least


def _observe_text(timeline: Timeline) -> str:
    sf = sparse_frame(timeline.current_frame)
    return (f"{len(timeline)} recorded steps; current frame "
            f"{sf['rows']}x{sf['cols']}, bg={sf['background']}")
