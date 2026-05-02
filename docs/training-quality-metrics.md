# Training Quality Metrics Definition (B0)

Version: 1
Domain: mr_visit_jp
Status: active

## Purpose

Define measurable training-quality signals for the MR training loop. Each dimension below
answers a concrete question a learner or trainer would ask after a session. These metrics
guide B1-B4 implementation and prevent treating valid schema output as sufficient proof of
learning value.

---

## Dimension 1: Scenario Realism

**Question:** Does the practice feel like a real MR visit?

**Definition:**
The scenario's persona behavior, doctor responses, and visit constraints produce
a believable interaction that reflects genuine MR practice conditions.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Persona responses vary by context; doctor pushes back on vague claims; time pressure is felt; scenario-specific constraints shape the flow. |
| Good | Persona follows a defined behavior pattern; doctor responds to key trigger phrases; basic constraints are enforced. |
| Functional | Persona has a single response template; doctor reacts only to explicit keywords; constraints are loose. |
| Poor | Persona is static or absent; doctor gives generic responses; no meaningful constraints. |

**Fixture-Checkable:** Partially (deterministic)
- Constraint enforcement (max_turns respected, persona_id mapped correctly)
- Director event variety (at least N distinct event types across turns)
- Playbook field presence and validity

**SME Review Required:**
- Whether doctor tone and pushback feel authentic to practicing MRs
- Whether scenario difficulty matches real-world difficulty distribution

**Maps to:** B1 (playbook depth directly affects persona behavior variety)

---

## Dimension 2: Turn Guidance Specificity

**Question:** Does the Director give useful turn-by-turn guidance?

**Definition:**
Director events and phase signals provide specific, actionable feedback at each turn
rather than generic "good job" or "needs improvement" labels.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Director events reference specific behaviors (e.g., "opening_missing_permission" not "bad_opening"); phase transitions are contextual; recovery hints point to concrete next actions. |
| Good | Events are specific to subskills; phase tracking is accurate; hints are category-level. |
| Functional | Events exist but are broad ("low_quality_turn"); phase tracking is basic; hints are generic. |
| Poor | No director events; no phase tracking; no guidance. |

**Fixture-Checkable:** Yes (deterministic)
- Director events match expected event taxonomy
- Phase transitions follow expected flow for scenario type
- Recovery hints are non-empty and scenario-relevant

**SME Review Required:**
- Whether guidance timing and tone are pedagogically appropriate
- Whether event granularity is useful (not too fine, not too coarse)

**Maps to:** B1 (playbook recovery_moves and expected_flow inform Director heuristics)

---

## Dimension 3: Evidence Quality

**Question:** Does the evaluation point to specific transcript evidence?

**Definition:**
Score justifications and diagnosis claims are backed by turn-indexed transcript excerpts,
not unsupported assertions about learner behavior.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Every subskill score has at least one turn-indexed evidence item with excerpt; evidence tags categorize the signal type; evidence spans multiple relevant turns when applicable. |
| Good | Priority subskills have turn-indexed evidence; evidence excerpts are verbatim or near-verbatim; tags indicate signal type. |
| Functional | Most subskills have some evidence text; turn references exist but may be inaccurate; excerpts are paraphrased. |
| Poor | Scores have no evidence beyond "Derived from N turns"; no turn references; no excerpts. |

**Fixture-Checkable:** Yes (deterministic)
- Evidence items have valid turn_index when present
- Evidence summary is non-empty for each subskill
- MAX_EVIDENCE_ITEMS contract is respected
- Evidence tags are drawn from allowed tag vocabulary

**SME Review Required:**
- Whether the selected evidence is the *most relevant* evidence for the score
- Whether evidence excerpts fairly represent the turn

**Maps to:** C2a (evidence display in review UX), C2b (transcript linking)

---

## Dimension 4: Diagnosis Clarity

**Question:** Does the learner understand what went wrong and why?

**Definition:**
The primary diagnosis explains skill gaps or communication issues in language the
learner can understand, with a clear link to observable transcript behavior.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Diagnosis names a specific gap with concrete transcript reference; severity is appropriate; recommendation_focus targets the right subskills; multiple diagnoses are prioritized not dumped. |
| Good | Diagnosis is specific to a subskill area; summary is understandable; severity is set; recommendation_focus is populated. |
| Functional | Diagnosis is in the catalog but generic; summary is technically correct but vague; severity defaults are used. |
| Poor | No diagnosis; diagnosis is unrelated to actual transcript behavior; diagnosis catalog is ignored. |

**Fixture-Checkable:** Yes (deterministic)
- Diagnosis IDs are from the defined catalog
- max_primary_diagnoses contract is respected
- Low-scoring subskills trigger appropriate diagnosis types
- Compliance-related diagnosis types are triggered by compliance flags

**SME Review Required:**
- Whether the diagnosis *ranking* matches what a trainer would prioritize
- Whether the summary language is learner-appropriate (not too technical, not too vague)

**Maps to:** C2a (diagnosis display in review UX), B2 (compliance-triggered diagnosis)

---

## Dimension 5: Compliance Signal Usefulness

