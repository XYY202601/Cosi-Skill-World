# evaluation-core

Core evaluation normalization layer.

## Purpose

Turn AI-generated assessment into stable, structured outputs.

## Responsibilities

- validate score ranges
- normalize diagnoses
- normalize compliance flags
- enforce judge / coach / compliance schema gates
- apply model-first artifact selection with rule fallback
- calculate weighted scores
- prepare recommendation inputs

## Why It Exists

Judging should not be a free-form model-only output.
This package enforces consistency and stability.

## First Domain Support

- `mr_visit_jp`
