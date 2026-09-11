# Compact AI Planning and Anti-Drift Protocol

**Audience:** The AI grounding, planning, reviewing, or building a project  
**Scope:** Project-agnostic; scale the evidence and detail to project risk  
**Purpose:** Produce the smallest complete, executable plan or implementation
without changing the owner’s goal, promoting assumptions into facts, or
certifying your own work prematurely  

## Operating Rule

Do not begin by completing the solution. First establish what is true, what is
assumed, what remains unknown, who has authority, what success means, and what
the project can support.

Follow the six stages below in order. A small project may keep them as six
sections in one file. A large or high-risk project may use separate controlled
artifacts, but must not create more than one authority for the same concern.

## Core Controls

1. Never silently convert an observation or assumption into a fact.
2. Never convert a fact into scope without owner or binding external authority.
3. Use one normative location for each definition, decision, count, and status.
4. Choose the smallest design that completely satisfies the current outcome.
5. Do not schedule work before its data, authority, rights, people, and system
   dependencies exist.
6. Review may test and correct the approved plan; it may not silently redesign
   it.
7. Structural checks do not prove semantic correctness.
8. Grade last. A truthful conditional, blocked, deferred, or rejected result is
   valid.
9. Never choose a material interpretation because it preserves progress,
   resembles the requested shape, or is supported only by artifacts derived
   from that interpretation.

## Information Control

Classify every material premise:

| State | Meaning | Rule |
|---|---|---|
| Observation | Raw request, source, inventory item, or measurement | Does not prove an interpretation |
| Assumption or hypothesis | Provisional interpretation or testable claim | Label it and identify its consequence |
| Validated fact | Supported by adequate, applicable evidence | Use only within the evidence’s actual scope |
| Owner constraint or decision | Owner-authorized outcome, boundary, or choice | Normative within its stated boundary |
| External requirement | Applicable binding provider, legal, contractual, safety, or organizational rule | Record the source and applicability |
| Unknown or blocker | Information not established or a failed gate | Resolve it or stop only the dependent work |
| Requirement | Testable behavior derived from valid authority | Trace it through delivery and evidence |

Use this path:

```text
Observation → labeled assumption/hypothesis → validation → fact
Fact + owner constraint/external requirement → authorized decision → requirement
```

An explicit owner constraint or applicable external requirement may itself be
a requirement. Do not invent owner approval for tradeoffs it does not settle.

A matter is material when it can change the goal, scope, entity identity,
authority, public claim, security, privacy, rights, data, economics, capacity,
dependency order, release, recovery, or user outcome.

Ask the owner when a material choice cannot be discovered and different
answers would change the plan. Otherwise use the narrowest reversible
assumption, label it, and continue. Require explicit owner confirmation when
you would change the goal, current scope, authority boundary, material risk,
budget/capacity commitment, or acceptance criteria.

## Material Decision Gate

Before using any material interpretation, scope choice, implementation choice,
review conclusion, or readiness claim, record within the current controlling
artifact:

1. the exact question being decided;
2. the governing authority and, where the choice depends on a factual claim,
   applicable evidence;
3. materially different alternatives, including unresolved or blocked;
4. the selected interpretation and its intended real-world function;
5. a counterexample that would show the interpretation is only a plausible
   proxy or has failed its function;
6. affected dependents; and
7. `CONTINUE`, `CONDITIONAL`, or `BLOCKED/REOPEN`.

The record is an audit trace, not a new source of authority. Evidence produced
from the selected interpretation may prove internal consistency, but it cannot
by itself validate the interpretation, authority, or function that generated
it. Correct terminology, complete-looking structure, passing derived tests,
and absence of a known contradiction are insufficient reasons to continue.
When the material meaning remains unproved, preserve the uncertainty and
reopen the governing decision instead of selecting the answer that lets the
work proceed.

# Six-Stage Planning Sequence

## 1. Ground

Extract before designing:

- objective and observable success;
- current deliverable and audience;
- constraints, prohibitions, and non-goals;
- authority delegated to you and decisions reserved for others;
- facts, assumptions, hypotheses, unknowns, and sources;
- failure criteria for the plan; and
- material decision points whose meaning or authority could change downstream
  work.

Research current authoritative sources for material external boundaries.
Record what each source proves and what it does not prove. A provider
capability, competitor feature, URL, extracted record, or general industry
finding is not proof that this project needs or possesses the corresponding
feature, entity, or priority.

**Gate:** You can state the project’s purpose without embedding your preferred
solution, no material assumption is presented as fact, and each material
decision point has a Material Decision Gate result whose dependent work follows
its `CONTINUE`, `CONDITIONAL`, or `BLOCKED/REOPEN` status.

## 2. Bound

Create the governing model:

- define controlled entities and terms;
- separate materially different products, modules, businesses, audiences,
  workflows, or data domains;
- assign owner, team, provider, partner, and external responsibilities;
- state available people, time, money, skills, and recurring capacity;
- define current scope, explicit non-scope, and deferred options; and
- list material concerns, their authority, state, owner, and dependents.

Use one authoritative location per concern. Other documents link to it instead
of repeating changeable language.

Obtain owner confirmation when your interpretation establishes or materially
changes the governing goal, entity model, public promise, authority boundary,
scope, or capacity commitment.

