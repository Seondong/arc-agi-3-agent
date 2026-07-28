"""Inject a real-data examples section into loop.ko.html.

Everything shown is pulled from artifacts/wm_dataset/ at build time, so the page
cannot drift from the corpus it describes.
"""
import glob
import html
import json
import pathlib
import re
from collections import Counter

ROOT = pathlib.Path("/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents")

# The same sixteen colours the level pages paint grids with, so a reader who has
# seen one page recognises the boards on this one.
PAL = ["#0d1117", "#0074D9", "#FF4136", "#2ECC40", "#FFDC00", "#9AA6B2",
       "#F012BE", "#FF851B", "#7FDBFF", "#B0344B", "#B10DC9", "#01FF70",
       "#FF69B4", "#85144b", "#39D3C9", "#DDDDDD"]


def svg_grid(frame, r0, r1, c0, c1, mark=None, cell=11, cls=""):
    """A window of the board as inline SVG.

    Inline because it must survive being served as a bare file from a CDN with
    no JavaScript and no fetch: the level pages build their canvases from JSON
    they load at runtime, which is fine there and would make this page blank
    anywhere else.
    """
    w, h = (c1 - c0 + 1) * cell, (r1 - r0 + 1) * cell
    out = [f'<svg class="grid {cls}" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
           f'role="img" shape-rendering="crispEdges">']
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            v = frame[r][c]
            out.append(f'<rect x="{(c - c0) * cell}" y="{(r - r0) * cell}" '
                       f'width="{cell}" height="{cell}" fill="{PAL[v % 16]}"/>')
    for (r, c) in (mark or []):
        if r0 <= r <= r1 and c0 <= c <= c1:
            out.append(f'<rect class="hit" x="{(c - c0) * cell + 0.5}" '
                       f'y="{(r - r0) * cell + 0.5}" width="{cell - 1}" '
                       f'height="{cell - 1}" fill="none" stroke="#fff" '
                       f'stroke-width="1.4"/>')
    out.append("</svg>")
    return "".join(out)


def bounds(frame, cells=None, pad=4, max_r=22, max_c=30):
    if cells:
        rs, cs = [c[0] for c in cells], [c[1] for c in cells]
        r0, r1 = max(0, min(rs) - pad), min(len(frame) - 1, max(rs) + pad)
        c0, c1 = max(0, min(cs) - pad), min(len(frame[0]) - 1, max(cs) + pad)
    else:
        r0, r1, c0, c1 = 0, len(frame) - 1, 0, len(frame[0]) - 1
    if r1 - r0 > max_r:
        r1 = r0 + max_r
    if c1 - c0 > max_c:
        c1 = c0 + max_c
    return r0, r1, c0, c1


def pick(t):
    """The example that SHOWS the most, not the one with the fewest bytes.

    Choosing by size gave a probe example whose click was at (1,1) -- a 66x66
    pixel corner in two colours -- and a plan example on a board that is almost
    entirely background. Both were valid data and neither was worth looking at.
    The board a reader sees has to have something in it, so candidates are
    scored on how much distinct structure falls inside the window that will
    actually be drawn.
    """
    from collections import Counter
    best = None
    for f in sorted(glob.glob(str(ROOT / "artifacts/wm_dataset/*.jsonl"))):
        for line in open(f):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") != t:
                continue
            fr = (e.get("input") or {}).get("frame")
            if not fr:
                continue
            tgt = e.get("target") or {}
            pts = tgt.get("cell_diff") or None
            r0, r1, c0, c1 = bounds(fr, pts)
            vals = Counter(fr[r][c] for r in range(r0, r1 + 1)
                           for c in range(c0, c1 + 1))
            cells = sum(vals.values())
            # enough colours to read as a picture, enough cells to be worth the
            # space, and not so dominated by one value that it looks blank
            top = vals.most_common(1)[0][1] / max(1, cells)
            score = (len(vals) >= 3, cells >= 150, round(1 - top, 2), len(vals))
            if best is None or score > best[0]:
                best = (score, pathlib.Path(f).name, e)
    return best