**Question:** Does the compliance feedback help the learner avoid risk without being punitive?

**Definition:**
Compliance flags are rule-grounded, evidence-backed, severity-calibrated, and paired with
concrete required handling. Positive compliance behavior is also recognized.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Flags are rule-matched with evidence excerpts; severity is rule-calibrated; required_handling gives specific corrective action; positive compliance is recognized; compliance channel is visually separated from skill scores. |
| Good | Flags match rules with evidence; severity is set; required_handling is present; compliance is shown separately. |
| Functional | Flags exist but may have weak evidence; severity defaults used; handling is generic. |
| Poor | No compliance checking; compliance is collapsed into overall score; false positives dominate. |

**Fixture-Checkable:** Yes (deterministic)
- Rule matching logic is deterministic (keyword + director event based)
- Severity levels match rule definitions
- Positive AE handling is detected when both signal + escalation keywords present
- Critical/high compliance caps overall band

**SME Review Required:**
- Whether rule thresholds (keyword lists) have acceptable false-positive/false-negative rates
- Whether severity calibration matches regulatory reality
- Whether required_handling text is compliant with real SOP language

**Maps to:** B2 (compliance channel design), C2a (compliance panel in review UX)

---

## Dimension 6: Coaching Actionability

**Question:** Can the learner walk away knowing exactly what to do differently next time?

**Definition:**
Coach feedback provides concrete, observable next actions tied to specific subskills,
not vague encouragement or generic improvement advice.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Each next action names a specific observable behavior; actions are ordered by impact; urgent compliance actions are prioritized; actions reference the scenario context. |
| Good | Actions are subskill-specific ("Open with permission and a concise relevance statement"); actions are ordered; compliance-critical actions appear first. |
| Functional | Actions are category-level ("Improve opening"); ordering is by subskill priority; compliance actions may not be highlighted. |
| Poor | Actions are generic ("Practice more"); no ordering; no compliance awareness. |

**Fixture-Checkable:** Yes (deterministic)
- next_actions list is non-empty when priority_subskills exist
- max actions contract (4) is respected
- Compliance-critical actions are inserted first when high/critical flags present
- Actions reference subskill vocabulary

**SME Review Required:**
- Whether action wording would actually change learner behavior
- Whether action specificity matches learner skill level (novice vs experienced)

**Maps to:** B3 (teaching plan + coaching continuity), C2a (coaching display in review)

---

## Dimension 7: Recommendation Explainability

**Question:** Does the learner understand why this practice path was recommended?

**Definition:**
Each recommendation can answer: why this scenario, why now, what to practice, what
evidence triggered it, and when to stop repeating it.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Recommendation includes reason, evidence_source, stop_condition, reason_category, and suggested_repetition_count; the reason references specific subskill scores, trends, compliance history, and curriculum stage. |
| Good | Recommendation has reason and evidence_source; reason references subskill overlap; stop_condition is present; reason_category is set. |
| Functional | Recommendation has a reason string; evidence_source is generic; stop_condition is generic; reason_category is "skill" by default. |
| Poor | Recommendation is a scenario title with no explanation; no evidence source; no stop condition. |

**Fixture-Checkable:** Yes (deterministic)
- ScenarioRecommendation fields are all populated
- stop_condition references subskill thresholds or compliance criteria
- evidence_source references specific data (trends, scores, compliance)
- reason_category matches driver_flags logic
- Repetition avoidance: same scenario not recommended if achieved with sufficient reps

**SME Review Required:**
- Whether the recommended path actually addresses the root cause of weak performance
- Whether stop conditions are realistic for the learner's context
- Whether difficulty progression is appropriately paced

**Maps to:** B4 (practice path recommendation V2), C3 (progress UX as training plan)

---

## Dimension 8: Multi-Session Improvement Visibility

**Question:** Can the learner and trainer see progress across sessions?

**Definition:**
Progress tracking, subskill trends, continuity scores, and teaching-plan outcomes make
multi-session improvement (or stagnation) visible without requiring manual comparison.

**Quality Rubric:**

| Level | Criteria |
| --- | --- |
| Excellent | Subskill rolling averages with trend direction; teaching-plan achievement status per session; continuity score tracks carryover improvement; weakness clusters show recurring patterns; progress dashboard is filterable. |
| Good | Subskill trends (improving/stable/declining) with rolling averages; teaching-plan achievement tracked; weakness clusters identified; progress page shows session history. |
| Functional | Basic subskill score history; teaching-plan status is binary; trends are simple; progress page exists but is static. |
| Poor | No multi-session tracking; each session is isolated; no trend data. |

**Fixture-Checkable:** Partially (deterministic)
- continuity_channel is present in review payload
- teaching_plan_achievement has valid status and counts
- Weakness clusters aggregate correctly across history items
- Rolling averages are computed correctly
- Trend direction logic is deterministic

**SME Review Required:**
- Whether trend sensitivity is appropriate (not too noisy, not too laggy)
- Whether the improvement narrative is motivating rather than discouraging
- Whether the dashboard layout supports trainer decision-making

**Maps to:** B3 (continuity tracking), C3 (progress UX), B4 (recommendation uses trend data)

