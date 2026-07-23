# SK48 Beliefs and Status

## Levels Solved
- Level 0: SOLVED (14 steps, reproducible)
- Level 1: UNSOLVED (order reversal problem)

## Confirmed Dynamics (High Confidence)
1. ACTION1/2 = vertical movement (6 rows), confidence: 0.99
2. ACTION3 = retract trail from right end (6 cols), confidence: 0.95
3. ACTION4 = extend trail from right end (6 cols), confidence: 0.95
4. Trail threads blocks when passing through center rows, confidence: 0.95
5. Threaded blocks move vertically with diamond, confidence: 0.90
6. Over-retraction detaches outermost block, confidence: 0.95
7. Block order on trail is determined by threading order, confidence: 0.95
8. Blocks on wall block vertical movement, confidence: 0.90

## Level 1 Key Challenge
- All 4 blocks at same vertical position (R25-28)
- From left to right on wall: 14, 9, 12, 8
- Reference wants order (from diamond): 8, 12, 9, 14
- This is the EXACT REVERSE of the wall order
- Extending threads them in wall order (14, 9, 12, 8) - WRONG
- No known action to reverse block order on trail

## Hypotheses for Level 1 Solution
1. H1: ACTION6 or ACTION7 has a reordering effect when used in specific context (low confidence)
2. H2: Need to thread blocks individually in reverse order by creative movement (medium confidence)
3. H3: There's a way to thread from the OTHER side (approaching blocks from right) (low confidence)
4. H4: The order doesn't matter and I'm missing something else (low confidence)

## Energy Management
- Level 0 uses ~14 steps, leaving ~50 for Level 1
- Level 1 attempts so far have used 30-40 steps without success
- Need more efficient approach

## Next Steps to Try
1. Test if ACTION7 works differently when trail has specific configuration
2. Try to find if blocks can be threaded from the opposite direction
3. Try extending ACTION6 when at different positions (with/without blocks threaded)
4. Consider if the reference image means something different than assumed
5. Try threading in a creative way: thread only ♥ (rightmost) by extending trail past other blocks at a different height, then move to block height
6. Try: Move below blocks, extend trail past ♥ position, move up to block height - trail might thread ONLY ♥ since the trail tip is already past the others

## Summary
- Level 0 is reliably solved in 14 steps
- Level 1 requires block order reversal which is the main unsolved puzzle
- All basic dynamics are understood with high confidence
- The threading game ("skewer") mechanics are confirmed
- ACTION6 and ACTION7 remain poorly understood but likely important for Level 1+
