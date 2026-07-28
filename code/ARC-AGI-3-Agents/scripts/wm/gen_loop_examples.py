"""Inject a real-data examples section into loop.ko.html.

Everything shown is pulled from artifacts/wm_dataset/ at build time, so the page
cannot drift from the corpus it describes.
"""
import glob
import html
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path("/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents")


def pick(t):
    """The smallest example of this type WHOSE GRID CAN BE SHOWN.

    Picking purely by size chose a frame too wide to crop, so the page printed
    "<64x64 grid>" — which is exactly the placeholder the reader is here to get
    away from. A visible grid is worth more than a few bytes saved.
    """
    best = best_any = None
    for f in sorted(glob.glob(str(ROOT / "artifacts/wm_dataset/*.jsonl"))):
        for line in open(f):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") != t:
                continue
            n = len(json.dumps(e))
            if best_any is None or n < best_any[0]:
                best_any = (n, pathlib.Path(f).name, e)
            fr = (e.get("input") or {}).get("frame")
            if fr and (best is None or n < best[0]):
                best = (n, pathlib.Path(f).name, e)
    return best or best_any


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


BLURB = {
    "predict": "가장 흔하고 가장 깨끗한 타입입니다. 엔진이 결정적이라서 저장된 "
               "해답만 있으면 공짜로 다시 만들어낼 수 있습니다. 목표가 프레임 "
               "전체가 아니라 <b>바뀐 칸만</b>이라는 점이 중요합니다. 64×64를 "
               "통째로 뱉게 하면 정작 배워야 할 것이 묽어집니다.",
    "probe": "무엇을 모르는지 알아차리고, 그걸 알아내려고 액션을 쓰고, 무엇이 "
             "돌아왔는지 적는 과정입니다. 정답이 아니라 <b>알아보는 행위</b> 자체를 "
             "가르치는 타입입니다.",
    "analyse": "화면을 보고 거기 무엇이 있는지 말하는 것입니다. 목표가 비어 있으면 "
               "학습쌍으로 치지 않습니다. 예전에는 59개 중 38개가 개체 목록 없이 "
               "로그 한 줄만 달고 있었습니다.",
    "plan": "검증을 통과한 모델 안에서 BFS가 찾아낸, 그 레벨을 실제로 클리어한 액션 "
            "열입니다. 액션이 비어 있으면 버립니다. 실패한 탐색을 그대로 학습시키면 "
            "결국 이 화면에서는 아무것도 하지 말라고 가르치는 셈이 됩니다.",
}

REPAIR = """  <h3>repair</h3>
  <p>보여드릴 실물이 <b>아직 없습니다.</b> 그리고 없다는 사실 자체가 지금 이
  프로젝트에서 가장 중요한 문제라, 빈칸으로 넘기지 않고 적어둡니다.</p>
  <p>이 타입은 모델을 <i>쓰는</i> 법을 가르치는 유일한 종류인데, 한 쌍이 되려면
  세 조각이 다 있어야 합니다. 거절당한 소스, 검증기가 짚어준 칸들, 그리고 그
  지적을 받아 고쳐 쓴 소스입니다. 그런데 지금까지 셋 중 둘이 기록되지 않고
  있었습니다. 거절된 소스는 임시 디렉터리에 잠깐 쓰였다가 프로세스와 함께
  사라졌고, <span class="fn">refute()</span>는 <span class="fn">diff</span>
  인자를 처음부터 받도록 만들어져 있었는데 정작 그걸 넘겨주는 호출자가 하나도
  없어서 "몇 개가 틀렸다"는 숫자만 남았습니다.</p>
  <p>둘 다 오늘 고쳤고, KA59가 그 상태로 도는 첫 게임입니다. 쌍이 쌓이면 이
  자리에 실물을 넣겠습니다.</p>"""


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
    if 'id="examples"' not in s:
        s = s.replace('  <h2 id="now">지금 실제 상태</h2>',
                      build() + '\n\n  <h2 id="now">지금 실제 상태</h2>')
    s = s.replace("  .aside p:last-child{margin-bottom:0}",
                  "  .aside p:last-child{margin-bottom:0}\n"
                  "  h3{font-size:18px;margin:28px 0 8px;font-weight:600}\n"
                  "  .src{font-size:13px;color:var(--dim);margin:0 0 10px}")
    p.write_text(s)
    print("examples section injected from the real corpus")


if __name__ == "__main__":
    main()
