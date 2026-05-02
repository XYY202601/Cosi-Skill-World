# recommendation-service

Rule-first next-step recommendation service.

## Purpose

Recommend what the learner should practice next.

## Recommendation Sources

- latest diagnosis
- repeated weakness patterns
- recent scenario history
- subskill trends
- current training track

## Current Strategy

Alpha uses rule-first recommendation.
Model-assisted recommendation may be added later.

Current production signals now include:
- latest diagnosis
- rolling subskill averages
- longer-window trend direction
- recurring weak-subskill clusters across recent sessions
- recent scenario repetition avoidance

## Example

If `opening` is weak:
- recommend short-time busy-doctor scenarios

If `objection_handling` is weak:
- recommend skeptical doctor scenarios
