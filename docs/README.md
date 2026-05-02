# docs

Project documentation.

## Goal

Document architecture, product logic, API contracts, prompt contracts, and design decisions.

## Key Sections

- `architecture/`
- `api/`
- `product/`
- `prompts/`
- `adrs/`

Start with `architecture/reference-mapping.md` when a task uses
`references/hermes-agent` or `references/deeptutor`.
Use `architecture/reference-adoption-template.md` when code is copied or closely adapted.
Use `architecture/skill-registry-contract.md` for shared skill/capability/action vocabulary.
Use `architecture/second-domain-spike-review.md` for the current non-MR domain
spike state and remaining gaps before registration.

## Rule

If a module boundary matters, document it here.
If a design decision is likely to be revisited, record an ADR.
