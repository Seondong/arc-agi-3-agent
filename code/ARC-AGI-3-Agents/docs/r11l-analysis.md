# r11l Analysis

## Game Type
Drag-and-drop puzzle. Move spider-like pieces (body + legs) to target positions.

## Actions
- ACTION6: Click at {x,y} coordinates. Valid coordinates are multiples of 4 (0, 4, 8, ..., 60)
  - Click on a leg sprite to select it as the active piece
  - Click elsewhere to move the active piece toward that position

## Key Mechanics
- Pieces consist of: body (bdkaz), legs (bdkazLeg), target (kzeze)
- Body is a 5x5 diamond shape with color 15 (value 15) and center diamond (value 6)
- Legs are 5x5 diamond shapes with color 0 (circles) and center 15
- Each piece has 2+ legs connected to 1 body
- Body position = average of all legs' center positions
- Win: all bodies overlap their corresponding targets
- Step counter depletes with each action (lives shown in column 0)
- Obstacles (qtwnv, bvzgd) block movement
- Animation moves piece in 1 frame (gfwuu=1)
- If piece hits obstacle during animation, 5 strikes = lose
- Max ~64 actions before game over

## Level 1
- 1 piece (kpaac): body at (15,45), legs at (5,34) and (25,57), target at (36,18)
- Need to move both legs so body centers at target (36+2, 18+2) = (38, 20)
- Strategy: click leg at (4,36) to select, move to position, then click second leg at ~(28,56), move to position
- Both legs' centers must average to (38, 20) for body to overlap target

## Level 2
- 2 pieces (kpaac and qniqj)
- kpaac: body (48,39), legs (43,33) and (52,46), target (54,15)
- qniqj: body (23,11), legs (15,4), (6,19), (47,7), target (37,48)
- Has obstacle (qtwnv) - need to avoid it

## Status
In progress. Mechanics understood but precise coordinate targeting needed.
