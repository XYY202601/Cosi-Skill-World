# mr_visit_jp

Domain bundle for Japanese MR visit training.

## Purpose

This directory contains all domain-specific assets for the first training track.

## Included

- skill manifest
- scenario templates
- doctor persona assets
- agent prompts
- openai-compatible prompt contracts (`prompts/*/openai_compat.yaml`)
- scoring rubrics
- compliance rules
- seed assets

## Domain Focus

Japanese MR visit training is modeled as:
- professional information delivery
- need discovery
- objection handling
- compliant communication
- effective closing and follow-up

It is not modeled as generic closing-oriented sales.

## Core Subskills

- preparation
- opening
- profiling
- scientific_delivery
- need_discovery
- objection_handling
- closing_followup

## Rule

Everything domain-specific belongs here.
Cross-domain abstractions should stay in `packages/` or `services/`.
