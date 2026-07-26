"""Measure how much of a model is rules and how much is special cases.

The published ablation runs a scheduled simplification pass: at intervals the
agent is asked to remove distinctions not forced by evidence, replace case-by-case
behaviour with shared parameterised rules, and separate genuinely level-specific
DATA from common mechanics. It helped in three of four settings.

We cannot prompt ourselves into simplicity, but we can measure the pressure. This
reports, per model, the things that make a model less general — and every one of
these is a real entry in ours, not a hypothetical:

  magic coordinates     a literal (row, col) baked into the rules, which by
                        definition cannot transfer to another level
  per-level branches    behaviour keyed on a level index
  ignore masks          cells excluded from verification instead of predicted
  missing renderer      dynamics without a frame, so nothing can be checked
                        cell-for-cell
  flagged rules         the ones the model's own docstring marks UNDER-DETERMINED
  legacy switches       retired rules still carried, which is debt of a healthy
                        kind: it is what lets a refuted version be re-run

Usage: model_debt.py [--game tu93]
"""
import re
from pathlib import Path

import _cli
from agents.wm.models import MODELS, meta_for, short_id

# A coordinate TABLE looks like a tuple inside a container: frozenset({(44, 51)}),
# [(19, 42), (57, 27)]. A bare pair bound to a name is usually a pair of VALUES
# (TERRITORY = (11, 12)), and a small pair is an offset, not a board position.
COORD = re.compile(r"[\{\[]\s*\((\d{1,2}),\s*(\d{1,2})\)")

TRIPLE_D = chr(34) * 3
TRIPLE_S = chr(39) * 3


def strip_docstrings(text):
    """Blank out docstring bodies before looking for hardcoded coordinates.

    Evidence narrated in prose - "the guard at (42,30)" - is not a hardcoded
    coordinate. Counting it as one made this tool report the exact opposite of
    the truth on its first run: it scored the models as getting worse at the
    moment the only real magic coordinate was removed from them.
    """
    out, in_doc, delim = [], False, None
    for ln in text.splitlines():
        if not in_doc:
            opener = None
            for d in (TRIPLE_D, TRIPLE_S):
                if d in ln:
                    opener = d
                    break
            if opener is None:
                out.append(ln)
                continue
            if ln.count(opener) >= 2:      # opens and closes on one line
                out.append("")
                continue
            in_doc, delim = True, opener
            out.append("")
        else:
            if delim in ln:
                in_doc = False
            out.append("")
    return out


def scan(path: Path):
    text = path.read_text()
    raw = text.splitlines()
    lines = strip_docstrings(text)
    body = [ln for ln in lines if not ln.strip().startswith("#")]
    out = {"lines": len(raw), "magic": [], "level_branches": [], "ignore": 0,
           "renders": True, "flagged": [], "legacy": []}
    for i, ln in enumerate(lines, 1):
        stripped = ln.strip()
        if stripped.startswith("#") or '"""' in stripped:
            continue
        for m in COORD.finditer(ln):
            # An OFFSET table (notch positions, direction deltas) has small
            # components; an absolute BOARD coordinate does not. Only the second
            # kind is debt — it cannot transfer to another level by construction.
            r, c = int(m.group(1)), int(m.group(2))
            if r >= 6 or c >= 6:
                out["magic"].append((i, stripped[:78]))
                break
        if re.search(r"level\s*==\s*\d|LEVEL\s*==\s*\d|\blevel\b.*\bin\b\s*\(", ln):
            out["level_branches"].append((i, stripped[:78]))
    out["ignore"] = text.count("def ignore(")
    out["renders"] = "NotImplementedError" not in text or "def render" not in text
    if "def render" in text and "NotImplementedError" in text:
        out["renders"] = False
    out["flagged"] = [ln.strip().lstrip("# ") for ln in raw
                      if "UNDER-DETERMINED" in ln or "UNDERIVED" in ln]
    out["legacy"] = re.findall(r'"([a-z_]+)"', 
                               re.search(r"LEGACY_SWITCHES\s*=\s*\(([^)]*)\)", text).group(1)
                               ) if "LEGACY_SWITCHES" in text else []
    return out


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--all-games", action="store_true")
    a = p.parse_args()
    games = sorted(MODELS) if (a.all_games or a.game == "tu93") else [short_id(a.game)]
    if not a.all_games:
        games = [short_id(a.game)]
    worst = []
    for g in games:
        src = Path(meta_for(g).get("source", ""))
        if not src.exists():
            continue
        d = scan(src)
        print(f"\n=== {g}  ({d['lines']} lines)")
        print(f"  renders frames         : {'yes' if d['renders'] else 'NO — cannot be frame-checked'}")
        print(f"  ignore masks           : {d['ignore']}")
        print(f"  per-level branches     : {len(d['level_branches'])}")
        for i, ln in d["level_branches"][:3]:
            print(f"      line {i}: {ln}")
        print(f"  magic coordinates      : {len(d['magic'])}")
        for i, ln in d["magic"]:
            print(f"      line {i}: {ln}")
        print(f"  rules flagged unsure   : {len(d['flagged'])}")
        for f in d["flagged"][:2]:
            print(f"      {f[:90]}")
        print(f"  retired rules kept     : {d['legacy'] or 'none'}")
        score = (len(d["magic"]) * 3 + len(d["level_branches"]) * 2
                 + d["ignore"] + len(d["flagged"]) + (0 if d["renders"] else 3))
        worst.append((score, g))
        print(f"  debt score             : {score}  (magic x3, branches x2, "
              f"masks, flags, no-renderer x3)")
    if len(worst) > 1:
        worst.sort(reverse=True)
        print(f"\nmost debt first: " + ", ".join(f"{g} ({s})" for s, g in worst))


if __name__ == "__main__":
    main()
