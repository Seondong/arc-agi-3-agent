# ft09 Analysis

## Game Mechanics
- **Type**: Lights-out / color-toggle puzzle
- **Action**: ACTION6 with x,y display coordinates (click-based)
- **Colors**: Two-color cycling (e.g., [9,8] or [9,12])
- **Toggle pattern** (`elp`): Controls which neighbors are toggled when clicking. Level 0-1 use `[[0,0,0],[0,1,0],[0,0,0]]` (only clicked cell)
- **Energy**: Each click costs 1 energy (displayed as bar at R63). Game over when energy=0.

## Win Condition
For each "bsT" (constraint) sprite:
- Center pixel value = target color
- For each of 8 neighbors: if constraint pixel == 0, neighbor must match target; if != 0, neighbor must NOT match target

## Level 0 (THR) - SOLVED
- Grid: 3x3 Hkx sprites around center wmW constraint
- Colors: [9, 8] (diamond, heart)
- Constraint wmW pixels: `[[0,2,2],[0,8,0],[0,2,2]]` center=8
- Target: TL=8, TC=9, TR=9, ML=8, MR=8, BL=8, BC=9, BR=9
- Display coordinates: (37,37), (37,45), (53,45), (37,53) - 4 clicks
- Solution: `[RESET, click(37,37), click(37,45), click(53,45), click(37,53)]`

## Level 1 (hxv) - SOLVED
- Grid: 3x5 Hkx sprites with 2 constraint sprites (jGI, EQX)
- Colors: [9, 12] (diamond, triangle)
- Display mapping: display_coord = grid_coord * 2
- Clicks needed (7): (20,14), (20,22), (36,22), (20,30), (36,30), (20,46), (28,46)

## Key Discoveries
- Display coordinates depend on camera scale and grid layout
- Level 0: scale ~2x per grid unit (6-pixel sprite blocks), bottom-right quadrant
- Level 1: scale 2x per grid unit, centered display
- Constraint sprites have 3x3 pixel patterns encoding match/no-match requirements
- Grid spacing between sprites is 4 grid units (8 display pixels at 2x scale)