def window(frame, cells=None, pad=3, max_r=20, max_c=52):
    """A readable slice of a 64x64 board.

    Cropping to "everything that is not background" reduced nothing on these
    games: the boards are full. So when the example points at particular cells
    -- and predict always does -- the window is drawn around THOSE, which is the
    part a reader wants anyway. Otherwise it is a labelled corner.
    """
    if cells:
        rs = [c[0] for c in cells]
        cs = [c[1] for c in cells]
        r0, r1 = max(0, min(rs) - pad), min(len(frame) - 1, max(rs) + pad)
        c0, c1 = max(0, min(cs) - pad), min(len(frame[0]) - 1, max(cs) + pad)
        if r1 - r0 > max_r:
            r1 = r0 + max_r
        if c1 - c0 > max_c:
            c1 = c0 + max_c
        label = f"(변화가 일어난 자리 주변: 행 {r0}-{r1}, 열 {c0}-{c1})"
    else:
        r0, r1, c0, c1 = 0, min(len(frame) - 1, max_r), 0, min(len(frame[0]) - 1, max_c)
        label = f"(64x64 중 왼쪽 위 {r1 - r0 + 1}x{c1 - c0 + 1} 만)"
    out = ["    " + "".join(str(c % 10) for c in range(c0, c1 + 1))]
    for r in range(r0, r1 + 1):
        out.append(f"{r:3d} " + "".join(f"{frame[r][c]:x}" for c in range(c0, c1 + 1)))
    return label, "\n".join(out)


def crop(frame, pad=1):
    bg = Counter(v for row in frame for v in row).most_common(1)[0][0]
    rs = [r for r in range(len(frame)) if any(v != bg for v in frame[r])]
    cs = [c for c in range(len(frame[0]))
          if any(frame[r][c] != bg for r in range(len(frame)))]
    if not rs or not cs:
        return None
    r0, r1 = max(0, min(rs) - pad), min(len(frame) - 1, max(rs) + pad)
    c0, c1 = max(0, min(cs) - pad), min(len(frame[0]) - 1, max(cs) + pad)
    if (r1 - r0) > 26 or (c1 - c0) > 60:
        return None
    out = ["    " + "".join(str(c % 10) for c in range(c0, c1 + 1))]
    for r in range(r0, r1 + 1):
        out.append(f"{r:3d} " + "".join(f"{frame[r][c]:x}" for c in range(c0, c1 + 1)))
    return "\n".join(out)





def build():
    parts = ['  <h2 id="examples">실제 예시 데이터</h2>',
             '  <p>아래는 설명을 위해 지어낸 것이 아니라 '
             '<span class="fn">artifacts/wm_dataset/</span> 에서 그대로 꺼내온 '
             '것입니다. 프레임은 64×64라 지면상 값이 있는 구간만 잘라 한 칸에 '
             '16진수 한 자리씩으로 보여줍니다.</p>']
    for t in ("predict", "probe", "analyse", "plan"):
        got = pick(t)
        if not got:
            continue
        _, fn, e = got
        inp, tgt = e.get("input", {}), e.get("target", {})
        parts.append(f"  <h3>{t}</h3>")
        parts.append(f"  <p>{BLURB[t]}</p>")
        parts.append(f'  <p class="src">출처: <span class="fn">{fn}</span> · '
                     f'{html.escape(str(e.get("source", "")))} · '
                     f'레벨 {e.get("level")}</p>')
        body = "입력\n"
        if inp.get("frame"):
            pts = tgt.get("cell_diff") or None
            label, g = window(inp["frame"], pts)
            body += f"  frame   {label}\n{g}\n"
        else:
            body += "  frame   (없음)\n"
        for k, v in inp.items():
            if k == "frame":
                continue
            body += f"  {k}   {json.dumps(v, ensure_ascii=False)[:200]}\n"
        body += "\n목표\n"
        for k, v in tgt.items():
            s = json.dumps(v, ensure_ascii=False)
            body += f"  {k}   {s[:280]}{'…' if len(s) > 280 else ''}\n"
        parts.append(f'<div class="flow">{html.escape(body.rstrip())}</div>')
    parts.append(REPAIR)
    return "\n".join(parts)


def main():
    p = ROOT / "artifacts/wm_viz/loop.ko.html"
    s = p.read_text()
    s = s.replace(
        "agents/wm/models/&lt;게임&gt;.py 가 있으면 먼저\n"
        "  │                                  먼저 재생해 본다.",
        "agents/wm/models/&lt;게임&gt;.py 가 있으면\n"
        "  │                                  먼저 재생해 본다.")
    from gen_loop_examples_build import CSS, build
    s = re.sub(r'  <h2 id="examples">.*?(?=  <h2 id="now">)', "", s, flags=re.S)
    s = s.replace('  <h2 id="now">지금 실제 상태</h2>',
                  build() + '\n\n  <h2 id="now">지금 실제 상태</h2>')
    if ".boards{" not in s:
        s = s.replace("  .aside p:last-child{margin-bottom:0}",
                      "  .aside p:last-child{margin-bottom:0}" + CSS)
    p.write_text(s)
    print("examples section injected from the real corpus")


if __name__ == "__main__":
    main()
