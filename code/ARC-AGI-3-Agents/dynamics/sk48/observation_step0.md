# SK48 Observations - Level 0

## Initial State
- 64x64 grid, background value 5
- Diamond (val 6/0) at R36-41, C11-16 (6x6)
- Trail at R38-39, C17-22 (alternating 1/2 pattern, 12 cells)
- Three colored blocks on right wall (C42-45):
  - Heart (val 8): R19-22
  - Diamond-shape (val 9): R25-28
  - Block14 (val 14): R31-34
- Vertical rail on left: C13-14, markers at 6-row intervals
- Energy bar at R53: full row of val 2 (64 cells)
- Reference/goal at R56-61

## Dynamics Discovered
- ACTION1 = UP (moves diamond+trail 6 rows up)
- ACTION2 = DOWN (moves diamond+trail 6 rows down)
- ACTION3 = RETRACT trail (6 columns left, pulls threaded blocks)
- ACTION4 = EXTEND trail (6 columns right)
- Diamond + trail + threaded blocks move as one unit vertically
- Energy cost: ~1 per ACTION4 (observed at R53)
- Threading: when trail passes through a block, block is "threaded"
- Retraction pulls threaded blocks left
- Cannot move vertically if a block is still attached to the wall
- Must retract to pull block off wall before vertical movement is possible
- Blocks on wall block vertical movement past them

## Level 0 Solution (14 steps)
1. ACTION1 x3 (move to heart height R18)
2. ACTION4 x4 (extend trail to thread heart at C42-45)
3. ACTION3 x1 (retract to pull heart off wall to C36-39)
4. ACTION2 x2 (move down to block14 height R30)
5. ACTION4 x1 (extend trail to thread block14 at C42-45)
6. ACTION3 x1 (retract to pull block14 off wall)
7. ACTION1 x1 (move up to diamond-shape height R24)
8. ACTION4 x1 (extend trail to thread diamond-shape -> LEVEL COMPLETE)

## Key Insight
- Thread blocks in the ORDER shown in the reference image
- Reference order: heart -> block14 -> diamond-shape (NOT top-to-bottom)
- Must retract after threading to free block from wall before moving vertically
