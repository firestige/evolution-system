# evolution-system

English | [中文](README.zh-CN.md)

evolution-system is the Evolution System of Agent Ops Ledger — the piece that closes the project's meta-recursive loop. It reads the objective facts Evidence recorded about how a Workflow ran in Execution, attributes outcomes to their causes, and applies targeted improvements to the Workflow. The revised Workflow then runs in Execution again to produce new objective facts, and the loop repeats until the objective evaluation reaches the goal the user set for evolution.

The other components split the loop into fixed roles — Workflow Packages define what runs, Execution runs it and emits facts, Evidence records them — while evolution-system owns the feedback leg: attribution, evaluation, and the targeted revision of Workflows.

## Developer preview

This repository is part of Agent Ops Ledger's architecture-first developer preview for trusted local use by individuals and small teams. The Evolution workstream is the newest of the five, and its detailed design still lands in the parent repository; it does not yet provide a runnable end-user release. **THERE WILL BE COMPATIBILITY-BREAKING CHANGES.**

## Get the source

This repository is normally consumed as a submodule of [Agent Ops Ledger](https://github.com/firestige/workflow-self-recursive):

```sh
git clone --recurse-submodules https://github.com/firestige/workflow-self-recursive.git
```

To clone it standalone:

```sh
git clone https://github.com/firestige/evolution-system.git
```

## Documentation

- [Conceptual architecture](https://github.com/firestige/workflow-self-recursive/blob/main/docs/agent-architecture.md) — product purpose and the meta-recursive context
- [Evidence System design](https://github.com/firestige/workflow-self-recursive/blob/main/docs/systems/evidence/evidence-system.md) — the objective facts this System consumes
- [Execution System design](https://github.com/firestige/workflow-self-recursive/blob/main/docs/systems/execution/project-execution-system.md) — where revised Workflows run
- [Workflow composition model](https://github.com/firestige/workflow-self-recursive/blob/main/docs/workflow-composition-model.md) — what a Workflow revision targets

## License

[Apache-2.0](LICENSE)
