# BP35 Analysis (bottomless_pit)

## Game: bp35-0a0ad940
- Tags: keyboard_click
- Baseline actions: 15, 72, 36, 31, 31, 48, 86, 155, 163
- Source: games/bottomless_pit

## Actions
- ACTION3: move(-1, 0) = LEFT (moves player 6 columns left)
- ACTION4: move(1, 0) = RIGHT (moves player 6 columns right)
- ACTION6: click(x, y) = Opens/destroys 14-blocks (5x5 grid sections)
- ACTION7: UNDO last action (restores destroyed blocks)
- ACTION1/ACTION2 (UP/DOWN): Not available in valid actions

## Map Structure
- 64x64 grid, player area at R37-41 horizontal band
- Player (11/star) surrounded by diamond of 9 cells
- 10 = open area, 14 = breakable blocks, 5 = walls/corridors
- 0 = goal row at R63, 15 = progress bar growing from left
- Map shifts when player reaches edge boundaries (1000+ cell changes)

## Key Mechanics
- Player moves horizontally in 6-column steps
- ACTION6 click destroys 5x5 blocks of type 14 (needs correct coordinates)
- Click coordinates: x=column, y=row of target block center
- Map scrolls/rearranges when player reaches horizontal boundaries
- Each step increases the 15-bar at R63 by 1 cell

## Observations
- Clearing all 14-blocks in visible area does not complete level
- Map generates new 14-blocks when scrolling to new sections
- Object 7 appeared after many steps (possible goal/portal)
- ACTION7 is UNDO, not fall (despite "bottomless_pit" name)
- The game seems to require finding a specific path/target

## Status: L0 not yet completed
- Need to discover the correct sequence for level completion
- Possibly need to reach a specific map location or clear specific blocks