---

## Dimension Classification Summary

| Dimension | Fixture-Checkable | SME Review Needed |
| --- | --- | --- |
| 1. Scenario Realism | Constraint enforcement, event variety | Authenticity of persona tone, difficulty calibration |
| 2. Turn Guidance Specificity | Event taxonomy, phase tracking, hint presence | Pedagogical timing, event granularity |
| 3. Evidence Quality | Turn references, excerpt presence, tag vocabulary | Evidence relevance, excerpt fairness |
| 4. Diagnosis Clarity | Catalog membership, count contract, trigger logic | Ranking priority, learner-appropriate language |
| 5. Compliance Signal Usefulness | Rule matching, severity calibration, band capping | False positive/negative rates, regulatory alignment |
| 6. Coaching Actionability | Action presence, ordering, compliance priority | Behavior change effectiveness, skill-level fit |
| 7. Recommendation Explainability | Field population, reason logic, repetition avoidance | Root cause accuracy, pacing appropriateness |
| 8. Multi-Session Visibility | Continuity fields, trend computation, cluster logic | Trend sensitivity, motivational framing |

---

## Fixture Metadata Conventions

### Transcript Fixtures

Add optional `training_quality` block to the `expected` section of transcript fixtures:

```json
{
  "expected": {
    "overall_score_min": 70,
    "overall_score_max": 90,
    "overall_band_one_of": ["strong", "excellent"],
    "training_quality": {
      "evidence_per_subskill_min": 1,
      "require_turn_references": true,
      "diagnosis_count_min": 1,
      "diagnosis_count_max": 3,
      "compliance_detection": "none",
      "coaching_action_count_min": 2,
      "continuity_channel_present": true
    }
  }
}
```

| Field | Type | Description |
| --- | --- | --- |
| `evidence_per_subskill_min` | int | Minimum evidence items expected per scored subskill |
| `require_turn_references` | bool | Whether evidence must include turn_index |
| `diagnosis_count_min` | int | Minimum primary diagnoses expected |
| `diagnosis_count_max` | int | Maximum primary diagnoses allowed |
| `compliance_detection` | "none" \| "positive_only" \| "risk" \| "critical" | Expected compliance signal level |
| `coaching_action_count_min` | int | Minimum next_actions expected |
| `continuity_channel_present` | bool | Whether continuity data is expected |

### Recommendation Fixtures

Add optional `training_quality` block to the `expected` section:

```json
{
  "expected": {
    "recommendation_ids": ["revisit_after_prior_rejection"],
    "training_quality": {
      "explainability": "full",
      "require_stop_condition": true,
      "require_evidence_source": true,
      "require_reason_category": true,
      "max_repetition_of_same_scenario": 1,
      "forbidden_unexplained_ids": []
    }
  }
}
```

| Field | Type | Description |
| --- | --- | --- |
| `explainability` | "minimal" \| "full" | Whether recommendations need full reason/evidence/stop |
| `require_stop_condition` | bool | Whether stop_condition must be non-empty |
| `require_evidence_source` | bool | Whether evidence_source must be non-empty |
| `require_reason_category` | bool | Whether reason_category must be set |
| `max_repetition_of_same_scenario` | int | Max times same scenario can appear in top-N |
| `forbidden_unexplained_ids` | string[] | Scenario IDs that must not appear without explanation |

---

## How These Metrics Guide B1-B4

### B1: Scenario-Specific Playbooks
- **Primary dimensions:** Scenario Realism, Turn Guidance Specificity
- Playbook `expected_flow`, `common_failure_patterns`, and `recovery_moves` directly feed Director event generation.
- Asset quality gate: every scenario must have all playbook fields validated at boot (fixture-checkable).

### B2: Compliance As First-Class Training Signal
- **Primary dimensions:** Compliance Signal Usefulness, Diagnosis Clarity
- Compliance channel must remain separate from skill scoring.
- Severity-based recommendation rules: critical > high > repeated medium.
- Positive compliance handling must appear as evidence, not just risk flags.

### B3: Coaching Continuity As A Teaching Plan
- **Primary dimensions:** Coaching Actionability, Multi-Session Improvement Visibility
- Teaching plan frozen at session start, compared against review outcome.
- Continuity score tracks carryover improvement across sessions.
- Coaching actions must reference prior session weaknesses when continuity context exists.

### B4: Recommendation Policy V2
- **Primary dimensions:** Recommendation Explainability, Multi-Session Improvement Visibility
- Each recommendation must answer: why, why now, what evidence, when to stop.
- Practice path should show 2-3 steps, not a single next scenario.
- Repetition avoidance when scenario was already achieved.
- Stop conditions tied to observable subskill thresholds.

---

## Verification

```bash
# Existing fixture tests must still pass
./.venv/bin/python -m pytest apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py apps/mr-visit-jp-runtime/tests/test_recommendation_fixtures.py

# Type consistency check across evaluation core
./.venv/bin/python -c "
from evaluation_core.mr_visit_jp import build_review_payload, ReviewBuildInputs
print('evaluation_core imports OK')
"
```
