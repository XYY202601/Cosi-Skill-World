# skill-registry

Skill package registration and discovery layer.

## Purpose

Allow the platform orchestrator to discover and route to domain skill packages.

## Concepts

A skill package is not just a prompt.
It is a domain runtime contract.

Registry vocabulary:

- `skill`: a domain package that owns a runtime contract and training assets
- `capability`: a grouped slice of skill behavior such as scenario catalog,
  practice session, review, or progress
- `action`: one externally routable operation with a method and runtime path
- `runtime`: the target service metadata used by Hermes to proxy requests
- `routing`: whether a skill is the default target for unscoped routes
- `registration`: whether a manifest should be discoverable now or kept as an
  in-repo spike until its runtime contract is ready

## Example

`mr_visit_jp` exposes capabilities:

- `scenario_catalog`
- `practice_session`
- `review`
- `progress`

And actions:

- `list_scenarios`
- `get_evaluation_gates`
- `start_session`
- `get_session`
- `send_turn`
- `finish_session`
- `get_review`
- `get_session_events`
- `get_progress_snapshot`

Reserved optional action ids for future runtimes:

- `get_curriculum`
- `get_organization_reports`

## Responsibilities

- register skill packages
- expose metadata
- resolve available actions
- validate skill package manifests
- build runtime paths from action ids plus path params
- identify the default skill for unscoped Hermes routes

## Non-Goals

This package does not execute business logic.
It is a registry, not a runtime.
It does not score sessions, generate reviews, or own HTTP handlers.
