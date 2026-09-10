# Agentic AI

How the agent layer is built, what each agent may do, and — more importantly —
what none of them can do.

---

## The one rule

> **Agents orchestrate. Tools compute.**

An agent decides *which* tool to call and *in what order*, passes results
between them, reconciles what comes back including disagreement and absence, and
says what it found. It does not compute an operational number. Every figure in
an agent's output came out of a tool, and every tool names the deterministic
module that produced it.

That is enforced rather than encouraged:

- `ToolSpec.computed_by` is required, and a test fails any tool that ships
  without one.
- Every `Finding` carries `source_tool`, and a test asserts that each one names
  a tool the agent is actually allowed to call.
- An agent that reaches for a tool it did not declare gets a `DENIED` entry in
  its own trace rather than a result.

---

## The access boundary

Four levels, checked at call time in `ToolRegistry.call`:

| Level | Meaning | Side effects |
|---|---|---|
| `READ` | Observe | none |
| `SIMULATE` | Run a model or a what-if | none |
| `PROPOSE` | Create a draft for a human to review | a pending record |
| `EXECUTE` | Act | real |

Two independent gates protect EXECUTE:

1. **The caller's ceiling.** Every agent — including the orchestrator — is
   constructed with `max_access=PROPOSE` at most. An EXECUTE tool is not merely
   refused, it is unreachable, and over MCP at the default ceiling it is not even
   listed.

2. **The approval context.** An EXECUTE call requires an `ApprovalContext` whose
   `human_verified` flag is true. That flag is set only by
   `approval_from_session`, which requires an authenticated session id. An
   agent constructing the dataclass itself gets `human_verified=False` and the
   call is refused.

```python
# What an agent can build — refused
ApprovalContext(actor="agent", actor_role="ISSUER")   # human_verified = False

# What only an API route holding a session can build
approval_from_session(actor="S. Iyer", actor_role="ISSUER", session_id=...)
```

There is deliberately no path from agent output to `approval_from_session`. An
agent that wants something executed produces a PROPOSE draft and a person
approves it through the interface.

---

## The agents

Each declares a purpose, the tools it may call, its ceiling, and its failure
modes. The declaration is validated against the registry at construction, so an
agent naming a tool that does not exist fails at startup rather than at 3 a.m.

### Command agent (orchestrator)

Routes a question to the specialists that can answer it. The plan comes from
matching the request against declared intents; each intent names its agents and
the order they run in, so a run is reproducible and auditable.

Agents run **in sequence**, and each one's output is fed into the next request's
context. That is what makes it a chain rather than a fan-out: the fleet agent
needs the events Global Eye found, and the route agent needs the vessel the fleet
agent decided mattered most.

The chain also *narrows*. After the fleet agent runs, `_carry_subject` sets the
request's vessel to the worst-exposed vessel that can still act on the answer —
a vessel already inside the risk area has no routing decision left, so scoring
its alternatives would be effort spent on nothing.

| Intent | Agents | Critic? |
|---|---|---|
| `fleet_exposure` | global_eye → fleet → route | yes |
| `port_advisory` | port_twin → weather → advisory | yes |
| `port_state` | port_twin → weather | no |
| `cargo_connection` | cargo → port_twin | no |
| `scenario` | scenario → global_eye | no |
| `learning` | outcome | no |
| `weather` | weather | no |
| `global_events` | global_eye | no |

### Specialists

| Agent | Tools | Ceiling |
|---|---|---|
| `global_eye` | `global_eye.events`, `global_eye.exposure` | READ |
| `weather` | `weather.get` | READ |
| `fleet` | `company.fleet`, `company.risk` | READ |
| `port_twin` | `ports.get`, `port_twin.state`, `port_twin.simulate` | SIMULATE |
| `route` | `routing.optimize` | SIMULATE |
| `cargo` | `cargo.opportunities`, `cargo.optimize` | SIMULATE |
| `scenario` | `scenarios.simulate` | SIMULATE |
| `outcome` | `learning.outcomes`, `learning.reliability`, `learning.policies` | READ |
| `advisory` | `advisories.list`, `advisories.draft`, `port_twin.simulate` | PROPOSE |

