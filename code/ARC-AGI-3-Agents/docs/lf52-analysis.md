# lf52 Game Analysis

## Game Type
Custom puzzle game with complex internal game engine (5,877 lines of source)

## Mechanics
- **ACTION1**: Move up (0, -1)
- **ACTION2**: Move down (0, 1)
- **ACTION3**: Move left (-1, 0)
- **ACTION4**: Move right (1, 0)
- **ACTION5**: Special action (kuexigxyxw)
- **ACTION6**: Click at (x, y) - interacts with special UI elements or game objects
- **ACTION7**: Undo (when available)

### Internal Engine
- Uses custom game engine class `equnaohchtj` with rendering pipeline
- Camera-based rendering with zoom/scroll
- Objects include "fozwvlovdui", "lgbyiaitpdi", "dgxfozncuiz" sprites

### Step Limits
- Level 1 (whtqurkphir=1): 64 actions max
- Levels 2-5: 320 actions max (64*5)
- Levels 6+: 640 actions max (64*10)

### ACTION6 Special Behavior
- If clicking at x<16, y>48 (bottom-left corner): triggers a special animation/transition
- Otherwise: interacts with game objects via dghsidbuet(x, y)

## Visual Layout (64x64 rendered grid)
- Row 0: Counter/status bar (white circles)
- Rows 1-9: Background (orange/color 10)
- Rows 10-53: Two connected rectangular rooms with walls
  - Upper room: R10-29, C9-43 (with gap at R29 C25+)
  - Lower room: R29-53, C33-52
- Rooms contain:
  - White circles (color 0) as corridors
  - Black circles (color 1) as 4x4 blocks in grid pattern
  - Color 14 blocks at specific positions (highlighted cells)
  - Walls (grey) as boundaries
  - Diamond markers (color 9) on right edge

### Pattern
The grid inside the rooms shows a regular pattern of 4x4 black blocks with white spaces between them. Some blocks have color 14 (special) markings that appear to indicate a puzzle target pattern.

## Status
- Game structure identified - appears to be a complex Sokoban or pattern-matching puzzle
- Directional movement confirmed (ACTION1-4)
- Each action increments a step counter (1 cell change at R0)
- ACTION6 click on game objects highlights adjacent cells (29-cell diff observed)
- ACTION7 is undo functionality
- Level 1-2 NOT YET SOLVED - requires understanding the specific puzzle goal
