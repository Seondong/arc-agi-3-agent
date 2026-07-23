# CD82 Analysis (crane_dipper)

## Game: cd82-fb555c5d
- Tags: keyboard_click
- Baseline actions: 41, 8, 30, 21, 19, 17
- Source: games/crane_dipper

## Actions
- ACTION1: nqhfiooufi(1) - crane direction 1 (minimal visible effect)
- ACTION2: nqhfiooufi(2) - crane direction 2 (minimal visible effect)
- ACTION3: nqhfiooufi(3) - transforms 2-bordered rectangle to diamond (201 cells)
- ACTION4: nqhfiooufi(4) - transforms diamond back to rectangle (201 cells)
- ACTION5: nlvliaznao() - "dip" crane, fills area below with 15 cells, resets step counter
- ACTION6: click(x, y) - click on target positions

## Map Structure
- 64x64 grid
- Upper left (R3-7): 0-block (target to fill)
- Below (R8-12): 15-block (reference pattern)
- Center (R24-32): 2-bordered rectangle with 15 inside
- Lower (R34-43): area that gets filled by dipping
- Hint boxes at R2-7 top-right showing box + box pattern

## Key Mechanics
- Step counter (iieoxmyyd) tracks transforms since last dip
- Need 3+ transforms before dipping has effect
- Different rotation sequences fill different triangular areas:
  - ACTION3,ACTION4,ACTION3 + dip: fills ~56 cells (top portion)
  - ACTION4,ACTION3,ACTION4 + dip: fills ~11 cells (small triangle)
  - ACTION4,ACTION4,ACTION4 + dip: fills ~15 cells (right triangle)
  - ACTION2,ACTION2,ACTION2 + dip: fills ~20 cells (left triangle)
- Level completion: compares two 10x10 sprite arrays with X-diagonal mask

## Filling Sequences Found
1. ACTION3, ACTION4, ACTION3, ACTION5 -> 56 cells filled
2. ACTION4, ACTION3, ACTION4, ACTION5 -> 11 cells filled
3. ACTION4, ACTION4, ACTION4, ACTION5 -> 15 cells filled
4. ACTION2, ACTION2, ACTION2, ACTION5 -> 20 cells filled

## Status: L0 not yet completed
- Successfully filled the lower 10x10 area (R34-43,C27-36)
- Remaining 64 cells of 0-type at R3-7 (upper block)
- Need to discover how to affect the upper block or complete the level check
