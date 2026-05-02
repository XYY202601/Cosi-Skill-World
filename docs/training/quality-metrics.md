# Training Quality Metrics Definition

This document defines the measurable training-quality signals for the COSI Skill World MR training loop. These metrics ensure that learners receive clear, actionable, and trustworthy feedback.

## Training Quality Dimensions

| Dimension | Description | Check Method |
| --- | --- | --- |
| **Scenario Realism** | How closely the scenario and persona behavior mimic a real MR visit. | SME Review / Fixtures |
| **Turn Guidance Specificity** | How concrete and helpful the Director's turn-level guidance is. | Fixtures |
| **Evidence Quality** | The accuracy and relevance of the transcript turn references linked to subskill scores. | Deterministic Fixtures |
| **Diagnosis Clarity** | How well the Judge's diagnosis explains the reason for a specific score. | Fixtures / SME Review |
| **Compliance Signal Usefulness** | Whether compliance risks are correctly identified and given appropriate severity. | Deterministic Fixtures |
| **Coaching Actionability** | How concrete and achievable the Coach's next-action suggestions are. | SME Review |
| **Recommendation Explainability** | Whether the "why" and "what to practice next" are clear and evidence-backed. | Deterministic Fixtures |
| **Multi-Session Improvement** | The visibility of skill growth trends across multiple sessions. | Deterministic Fixtures |

## Quality Rubrics

### 1. Evidence Quality (Deterministic)
- **High (3)**: Every diagnosis points to at least one specific, relevant transcript turn.
- **Medium (2)**: Evidence is provided but is generic or occasionally misaligned.
- **Low (1)**: Diagnosis has no turn references or points to irrelevant turns.

### 2. Diagnosis Clarity
- **High (3)**: Diagnosis identifies a specific behavior, explains why it matters, and references evidence.
- **Medium (2)**: Diagnosis identifies a behavior but lacks deep explanation.
- **Low (1)**: Diagnosis is a generic summary of the subskill.

### 3. Coaching Actionability
- **High (3)**: Coach suggests a specific, observable behavior to try in the next session (e.g., "Ask about the endpoint of the trial X").
- **Medium (2)**: Coach suggests a general area of improvement (e.g., "Improve your profiling").
- **Low (1)**: Coaching is vague or repetitive.

## Implementation Guidelines

- **B1 (Playbooks)**: Use playbooks to set the "gold standard" for expected flow and evidence.
- **B2 (Compliance)**: Use deterministic rules to verify compliance signal accuracy.
- **B3 (Continuity)**: Measure quality by comparing session outcomes against frozen teaching plans.
- **B4 (Recommendations)**: Use fixture-based regression tests to assert explainability fields exist and are populated.

## Verification

### Deterministic Fixtures
Use `apps/mr-visit-jp-runtime/tests/test_transcript_fixture_evaluation.py` and `test_recommendation_fixtures.py` to assert that:
- Evidence linkage exists.
- Compliance flags match expected severity.
- Recommendation reasons are non-empty and categorized.

### SME Review
Periodically export review samples for human calibration using the schema defined in Phase H4.
