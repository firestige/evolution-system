# evolution-system

[English](README.md) | 中文

evolution-system 是 Agent Ops Ledger 的 Evolution System —— 补上整个项目 meta-recursive 闭环的最后一块拼图。它从 Evidence 获取 Workflow 在 Execution 中运行的客观事实，进行归因，并有针对性地改进 Workflow；改进后的 Workflow 再次进入 Execution 运行，产生新的客观事实，如此往复，直到客观评价达到用户为 evo 设定的目标。

其他组件在闭环中有固定分工 —— Workflow Package 定义运行什么、Execution 运行它并发出事实、Evidence 记录事实 —— 而 evolution-system 拥有反馈这一环：归因、评价与对 Workflow 的有针对性修订。

## Developer preview

本仓库是 Agent Ops Ledger 架构优先开发者预览版的一部分，适用于个人或小团队的可信本地环境。Evolution 是五个 workstream 中最新的一个，其详细设计仍落在父仓库中，尚未提供可供最终用户运行的发行版。**后续会有破坏兼容性的变更。**

## 获取源码

本仓库通常作为 [Agent Ops Ledger](https://github.com/firestige/workflow-self-recursive) 的 submodule 使用：

```sh
git clone --recurse-submodules https://github.com/firestige/workflow-self-recursive.git
```

单独克隆：

```sh
git clone https://github.com/firestige/evolution-system.git
```

## 文档

- [概念架构](https://github.com/firestige/workflow-self-recursive/blob/main/docs/agent-architecture.zh-CN.md) —— 产品目的与 meta-recursive 语境
- [Evidence System 设计](https://github.com/firestige/workflow-self-recursive/blob/main/docs/systems/evidence/evidence-system.zh-CN.md) —— 本 System 消费的客观事实来源
- [Execution System 设计](https://github.com/firestige/workflow-self-recursive/blob/main/docs/systems/execution/project-execution-system.zh-CN.md) —— 修订后的 Workflow 在哪里运行
- [Workflow 组合模型](https://github.com/firestige/workflow-self-recursive/blob/main/docs/workflow-composition-model.md) —— Workflow 修订针对的对象

## License

[Apache-2.0](LICENSE)
