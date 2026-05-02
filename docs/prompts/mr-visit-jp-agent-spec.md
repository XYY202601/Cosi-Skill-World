# MR Visit JP Agent Spec

## Agents
- Doctor Agent: roleplay and response generation
- Director Agent: pacing and scene constraints
- Judge Agent: structured scoring and diagnosis
- Coach Agent: learner feedback and next actions
- Compliance Checker: compliance event tagging

## Output Discipline
All judge/coach/compliance outputs must be validated against schemas in `packages/shared-schemas`.

## Prompt Asset Rules
- Base prompt contracts live at `domains/mr_visit_jp/prompts/<role>/openai_compat.yaml`.
- Prompt profiles live at `domains/mr_visit_jp/prompts/openai_compat_profiles.yaml`.
- Profile lookup is deterministic: an explicit `profile_id` wins, otherwise the registry `default_profile` is used.
- Role fallback is deterministic: if a profile does not override a role, the base role contract is used unchanged.
- Any profile override that changes prompt text or output requirements must also bump that role's `version` above the base contract version.
- Version-only overrides without prompt-content changes are invalid.
- Runtime boot validates prompt contracts and prompt profiles before any session starts.
- Prompt assembly is snapshot-tested so prompt drift is visible in review.
