# MR Visit JP Session State Machine

## States
- initialized
- running
- awaiting_user
- evaluated
- finalized

## Transition Notes
- `start_session` creates `initialized`
- first `send_turn` moves to `running`
- `finish_session` runs evaluation and moves to `evaluated`
- persistence complete marks `finalized`