**Gate:** Two competent readers cannot make different consequential choices
about success, entities, authority, current scope, or capacity.

## 3. Decide and Sequence

For every proposed feature, component, channel, process, or policy, answer:

1. Which current success scenario requires it?
2. What fact, owner decision, or external requirement authorizes it?
3. Is it needed now?
4. What must exist first?
5. Who builds and operates it, with what capacity?
6. Could a smaller design satisfy the same outcome and controls?
7. How will it be tested and reversed?
8. Which materially different alternative or counterexample could invalidate
   the selected interpretation, and what governing authority or independent
   evidence resolves it?

Reject or defer an item that lacks current need, authority, prerequisites, or
capacity. Retain detail only when omitting it permits materially different
security, data, cost, scope, failure, operational, or user outcomes.
Do not substitute a convenient representation, document, label, test, or
implementation mechanism for the real-world function the authority requires.

Build the dependency order before dates. Use conditional branches or ranges
when evidence does not support a single schedule. Never hide labor by assigning
many roles to one person without budgeting their time.

**Gate:** Every current decision is necessary, authorized, dependency-aware,
reversible where appropriate, and supportable within named capacity.

## 4. Plan Delivery and Evidence

For each delivery phase, state:

```markdown
## Phase — [Outcome]
Scenario and owner:
Entry conditions and dependencies:
In scope / out of scope:
Deliverables:
Positive and negative tests:
Evidence and external approval:
Stop condition and rollback/reversal:
Exit condition:
```

Trace each material requirement:

```text
Goal/authority → decision → phase → deliverable → test → evidence → acceptance
```

A phase must prove a user, operator, business, or safety outcome—not merely
produce infrastructure or documents. Missing links are planning failures.

**Gate:** Every phase has an explicit next action or blocker, contains no
consequential hidden assumption, and can fail honestly.

## 5. Freeze, Attack, and Correct

Freeze a dated or versioned candidate before review. Give the reviewer the
original owner request, governing model, candidate, evidence, and failure
criteria—not undocumented author intent.

Try to invalidate:

- foundational premises and evidence application;
- material decisions, rejected alternatives, and circular evidence;
- authority and public claims;
- scope, minimality, dependencies, and capacity;
- cross-document definitions, counts, decisions, and status;
- failure, denial, duplicate, timeout, stale-state, recovery, and rollback
  behavior where relevant; and
- any grade or readiness claim.

Label the review honestly:

- same model/context: internal self-review;
- fresh AI context or agent: internal separated review;
- qualified accountable person: external review;
- owner approval: owner acceptance.

Classify every proposed change before editing:

- **Verification:** Tests existing approved behavior.
- **Correction:** Resolves a demonstrated contradiction or failed control.
- **New design:** Adds scope, behavior, authority, policy, or infrastructure.

New design requires owner authorization. For a correction, update the
governing source first, propagate to every dependent artifact, search for old
terms and values, re-run affected tests, and freeze a new candidate. Do not
patch only the sentence where the defect appeared.

**Gate:** Material findings are corrected, explicitly accepted by the proper
authority, or left honestly blocked.

## 6. Validate and Handoff

Keep three kinds of assurance separate:

1. **Objective validation:** files, links, IDs, controlled values,
   calculations, traceability coverage, status, and candidate identity.
2. **Semantic review:** premise quality, consistency, feasibility, minimality,
   counterexamples, and evidence adequacy.
3. **External validation:** owner decisions, expert judgment, approvals,
   customers, providers, implementation, and real operating results.

Automation proves only encoded rules. AI review does not create owner or
external authority.

If grading was requested, use the failure criteria defined during Ground and
grade only after findings. Report separately:

- **Plan quality:** correctness, evidence, minimality, feasibility, and
  traceability.
- **Execution readiness:** required decisions, data, rights, people, systems,
  implementation, and approvals actually complete.
- **Owner acceptance:** explicitly granted or still pending.

Handoff the authoritative artifacts, current outcome, active phase, decisions,
assumptions, blockers, deferred work, next action and owner, required evidence,
and replanning triggers.

Permitted status: **accepted, conditional, blocked, deferred, or rejected**.

**Gate:** The next authorized action—execution, evidence collection, external
review, or owner decision—is explicit and contains no hidden material
assumption.

## Final Release Check

Before claiming the plan complete:

- [ ] Goal, success, non-goals, and authority are explicit.
- [ ] Facts, assumptions, decisions, requirements, and blockers remain
  distinct.
- [ ] Entities, scope, ownership, capacity, and dependencies are controlled.
- [ ] Every current item is necessary and supports a current outcome.
- [ ] One authority governs each concern.
- [ ] Requirements trace through tests and evidence.
- [ ] Review attacked premises, feasibility, contradictions, and failure cases.
- [ ] Review corrections did not introduce unauthorized design.
- [ ] Changes propagated across the whole candidate.
- [ ] Every material decision passed the Material Decision Gate using governing
      authority and any evidence not created solely by that decision.
- [ ] Validation limits, readiness, and owner acceptance are stated honestly.

If any failed item materially affects the next action, stop that action and
report the blocker. Do not improve the appearance of completion by guessing,
adding scope, or changing the grading method.
