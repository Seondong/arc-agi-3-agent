# su15 Analysis

## Game Type
Suika-style merge game with vacuum/attraction mechanic on a 64x64 grid.

## Mechanics
- 2 actions: ACTION6 (click with x,y coordinates), ACTION7 (undo)
- Click creates a vacuum effect at the click point, attracting fruits within radius 8
- Fruits move up to 4 pixels per frame toward click point, over 4 animation frames (~16px total per click)
- When 2+ same-level fruits overlap, they merge into the next level
- Fruit levels: 0 (1x1), 1 (2x2), 2 (3x3), 3 (4x4), 4 (5x5), etc.
- Win condition: specific fruit level(s) must be inside the goal area (diamond shape, color 9)
- Step counter limits total actions per level
- Bottom row (R63) shrinks by 2 cells per click (visual counter)

## Key Sprites
- Fruits tagged "fruit" - square blocks of increasing size, colors vary by level
- Goal tagged "goal" - diamond/circle shape (color 9)
- Key tagged "key" - visual indicator of target fruit type
- Background "tixakbqato" - split background (gray/dark)

## Coordinate System
- Display coordinates = grid coordinates (64x64)
- Fruit position = top-left corner of sprite
- Fruit center = position + (width//2, height//2)
- Range check: closest point on fruit bounding box to click must be <= radius 8

## Level 1 Solution (7 clicks)
- Goal: [2, 1] = 1 fruit of level 2 (3x3, color 15) in goal
- Fruit starts at (3, 58), goal at (44, 11)
- Chain of diagonal clicks pulling fruit from bottom-left to upper-right:
  1. Click (10, 52) - pull fruit from (3,58) to ~(9,51)
  2. Click (15, 45) - pull to ~(14,44)
  3. Click (21, 38) - pull to ~(20,37)
  4. Click (27, 31) - pull to ~(26,30)
  5. Click (33, 24) - pull to ~(32,23)
  6. Click (39, 17) - pull to ~(38,16)
  7. Click (45, 12) - pull into goal area -> Level complete!

## Level 2 Solution (14 clicks)
- Goal: [3, 1] = 1 fruit of level 3 (4x4, color 11/star) in goal
- 8 type-0 (1x1) fruits scattered, goal at (29, 23)
- Strategy: merge pairs progressively (0+0->1, 1+1->2, 2+2->3), then position in goal
- Merge sequence:
  1. Click (39, 38) - merge 2 type-0s into type-1
  2. Click (17, 39) - merge 2 type-0s into type-1
  3. Click (15, 56) - merge 2 type-0s into type-1
  4. Click (48, 55) - merge 2 type-0s into type-1
  5. Click (31, 37) - pull type-1 left
  6. Click (23, 38) - merge 2 type-1s into type-2
  7. Click (21, 55) - pull type-1 right
  8. Click (40, 55) - pull type-1 left
  9. Click (27, 55) - pull type-1 right more
  10. Click (33, 55) - merge 2 type-1s into type-2
  11. Click (32, 47) - pull type-2 up
  12. Click (30, 40) - merge 2 type-2s into type-3
  13. Click (28, 31) - pull type-3 toward goal
  14. Click (31, 26) - place type-3 in goal -> Level complete!

## Full Solution
Level 1+2 completed in 21 total actions.
