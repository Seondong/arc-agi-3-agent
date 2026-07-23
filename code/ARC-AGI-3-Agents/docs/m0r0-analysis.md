# m0r0 Game Analysis

## Game Type
Mirror-movement block merging puzzle (Sokoban variant)

## Mechanics
- **ACTION1**: Move up (dy=-1)
- **ACTION2**: Move down (dy=1)
- **ACTION3**: Move left (dx=-1)
- **ACTION4**: Move right (dx=1)
- **ACTION5**: No observable effect
- **ACTION6**: Click to select individual block (cvcer sprites) or enter all-move mode
- **Step limit**: 150 actions total

### Block Movement Rules
When no cvcer is selected (vmcbq=True), ALL blocks move simultaneously with mirrored directions:
- `ubwff-idtiq`: moves (dx, dy) - normal direction
- `ubwff-crkfz`: moves (-dx, dy) - x-mirrored, y-same
- `kncqr-idtiq`: moves (dx, -dy) - y-mirrored (appears in later levels)
- `kncqr-crkfz`: moves (-dx, -dy) - both mirrored (appears in later levels)

When a cvcer sprite is clicked/selected, only that sprite moves normally.

### Win Condition
When two blocks occupy the same grid position after movement, they merge (become INTANGIBLE). When ALL movable blocks are merged/removed, the level advances.

### Hazards (wyiex)
If a block lands on a wyiex cell, all blocks reset to starting positions.

## Level 1 (L0) - SOLVED
- **Grid**: 11x11
- **Maze**: jggua-Level6 rotated 180 degrees
- **Blocks**: ubwff-idtiq at (3,9), ubwff-crkfz at (7,9)
- **No cvcer sprites** - all blocks always move together
- **No wyiex hazards**

### Solution (15 moves)
U U L U L U U U U U R R R U R
(ACTION1 ACTION1 ACTION3 ACTION1 ACTION3 ACTION1 ACTION1 ACTION1 ACTION1 ACTION1 ACTION4 ACTION4 ACTION4 ACTION1 ACTION4)

### Maze Layout (rotated 180, -1=open, 0=wall)
```
     0  1  2  3  4  5  6  7  8  9  10
r0:  W  W  W  W  W  W  W  W  W  W  W
r1:  W  W  W  .  .  .  .  .  W  W  W
r2:  W  W  .  .  .  W  .  .  .  .  W
r3:  W  .  .  .  W  W  W  .  .  .  W
r4:  W  .  .  W  W  W  W  W  .  .  W
r5:  W  W  .  W  W  W  W  W  W  .  W
r6:  W  W  .  W  W  W  W  W  W  .  W
r7:  W  .  .  .  W  W  W  W  .  .  W
r8:  W  .  .  .  .  W  .  .  .  .  W
r9:  W  .  .  .  .  W  .  .  .  .  W
r10: W  .  .  .  .  W  .  .  .  W  W
```
Only row 1 has x=5 open, so blocks must navigate up through separate corridors and merge at (5,1).

## Level 2 (L1) - IN PROGRESS (43/150 steps used)
- **Grid**: 13x13
- **Maze**: jggua-Level11 at position (2,0)
- **Blocks**: ubwff-idtiq at (4,1), ubwff-crkfz at (8,1)
- **Many wyiex hazards**: rows 8 and 12 heavily mined, column 5 rows 5-8
- **Central wall at x=6** divides left/right halves
- **Single passage at (3,4)** connects the two halves
- Blocks outside the maze (x<2, x>10) hit wyiex on row 8 perimeter

### Maze Layout (at grid offset +2,0)
```
     x: 2  3  4  5  6  7  8  9  10
y=0: .  .  .  .  W  .  .  .  .
y=1: .  .  .  .  W  .  .  .  .
y=2: .  .  .  .  W  .  .  .  .
y=3: W  W  W  W  W  W  W  W  W
y=4: W  .  W  W  W  W  W  W  W
y=5: .  .  .  .  W  .  .  .  .
y=6: .  .  .  .  W  .  .  .  .
y=7: .  .  .  .  W  .  .  .  .
y=8: .  .  .  .  W  .  .  .  .
y=9: .  .  .  .  W  .  .  .  .
```

### Wyiex (hazard) positions
- (5,5), (5,6), (5,7), (5,8)
- y=8: x=0,1,2,4,5,8,9,10,11,12 (safe only: x=3,7)
- y=12: x=0-12 (entire row - blocks perimeter navigation)

### Key Challenge
1. x=6 wall blocks center merging
2. Only passage between halves at (3,4)
3. Wyiex at row 8 blocks most horizontal positions (safe only at x=3 and x=7)
4. Block mirroring means idtiq_x + crkfz_x = 12 always, but safe spots at row 8 sum to 10 (3+7)
5. Solution requires using wall collisions to create asymmetric effective movement
6. Perimeter navigation fails due to wyiex on borders at row 8
