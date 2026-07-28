"""The visual half of gen_loop_examples: turn a pair into SVG boards + prose.

A 64x64 board printed as hex digits is complete and unreadable, which was the
first version of this section. The reader has to decode two grids by eye before
any of it means anything. These are the same numbers, painted with the same
sixteen colours the level pages use, with the cells the example actually points
at outlined in white.
"""
import html
import json

from gen_loop_examples import PAL, ROOT, bounds, pick, svg_grid  # noqa: F401

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
    "plan": "검증을 통과한 모델 안에서 BFS가 찾아낸, 그 레벨을 실제로 클리어한 "
            "액션 열입니다. 액션이 비어 있으면 버립니다. 실패한 탐색을 그대로 "
            "학습시키면 결국 이 화면에서는 아무것도 하지 말라고 가르치는 셈이 "
            "됩니다.",
}

REPAIR_NONE = """  <h3>repair <span class="tag none">아직 실물 없음</span></h3>
  <p>보여드릴 실물이 <b>아직 없습니다.</b> 그리고 없다는 사실 자체가 지금 이
  프로젝트에서 가장 중요한 문제라, 빈칸으로 넘기지 않고 적어둡니다.</p>
  <p>이 타입은 모델을 <i>쓰는</i> 법을 가르치는 유일한 종류인데, 한 쌍이 되려면
  세 조각이 다 있어야 합니다. 거절당한 소스, 검증기가 짚어준 칸들, 그리고 그
  지적을 받아 고쳐 쓴 소스입니다. 그런데 지금까지 셋 중 둘이 기록되지 않고
  있었습니다. 거절된 소스는 임시 디렉터리에 잠깐 쓰였다가 프로세스와 함께
  사라졌고, <span class="fn">refute()</span>는 <span class="fn">diff</span>
  인자를 처음부터 받도록 만들어져 있었는데 정작 그걸 넘겨주는 호출자가 하나도
  없어서 몇 개가 틀렸다는 숫자만 남았습니다.</p>
  <p>둘 다 오늘 고쳤고, KA59가 그 상태로 도는 첫 게임입니다. 쌍이 쌓이면 이
  자리에 실물을 넣겠습니다.</p>"""

CSS = """
  h3{font-size:19px;margin:34px 0 8px;font-weight:600}
  .src{font-size:12.5px;color:var(--dim);margin:0 0 14px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .grid{display:block;border-radius:4px;image-rendering:pixelated;
    outline:1px solid var(--rule)}
  .boards{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap;margin:6px 0 4px}
  .board{display:flex;flex-direction:column;gap:7px}
  .board .cap{font-size:12px;color:var(--dim);letter-spacing:.02em}
  .arrow{align-self:center;font-size:22px;color:var(--dim);padding:0 2px}
  .hit{animation:pulse 1.6s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}
  @media (prefers-reduced-motion:reduce){.hit{animation:none;opacity:.9}}
  .io{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:12px 0 0;
    font-size:13.5px;align-items:baseline}
  .io dt{color:var(--dim);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:12.5px;white-space:nowrap}
  .io dd{margin:0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:12.5px;word-break:break-all}
  .chip{display:inline-block;background:var(--panel);border:1px solid var(--rule);
    border-radius:6px;padding:2px 8px;margin:0 5px 5px 0;font-size:12px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .tag{font-size:11.5px;font-weight:500;border-radius:20px;padding:2px 10px;
    margin-left:8px;vertical-align:middle;border:1px solid var(--rule);
    color:var(--dim)}
  .tag.none{border-style:dashed}
"""


def board(frame, box, mark, cap):
    r0, r1, c0, c1 = box
    return (f'<div class="board">{svg_grid(frame, r0, r1, c0, c1, mark)}'
            f'<div class="cap">{html.escape(cap)}</div></div>')


def io_rows(pairs):
    out = ['<dl class="io">']
    for k, v in pairs:
        out.append(f"<dt>{html.escape(k)}</dt><dd>{v}</dd>")
    out.append("</dl>")
    return "".join(out)


def chips(items):
    return "".join(f'<span class="chip">{html.escape(str(x))}</span>' for x in items)


def apply_diff(frame, diff):
    after = [row[:] for row in frame]
    for r, c, v in diff:
        after[r][c] = v
    return after


