# Web Acceptance Walkthrough

This checklist is the browser-level acceptance path until Playwright coverage is added.

Prerequisites:

```bash
make stack-up
make smoke-check
```

Use `http://127.0.0.1:3000`.

## Auth

- With `AUTH_MODE=mock`, open `/login`.
- Log in as `learner_demo_001` with password `Welcome123`.
- Confirm the header shows the active learner context.

## MR Training Loop

- Open `/scenarios`.
- Start `busy_doctor_short_visit`.
- Send one learner turn.
- Finish the session.
- Confirm the review page shows score, subskill diagnosis, evidence, compliance state, and next actions.

## Records And Progress

- Open `/records`.
- Filter/search records and open the latest record.
- Confirm `/records/[id]` shows replay/session context.
- Open `/records/[id]/review` and confirm it renders the same finalized review.
- Open `/progress` and confirm latest recommendations and practice path are visible.

## Marketplace And Cross-Skill Dashboard

- Open `/marketplace`.
- Confirm `mr_visit_jp` appears as stable and `gp_visit_jp` appears as spike.
- For an organization admin mock user, confirm install/disable controls render.
- Open `/` and confirm installed skills are summarized without flattening MR and GP scoring semantics.

## Training Plans

- Log in as `org_admin_demo`.
- Open `/admin` and `/training-plans/<plan_id>` when a plan exists.
- Confirm plan goals, assigned learners, status, and evidence-backed progress are shown.
- Open `/team` and confirm supervisor summaries show plan progress and at-risk learners without raw transcript exposure.

## Cleanup

```bash
make stack-down
```
