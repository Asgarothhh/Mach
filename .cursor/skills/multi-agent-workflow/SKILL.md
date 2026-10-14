---
name: multi-agent-workflow
description: Coordinate Architect, Implementer, and Reviewer through a controlled plan, implementation, review, and remediation cycle.
---

# Multi-Agent Workflow

Use this workflow for non-trivial features, bug fixes, refactoring,
and changes affecting multiple modules.

## Phase 1: Architecture

1. Delegate analysis to /architect.
2. Pass the original request and constraints.
3. Wait for the complete implementation plan.
4. Verify that the plan identifies files, tests, and acceptance criteria.
5. Ask the user to resolve important ambiguities when necessary.

Do not begin implementation before the plan is ready.

## Phase 2: Implementation

1. Delegate the approved plan to /implementer.
2. Include the original requirements, plan, constraints, and acceptance criteria.
3. Require tests and actual verification results.
4. Review material deviations from the plan.

## Phase 3: Independent Review

1. Delegate the review to /reviewer after implementation.
2. Pass the original requirements, plan, changed file list, and diff.
3. Require independent findings and an explicit verdict.
4. Do not substitute the implementer's self-review for this step.

## Phase 4: Remediation

If CRITICAL or HIGH findings exist, or required acceptance criteria
remain unmet:

1. Send the findings to /implementer.
2. Request minimal, targeted fixes.
3. Require relevant tests to be rerun.
4. Request another independent review.

Allow at most two remediation cycles. If blocking defects remain,
stop and report them.

## Phase 5: Final Verification

1. Inspect the final diff.
2. Verify the acceptance criteria.
3. Verify available test evidence.
4. Report changed files, test results, review verdict, and limitations.
5. Obtain approval before commits, pushes, deployments, or destructive actions.

## Parallelism

Parallelize independent research and read-only reviews when useful.
Do not run multiple writers against the same files concurrently
unless an explicit isolation and integration strategy exists.

## Small tasks

For trivial changes, avoid unnecessary orchestration overhead.

## Automatic Complexity Routing

The user provides a complete specification.
Do not ask the user to manually split it into simple and complex tasks.

1. Use the default cost-efficient model to analyze the specification.
2. Decompose the specification into atomic, verifiable tasks.
3. Build a dependency graph and identify tasks that can be executed independently.
4. Assign each task a risk level: LOW, MEDIUM, or HIGH.
5. Record the reasons for each risk classification.

HIGH risk includes:
- Authentication, authorization, or security boundaries.
- Database schema changes and potentially destructive migrations.
- Cross-module architectural changes.
- Concurrency and data consistency.
- Critical business logic or complex algorithms.
- Contradictions between the specification and actual code.
- High-impact backward compatibility risks.

Routing:
- LOW: use the default Architect, Implementer, and Reviewer.
- MEDIUM: use the default Implementer and request additional targeted analysis.
- HIGH: invoke the deep-architect agent before implementation and the
  deep-reviewer agent after implementation.

Use stronger models only for the tasks that meet the HIGH-risk criteria.
Do not escalate merely because a task affects many files.

Before implementation, consolidate the plans into one dependency-aware
execution plan.

After implementation, verify all acceptance criteria against the original
specification, including requirements that span multiple tasks.

Never silently skip a requirement because it was not included in an
individual task.