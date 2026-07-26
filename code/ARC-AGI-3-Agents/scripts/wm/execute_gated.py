"""Execute a plan one action at a time, checking the model's prediction first.

Until now a plan was run blind: the loop planned N actions inside a certified
model and then spent all N in the environment, learning only "cleared" or "no
clear" at the end. On m0r0 L1 that cost 20 actions to discover the model was
wrong at step 12; on sk48 L1 it cost 18 to learn nothing at all.

Gating turns each action into a checked experiment. Before acting, the model
predicts the next state; after acting, the prediction is compared with what came
back. The first mismatch stops execution and is reported as a pointed bug with
the replay key that reproduces it — the same currency `run_backtest` deals in,
except paid for one action at a time instead of a whole plan.

What can be checked depends on what the model offers:
  frame   a model with a renderer is checked cell for cell (minus its ignore mask)
  status  every model is checked on RUNNING / LEVEL_COMPLETED / GAME_OVER
A model with no renderer is therefore gated more weakly, and says so.

Usage: execute_gated.py --game m0r0 --level 1 "ACTION2,ACTION3,..."
       or import execute_gated() from another script.
"""
import _cli
from agents.wm.core import Action, Status, diff_cells, ignored_cells
from agents.wm.harness import Session, engine_steps
from agents.wm.journal import Journal
from agents.wm.models import model_for


def execute_gated(session, model, state, actions, *, journal=None, version="v0",
                  verbose=True):
    """Run `actions`, stopping at the first step the model gets wrong.

    Returns a dict: how far it got, why it stopped, and the pointed bug if any.
    """
    hud = ignored_cells(model, session.grid) or set()
    try:
        model.render(state)
        renders = True
    except NotImplementedError:
        renders = False
    lv0 = session.raw.levels_completed
    taken = []

    for i, name in enumerate(actions, start=1):
        at = list(session.actions)
        pred_state, pred_status = model.step(state, Action(name))
        pred_frame = model.render(pred_state) if renders else None

        session.act(name)
        taken.append(name)
        died = session.dead
        cleared = (not died) and session.raw.levels_completed > lv0
        real_status = (Status.GAME_OVER if died else
                       Status.LEVEL_COMPLETED if cleared else Status.RUNNING)

        off = None
        if pred_frame is not None and not died:
            off = diff_cells(pred_frame, session.grid, hud)

        bad_status = pred_status != real_status
        bad_frame = off is not None and off > 0 and not cleared
        if bad_status or bad_frame:
            bits = []
            if bad_status:
                bits.append(f"status predicted={pred_status} actual={real_status}")
            if bad_frame:
                bits.append(f"{off} cell(s) mispredicted")
            bug = (f"gated execution stopped at step {i} after {name}: "
                   + "; ".join(bits))
            if verbose:
                print(f"  ABORTED at step {i}/{len(actions)} — {'; '.join(bits)}")
                print(f"  {len(actions) - i} action(s) not spent")
            if journal:
                journal.refute(version=version, bug=bug, step_index=i, action=name,
                               cells_off=off or 0, at=at)
            return {"taken": taken, "aborted_at": i, "bug": bug, "cleared": False,
                    "died": died, "checked": "frame+status" if renders else "status",
                    "saved": len(actions) - i}
        state = pred_state
        if cleared:
            if verbose:
                print(f"  cleared at step {i}/{len(actions)}, every step predicted")
            return {"taken": taken, "aborted_at": None, "bug": None, "cleared": True,
                    "died": False, "checked": "frame+status" if renders else "status",
                    "saved": len(actions) - i}
        if died:
            return {"taken": taken, "aborted_at": i, "bug": None, "cleared": False,
                    "died": True, "checked": "frame+status" if renders else "status",
                    "saved": len(actions) - i}

    return {"taken": taken, "aborted_at": None, "bug": None, "cleared": False,
            "died": False, "checked": "frame+status" if renders else "status",
            "saved": 0}


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    _cli.actions_arg(p)
    p.add_argument("--version", default="v0")
    p.add_argument("--legacy", default="",
                   help="comma-separated legacy switches, to gate with a RETIRED "
                        "model version and see where it goes wrong")
    p.add_argument("--quiet-journal", action="store_true")
    a = p.parse_args()

    s = Session.open(a.game, a.level)
    legacy = [x for x in a.legacy.split(",") if x]
    model = model_for(a.game, version=0, legacy=legacy) if legacy \
        else model_for(a.game, version=0)
    state = model.reconstruct(s.grid)
    J = None if a.quiet_journal else Journal(a.game, a.level)
    acts = _cli.actions(a.actions)
    print(f"{a.game} L{a.level}: gating {len(acts)} action(s)")
    r = execute_gated(s, model, state, acts, journal=J, version=a.version)
    print(f"  result: {'CLEARED' if r['cleared'] else ('DIED' if r['died'] else 'ran out')}"
          f"; checked on {r['checked']}; {len(r['taken'])} action(s) spent, "
          f"{r['saved']} saved; {engine_steps()} engine steps")
    return 0 if r["cleared"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
