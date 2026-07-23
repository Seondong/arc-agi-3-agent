"""
SK48 World Model - Threading/Skewer Game
Version 0.5 - Based on Level 0 solution and Level 1 exploration

Core Mechanics:
- Diamond (val 6/0) is the player-controlled object
- Trail (val 1=bullet, 2=circle) extends horizontally from diamond
- Colored blocks (val 8,9,12,14) are targets on the right wall
- Reference image at bottom shows goal arrangement

Actions:
- ACTION1: Move diamond UP by 6 rows (along vertical rail)
- ACTION2: Move diamond DOWN by 6 rows
- ACTION3: RETRACT trail from right end (6 cols, pulls threaded blocks left)
- ACTION4: EXTEND trail from right end (6 cols, threads blocks it passes through)
- ACTION6: Unknown (no observed effect)
- ACTION7: Seems to retract from right end (same as ACTION3 in some contexts)
           OR extend from diamond end (pushing blocks right) - NEEDS MORE TESTING

Threading Mechanics:
- Trail passes through a block's center rows -> block is "threaded"
- Threaded blocks move with the diamond+trail vertically
- Retraction pulls all threaded blocks toward diamond
- Over-retraction (past minimum trail length) causes outermost block to detach
- Blocks still on wall block vertical movement (must retract off wall first)
- Detached blocks remain at their current position

Level 0 Solution (14 steps):
1. ACTION1 x3 (UP to heart height R18)
2. ACTION4 x4 (extend through heart)
3. ACTION3 x1 (retract heart off wall)
4. ACTION2 x2 (DOWN to block14 height R30)
5. ACTION4 x1 (extend through block14)
6. ACTION3 x1 (retract block14 off wall)
7. ACTION1 x1 (UP to diamond-shape height R24)
8. ACTION4 x1 (extend through diamond-shape -> LEVEL COMPLETE)

Level 1 Puzzle:
- 4 blocks all at same row: 14(C30), 9(C36), 12(C42), 8(C48)
- Reference order: 8(heart), 12(triangle), 9(diamond), 14(block14) from diamond outward
- But extending threads them in order: 14, 9, 12, 8 (reversed!)
- The REVERSAL problem is the key challenge of Level 1
- Unknown actions (ACTION6, ACTION7) don't seem to help with reordering

Energy:
- Bar at R53, 64 cells max
- Each extend/retract costs ~1 energy
- Vertical moves seem free or low cost

Confidence Scores:
- ACTION1/2 = UP/DOWN: 0.99
- ACTION3 = RETRACT: 0.95
- ACTION4 = EXTEND: 0.95
- Threading mechanic: 0.95
- Block order matters: 0.90
- ACTION6 purpose: UNKNOWN
- ACTION7 = retract/drop outermost: 0.60
"""

class SK48World:
    def __init__(self):
        self.diamond_row = 42  # Top row of diamond (Level 1)
        self.diamond_col = 5   # Left col of diamond (Level 1)
        self.STEP_SIZE = 6
        self.trail_length = 6  # Initial trail length (cells per row)
        self.threaded_blocks = []  # List of block values in order from diamond
        self.energy = 64

    def action1(self):  # UP
        """Move diamond + trail + threaded blocks up by 6 rows"""
        self.diamond_row -= self.STEP_SIZE

    def action2(self):  # DOWN
        """Move diamond + trail + threaded blocks down by 6 rows"""
        self.diamond_row += self.STEP_SIZE

    def action3(self):  # RETRACT
        """Retract trail from right end, pulling blocks left.
        If trail gets too short, outermost block detaches."""
        self.trail_length -= self.STEP_SIZE
        if self.trail_length < self._min_trail_length():
            if self.threaded_blocks:
                self.threaded_blocks.pop()  # Remove outermost block
        self.energy -= 1

    def action4(self):  # EXTEND
        """Extend trail from right end. If trail reaches a block, thread it."""
        self.trail_length += self.STEP_SIZE
        self.energy -= 1
        # Check for block threading at trail tip

    def _min_trail_length(self):
        """Minimum trail length to keep all blocks threaded"""
        # Each block takes 4 cells + 2 trail cells between blocks
        return 2 + len(self.threaded_blocks) * 6
