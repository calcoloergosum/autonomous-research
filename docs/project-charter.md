# Project charter — Autonomous Research Framework

**Owner:** Human project owner.  
**Phase:** Build the minimal execution substrate (VS-001).  
**Project objective:** Build a framework that, for a human-defined final research question, can autonomously generate and prioritize research tasks, estimate their final impact and evidence-acquisition cost, execute approved experiments with bounded resources, collect evidence, revise intermediate baselines, and reallocate efforts as predictions change.

## Invariants

1. The final research question, success criteria, and safety/resource permissions belong to a human. The AI cannot change them.
2. The candidate research portfolio is open-ended: the system must not require a fixed list of arms, candidates, or trials.
3. Intermediate evidence is used to decide what to do next and need not be publication-quality. A final answer must satisfy independently defined strong evidence criteria; weak exploratory evidence is not silently promoted to proof.
4. Impact and cost are **predictions with uncertainty**, updated from observed experiments. Execution history is preserved.
5. A baseline revision may reorganize subordinate tasks but must not alter the final question or discard past observations.
6. LLM, local compute, and human capacity are separately constrained; human availability may be time-window dependent. Maximum parallelism and strict pipelines are not assumed optimal.
7. Any claim of research progress must trace to observed evidence. Unexecuted plans are not results.

## Long-term outcomes (not VS-001 deliverables)

- Persistent graph/portfolio of questions, hypotheses, experiments, evidence, dependencies, and baseline revisions.
- Impact / cost estimation with empirical calibration and cross-task generalization.
- Adaptive allocation between exploration and exploitation, with separate resource scheduling.
- Human task queue and approvals that respect human availability.
- Research-policy evaluation on actual runs and simulated environments, including time-to-sufficient-evidence and useful results per budget.

## Initial vertical slice boundary

VS-001 implements **only** a single-study, single-host local experiment lifecycle with persistence, provenance, modest failure recovery, and test coverage. It does not implement autonomous planning or the final science task. See `tasks/VS-001.md`.

## Clarifications deliberately not invented

- No actual ultimate research question or final evidence requirement has been supplied. These are required to run a real study and must come from a human.
- Budget, human working hours, API credentials, hardware configuration, and external spending permissions are not yet specified.
- VS-001 uses the demo fixture solely to verify plumbing; it is not a substitute for these choices.
