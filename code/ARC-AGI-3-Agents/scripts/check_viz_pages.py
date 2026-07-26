"""Static checks for the visualization pages, because nobody here has a browser.

Written after a real rendering bug shipped: `paper.html` had `id="ledger"` on both
the section heading and the table below it, so `getElementById("ledger")` returned
the *heading*, the table rows were injected into an <h2>, and the browser dropped
every <tr>/<td> — the ledger came out as a wall of oversized text. Nothing in the
JSON, the JS syntax, or the HTTP status said a word about it.

So: check the things a page can get wrong without failing loudly.

  1. duplicate ids, and ids that shadow a getElementById target
  2. getElementById targets that do not exist at all
  3. an element fed table rows must actually be a <table>
  4. an element drawn on with getContext must actually be a <canvas>
  5. every fetch("./x") and href="./x" must resolve on disk
  6. every <script> block must parse (delegated to node --check when available)

Usage: check_viz_pages.py [dir]        default artifacts/wm_viz
Exits non-zero if anything fails, so it can sit in a regression run.
"""
import collections
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TAG_OPEN = re.compile(r"<(\w+)([^>]*)\bid=\"([^\"]+)\"")


def elements_by_id(text):
    """id -> tag name, in document order (first wins, like getElementById)."""
    out = {}
    for tag, _attrs, i in TAG_OPEN.findall(text):
        out.setdefault(i, tag.lower())
    return out


def check(path: Path):
    text = path.read_text()
    problems = []
    ids = re.findall(r'\bid="([^"]+)"', text)
    tags = elements_by_id(text)
    dupes = {i for i, n in collections.Counter(ids).items() if n > 1}
    targets = set(re.findall(r'getElementById\("([^"]+)"\)', text))

    for t in sorted(targets & dupes):
        problems.append(f"id \"{t}\" appears {ids.count(t)}x and is a getElementById "
                        f"target — the first one ({tags[t]}) wins, silently")
    # ids the page builds at runtime, e.g. id="mv-${version}" or "row-"+i
    dynamic = tuple(pre for pre in re.findall(r'id="([^"$]*)\$\{', text) if pre)
    for t in sorted(targets - set(tags)):
        if re.search(r'getElementById\("' + re.escape(t) + r'"\s*\+', text):
            continue
        if dynamic and t.startswith(dynamic):
            continue
        problems.append(f"getElementById(\"{t}\") has no element")

    # rows injected into a non-table, the bug that started this file
    for t, assigned in re.findall(
            r'getElementById\("([^"]+)"\)\.innerHTML\s*=\s*\n?\s*("(?:<tr|<tbody))', text):
        if tags.get(t) not in ("table", "tbody"):
            problems.append(f"table rows are injected into <{tags.get(t, '?')} id=\"{t}\"> "
                            f"— <tr> is invalid there and the browser will drop the markup")
    for t in re.findall(r'getElementById\("([^"]+)"\)[^\n]*getContext', text):
        if tags.get(t) != "canvas":
            problems.append(f"getContext called on <{tags.get(t, '?')} id=\"{t}\">")

    root = path.parent
    for ref in re.findall(r'fetch\("\./([^"`]+)"\)', text):
        if not (root / ref).exists():
            problems.append(f"fetch(\"./{ref}\") does not exist")
    for ref in re.findall(r'href="\./([^"#?]+)', text):
        if not (root / ref).exists():
            problems.append(f"href=\"./{ref}\" does not exist")

    for i, block in enumerate(re.findall(r"<script>(.*?)</script>", text, re.S)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(block)
            tmp = fh.name
        try:
            r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
            if r.returncode:
                problems.append(f"script block {i} does not parse: "
                                f"{r.stderr.strip().splitlines()[-1] if r.stderr else '?'}")
        except FileNotFoundError:
            pass                          # no node here; skip rather than pretend
        finally:
            Path(tmp).unlink(missing_ok=True)
    return problems


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/wm_viz")
    pages = sorted(root.glob("*.html"))
    if not pages:
        print(f"no pages under {root}")
        return 1
    bad = 0
    for p in pages:
        problems = check(p)
        bad += len(problems)
        print(f"{'FAIL' if problems else 'ok  '} {p.name}"
              + ("" if problems else "  (ids, targets, tables, canvases, links, scripts)"))
        for m in problems:
            print(f"       - {m}")
    print(f"\n{'all pages clean' if not bad else str(bad) + ' problem(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