def section(t, e):
    inp, tgt = e.get("input") or {}, e.get("target") or {}
    frame = inp.get("frame")
    parts = [f"  <h3>{t}</h3>", f"  <p>{BLURB[t]}</p>",
             f'  <p class="src">{html.escape(str(e.get("source", "")))} · '
             f'레벨 {e.get("level")}</p>']

    if t == "predict" and frame:
        diff = tgt.get("cell_diff") or []
        cells = [(d[0], d[1]) for d in diff]
        box = bounds(frame, diff)
        after = apply_diff(frame, diff)
        parts.append('  <div class="boards">'
                     + board(frame, box, cells, "입력 프레임")
                     + f'<div class="arrow">{html.escape(inp.get("action", ""))} →</div>'
                     + board(after, box, cells, "목표 — 이 diff를 적용한 결과")
                     + "</div>")
        parts.append("  " + io_rows([
            ("action", html.escape(str(inp.get("action")))),
            ("cell_diff", html.escape(json.dumps(diff[:8])
                                      + (" …" if len(diff) > 8 else ""))),
            ("dead", str(tgt.get("dead"))),
        ]))
        parts.append("  <p class='src'>흰 테두리가 바뀐 칸입니다. 목표는 프레임 "
                     "전체가 아니라 저 <span class='fn'>[행, 열, 새 값]</span> "
                     "목록입니다.</p>")

    elif t == "probe" and frame:
        acts = tgt.get("actions") or []
        mark = []
        for a in acts:
            if "@" in str(a):
                x, y = str(a).split("@", 1)[1].split(":")
                mark.append((int(y), int(x)))
        box = bounds(frame, [(r, c, 0) for r, c in mark] or None)
        parts.append('  <div class="boards">'
                     + board(frame, box, mark,
                             "무엇을 눌러볼지 정해야 하는 화면")
                     + "</div>")
        parts.append("  " + io_rows([
            ("question", html.escape(str(inp.get("question")))),
            ("actions", chips(acts)),
            ("observed", html.escape(str(tgt.get("observed")))),
            ("died", str(tgt.get("died"))),
        ]))

    elif t == "analyse" and frame:
        ents = tgt.get("entities") or {}
        mark = [tuple(v[:2]) for v in ents.values() if isinstance(v, list)
                and len(v) >= 2 and all(isinstance(x, int) for x in v[:2])]
        box = bounds(frame, [(r, c, 0) for r, c in mark] or None)
        parts.append('  <div class="boards">'
                     + board(frame, box, mark, "입력 — 프레임 하나")
                     + "</div>")
        parts.append("  " + io_rows(
            [("entities", html.escape(json.dumps(ents, ensure_ascii=False)))]))
        parts.append("  <p class='src'>흰 테두리가 모델이 개체라고 지목한 "
                     "자리입니다.</p>")

    elif t == "plan" and frame:
        acts = tgt.get("actions") or []
        st = tgt.get("stats") or {}
        box = bounds(frame, None)
        parts.append('  <div class="boards">'
                     + board(frame, box, [], "입력 — 레벨의 첫 프레임")
                     + "</div>")
        parts.append("  " + io_rows([
            ("actions", chips(acts)),
            ("stats", html.escape(json.dumps(st))),
        ]))
        parts.append(f"  <p class='src'>모델 안에서 {st.get('sims', '?')}번을 "
                     f"시뮬레이션해 찾은 열입니다. 환경 액션은 여기서 "
                     f"<b>0</b>이고, 실제로 쓰인 것은 저 "
                     f"{len(acts)}개뿐입니다.</p>")
    return "\n".join(parts)


def pick_repair():
    """A repair pair, preferring one whose counterexample is a status mismatch.

    Those are the sharpest: no cell is wrong, so the model has the dynamics
    right and only its idea of winning is wrong.
    """
    import glob
    best = None
    for f in sorted(glob.glob(str(ROOT / "artifacts/wm_dataset/*.jsonl"))):
        for line in open(f):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") != "repair":
                continue
            bug = (e.get("input") or {}).get("bug") or ""
            score = ("status predicted" in bug, -len(json.dumps(e)))
            if best is None or score > best[0]:
                best = (score, e)
    return best[1] if best else None


def repair_section(e):
    i, t = e.get("input") or {}, e.get("target") or {}
    before, after = i.get("model_source_before", ""), t.get("model_source_after", "")
    status_only = "status predicted" in (i.get("bug") or "")
    why = ("셀은 하나도 틀리지 않았습니다. 동역학은 맞고 <b>무엇이 승리인지</b>에 "
           "대한 판단만 틀린 경우이고, 이것이 루프가 만드는 반례 중 가장 날카로운 "
           "종류입니다." if status_only else
           "검증기가 어느 칸이 어떻게 틀렸는지 정확히 짚어 돌려준 경우입니다.")
    return "\n".join([
        '  <h3>repair <span class="tag">가장 희소함</span></h3>',
        "  <p>모델을 <i>쓰는</i> 법을 가르치는 유일한 타입입니다. 한 쌍이 되려면 "
        "거절당하거나 반증당한 소스, 검증기가 짚은 지점, 그리고 그 지적을 받아 "
        "고쳐 쓴 소스가 모두 있어야 합니다.</p>",
        f'  <p class="src">{html.escape(str(e.get("source","")))} · '
        f'레벨 {e.get("level")}</p>',
        "  " + io_rows([
            ("반례", html.escape(i.get("bug", "")[:160])),
            ("짚힌 칸", f"{len(i.get('cells') or [])}개"),
            ("고치기 전", f"{len(before):,}자"),
            ("고친 뒤", f"{len(after):,}자"),
        ]),
        f"  <p class='src'>{why}</p>",
        "  <p>입력과 목표가 둘 다 파이썬 소스라는 점에서 다른 네 타입과 다릅니다. "
        "모델이 배워야 하는 것은 프레임을 읽는 법이 아니라 <b>지적을 받아 자기 "
        "이론을 고치는 법</b>입니다.</p>",
    ])


def build():
    parts = ['  <h2 id="examples">실제 예시 데이터</h2>',
             '  <p>설명을 위해 지어낸 것이 아니라 '
             '<span class="fn">artifacts/wm_dataset/</span> 에서 그대로 꺼내온 '
             '것입니다. 보드는 <span class="fn">gen_loop_examples.py</span>가 '
             '빌드할 때 SVG로 그리므로, 코퍼스가 바뀌면 이 그림도 함께 바뀝니다. '
             '색은 레벨 페이지들이 쓰는 것과 같은 16색입니다.</p>']
    for t in ("predict", "probe", "analyse", "plan"):
        got = pick(t)
        if got:
            parts.append(section(t, got[2]))
    got = pick_repair()
    parts.append(repair_section(got) if got else REPAIR_NONE)
    return "\n".join(parts)
