# evolution-system

[English](README.md) | 中文

evolution-system 是 workflow-self-recursive 的无状态 Metric Result 服务。它把
`EvaluationSelection` 解析到 Evidence，绑定 owner 已批准的 Evaluation Catalog 2.0 评审候选，并返回
`ResolvedEvaluationContext` receipt 与权威 Metric Results。compare 请求分别携带左右
selection；两侧结果和所有兼容 delta 均由 Evolution 计算。

Evolution 只通过带版本的 Evidence Query API 读取 Facts 与 recorded Traces。它不拥有
Evidence、不持久化数据库、不回写 Metric Result，也不推断未记录因果。BI 是展示客户
端，不计算 published metrics。

Iteration 5 明确不包含 Workflow 编辑、改进应用、AI 归因和 meta-recursive loop；它们是
后续产品范围，不是本服务基线的职责。

## 开发者预览

当前候选提供封闭、无副作用的 compute 边界、精确的 12-coordinate registry、12/12
candidate metric 的 pure formula，以及 Task membership、Manifest projection、Facts 和
recorded Trace nodes 的 typed reader/resolver。Delivery、operational、Task、Role/model、
Role-template 与 exact reported-Usage calculator input 在关联缺失时 fail closed。

端到端 compute orchestration，以及 Usage Event native Span identity 的物理 projection，仍是
Wave5 未完成工作。该 exact call binding 尚未公开时，call-scoped Usage availability/cost
只产生 missing coverage；绝不按 Delivery identity、timestamp、arrival order 或文本关联。
2.0 Catalog 仍是 review candidate，**正式发布前仍可能发生破坏兼容性的变更。**

## 开发

支持 Python 3.13 与 3.14。依赖锁定和构建由 [uv](https://docs.astral.sh/uv/) 管理；
本地命令默认使用 Python 3.14。

```sh
make sync    # 安装精确锁定的环境
make format  # 格式化 Python 源码与测试
make lint    # 格式、Ruff 与严格 mypy
make unit    # 运行无需外部服务的确定性测试
make build   # 构建 wheel 与源码包
make check   # 运行非容器验收门
```

## 获取源码

本仓库通常作为 [workflow-self-recursive](https://github.com/firestige/workflow-self-recursive)
的 submodule 使用：

```sh
git clone --recurse-submodules https://github.com/firestige/workflow-self-recursive.git
```

单独克隆：

```sh
git clone https://github.com/firestige/evolution-system.git
```

## 文档

- [Evolution System 设计](https://github.com/firestige/workflow-self-recursive/blob/main/docs/systems/evolution/evolution-system.zh-CN.md)
- [Metric Catalog 2.0 评审候选](https://github.com/firestige/workflow-self-recursive/blob/main/docs/contracts/evaluation/metric-catalog-2-candidate.zh-CN.md)
- [Evidence Query Contract](https://github.com/firestige/workflow-self-recursive/blob/main/docs/contracts/evidence-query/evidence-query.zh-CN.md)

## License

[Apache-2.0](LICENSE)