The advisory agent holds the highest ceiling in the system and it is still
PROPOSE. It will also refuse to draft anything without a computed recommendation
in its context — it will not invent a number to put in front of a master.

---

## Confidence

Confidence propagates; it is never asserted.

```python
propagate_confidence([0.9, 0.9, 0.3])  # 0.30, not 0.70
```

The result is bounded above by the **minimum** input, because a chain is as weak
as its weakest link and a mean would let three confident reads paper over one
stale one. Each failed tool call costs a further 0.82× and each unfilled gap a
further 0.9×. No evidence at all returns `None`, which the UI must render as
unknown rather than as zero.

Per-tool confidence reflects what produced the answer: a deterministic model over
exported artefacts is trusted more than a heuristic over a news feed, and the
table in `specialists.py` says so rather than treating every source as equal.

---

## The Critic

Every high-impact recommendation passes through the Critic before a human sees
it. Its job is narrow and it matters that it stays narrow: it checks whether a
recommendation is **supported, safe and consistent** with the evidence that
produced it. It does not re-derive the recommendation, and it cannot overrule a
mathematical constraint.

| Check | Severity | Fails when |
|---|---|---|
| `supported_by_evidence` | blocking | No tool produced the numbers |
| `physical_envelope` | blocking | Speed outside 6–24 kn, or an arrival shift over 48 h |
| `action_still_available` | blocking | Diverting a vessel already in the risk area; a deadline that has passed |
| `no_constraint_violations` | blocking | The producing simulation reported a hard-constraint breach |
| `confidence_actionable` | qualifying | Model confidence below 0.35 |
| `evidence_fresh` | qualifying | The driving artefact is older than 18 h |
| `impact_quantified` | qualifying | No measurable benefit claimed |
| `contributors_agree` | qualifying | A contributing agent was blocked or ran with gaps |

One blocking failure rejects. Qualifying failures modify: the recommendation is
still actionable but something must be shown alongside it.

**The Critic can only lower confidence, never raise it.** Each qualifying
failure multiplies it by 0.85. A reviewer's job is to find reasons to trust
something less.

**The Critic reports hard-constraint violations; it never relaxes them.** Where
the simulator has already said a berth cannot take a hull, no amount of reasoning
here changes that.

**Disagreement reaches the operator as disagreement.** Two agents reaching
opposite conclusions — the weather agent sees a clearing window, the fleet agent
sees a closing deadline — is a real and common state, and it is reported rather
than averaged into false consensus.

---

## Where a language model fits

Two points, both optional:

1. **Intent classification.** `classify_intent` accepts a classifier callable.
   Its answer is validated against the known intents — a model returning
   something unrecognised is ignored, and a classifier that throws falls back to
   keyword matching with a warning.

2. **Narration.** The summary is assembled from the agents' own summaries, each
   built from findings that name their source tool. A model may render that more
   fluently, but it cannot introduce a number the trace does not contain.

The classifier is given no tools and no approval context, so the worst a
misclassification does is run the wrong read-only chain.

**The product ships with no model configured.** Keyword matching is the default
and the tests run against it.

---

## The trace

Every run produces a flat trace: which agent, which tool, whether it succeeded,
how long it took, and which module computed the result. The agent console
renders it, and an operator can expand any step to see the evidence.

```
GLOBAL EYE  events ✓  exposure ✓
FLEET       fleet ✓  risk ✓
ROUTE       optimize ✓
CRITIC      APPROVED
```

A failed call is distinguished from an *unavailable* one. "The weather artefact
has not been exported" and "the weather tool crashed" are different states: the
first is something the product reports honestly, the second is a defect.

---

## Adding an agent

1. Write the deterministic module. It owns the arithmetic.
2. Register a tool that wraps it, with an access level, an argument schema,
   `computed_by`, and its failure modes.
3. Subclass `Agent`, declare `allowed_tools` and `max_access`, and implement
   `run`. Select and reconcile; do not compute.
4. Add it to an intent's chain in `orchestrator.py` if it should be routed to.
5. If it produces a recommendation, make sure the intent is `high_impact` so the
   Critic sees it.

A test will fail if the agent declares a tool that does not exist, if it holds an
EXECUTE ceiling, or if it declares no failure modes.
