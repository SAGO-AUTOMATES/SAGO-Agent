# Architecture Decision Records (ADR)

## ADR-001: Keep enhancements additive and feature-flagged
All changes are opt-in via env/config flags defaulting to current behavior to avoid breaking TUI/features.

## ADR-002: Prefer AST/structure tools over whole-file reads
Use repo_map/project_graph/read_function/ast_edit before read_file/edit_file to reduce context poisoning.

## ADR-003: Multi-pass verification
Verifier may suggest corrections; execution paths can opt into correction passes via env flags.

## ADR-004: Event propagation via message bus
Executor lifecycle events (task_started/tool_executed/task_completed/task_cancelled) are
published to `orchestrator.message_bus` only when `SAGO_BUS_EVENTS=1`. Default-off keeps
behavior unchanged; subscribers register handlers on the `executor` channel.

## ADR-005: Semantic routing is opt-in
Embedding-similarity boosting of agent delegation requires `SAGO_SEMANTIC_ROUTING=1`.
Boosts are relative to the candidate mean to keep hash-vector fallbacks from ranking
everything equally.

## ADR-006: Dynamic replanning is opt-in
`SAGO_REPLAN=1` gives failed LLM steps one feedback round (error text appended to the
task) inside the workflow engine. One round per step; result recorded on the step.
Zero effect without the flag.