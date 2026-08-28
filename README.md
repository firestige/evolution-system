# evolution-system

English | [中文](README.zh-CN.md)

evolution-system is workflow-self-recursive's stateless Metric Result service. It
resolves an `EvaluationSelection` against Evidence, binds the owner-approved
Evaluation Catalog 2.0 review candidate, and returns a `ResolvedEvaluationContext` receipt together
with authoritative Metric Results. Compare requests contain independent left and
right selections; Evolution computes both sides and every compatible delta.

Evolution reads Facts and recorded Traces through the versioned Evidence Query
API. It does not own Evidence, persist a database, write Metric Results back, or
infer unrecorded causality. BI is its presentation client and does not calculate
published metrics.

Iteration 5 deliberately excludes Workflow editing, improvement application, AI
attribution, and the meta-recursive loop. Those remain later product scope rather
than responsibilities of this service baseline.

## Developer preview

The current candidate exposes a closed, side-effect-free compute boundary, an
exact 12-coordinate registry, pure formulas for all 12 candidate metrics, typed
Evidence/Workflow resolvers, and end-to-end SINGLE/FULL_COMPARE/PARTIAL_COMPARE
orchestration. Every successful side returns the exact 12 Metric Results and a
receipt-bound resolved read set; metric-level holes do not fail the other results.

The current public Fact projection still does not expose a Usage Event's native
Span identity or a recorded repair-to-Role attribution. Those call-/Role-scoped
inputs therefore produce explicit missing coverage; they are never joined by
Delivery identity, timestamp, arrival order, or text. The 2.0 Catalog remains a
review candidate, so **compatibility-breaking changes remain possible before
publication.**

## Development

Python 3.13 and 3.14 are supported. Dependencies and builds are locked with
[uv](https://docs.astral.sh/uv/); local commands default to Python 3.14.

```sh
make sync    # install the exact locked environment
make format  # format Python sources and tests
make lint    # formatting, Ruff, and strict mypy
make unit    # deterministic tests without external services
make build   # build wheel and source distribution
make check   # run the non-container acceptance gate
```

## Get the source

This repository is normally consumed as a submodule of
[workflow-self-recursive](https://github.com/firestige/workflow-self-recursive):

```sh
git clone --recurse-submodules https://github.com/firestige/workflow-self-recursive.git
```

To clone it standalone:

```sh
git clone https://github.com/firestige/evolution-system.git
```

## Documentation

- [Evolution System design](https://github.com/firestige/workflow-self-recursive/blob/main/docs/systems/evolution/evolution-system.md)
- [Metric Catalog 2.0 review candidate](https://github.com/firestige/workflow-self-recursive/blob/main/docs/contracts/evaluation/metric-catalog-2-candidate.md)
- [Evidence Query Contract](https://github.com/firestige/workflow-self-recursive/blob/main/docs/contracts/evidence-query/evidence-query.md)

## License

[Apache-2.0](LICENSE)
