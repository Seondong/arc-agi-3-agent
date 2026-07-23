# re86 Analysis

## Game Type
Cross/shape positioning puzzle. Move cross/diamond shapes to overlay target positions.

## Actions
- ACTION1: Move active shape up (3 pixels)
- ACTION2: Move active shape down (3 pixels)
- ACTION3: Move active shape left (3 pixels)
- ACTION4: Move active shape right (3 pixels)
- ACTION5: Cycle active shape (switch which shape the player controls)

## Mechanics
- Shapes tagged "vfaeucgcyr" are movable cross/diamond/X shapes
- Player marker (color 0) sits at the center of the active shape
- ACTION5 cycles through shapes, clearing center of old shape and marking new one
- Target boxes (tagged "vzuwsebntu") have 3x3 borders (color 4) with center color indicating which shape must cover that pixel
- Win condition: all target box center pixels must match the rendered overlay of all shapes
- Energy bar at row 63 (color 15) decreases by 1 per move
- StepCounter per level (100 for L0-L1)

## Level 0 Solution (20 moves)
Shapes: diamond cross (color 9, 27x27, center at (36,45)) and star cross (color 11, 23x23, center at (21,27))

Target analysis:
- Diamond targets need center at (48, 24): right 4, up 7
- Star targets need center at (15, 9): left 2, up 6

Solution: `action4 x4, action1 x7, action5, action3 x2, action1 x6`

## Level 1 Solution (38 moves)
3 shapes: X-diamond (color 12, 23x23, active, center (27,18)), diamond (color 13, 19x19, center (39,30)), cross (color 9, 27x27, center (48,42))

Target analysis:
- X-diamond needs center at (18, 48): left 3, down 10
- Diamond needs center at (18, 9): left 7, up 7
- Cross needs center at (27, 48): left 7, down 2

Solution: `action3 x3, action2 x10, action5, action3 x7, action1 x7, action5, action3 x7, action2 x2`

## Full Solution (both levels)
```
action4,action4,action4,action4,action1,action1,action1,action1,action1,action1,action1,action5,action3,action3,action1,action1,action1,action1,action1,action1,action3,action3,action3,action2,action2,action2,action2,action2,action2,action2,action2,action2,action2,action5,action3,action3,action3,action3,action3,action3,action3,action1,action1,action1,action1,action1,action1,action1,action5,action3,action3,action3,action3,action3,action3,action3,action2,action2
```

Result: 58 actions, Levels completed: 2
