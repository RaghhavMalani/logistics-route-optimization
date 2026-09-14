# The flagship demo — two minutes, from "what should we do?" to the revealed outcome

One job: show a system that computes a decision, puts it in front of a human
with every trade-off on the chart, and then lets history mark its answer.

**The spine:** `SENSE → UNDERSTAND → PREDICT → GENERATE OPTIONS → SIMULATE →
OPTIMISE → CRITIQUE → HUMAN DECISION → OBSERVE OUTCOME → LEARN`

Every number on screen is a measurement a simulator produced on a branch of
the observed world. Where there is none, the screen says so — and that is one
of the things you show.

---

## Before you start

```bash
python run_award_demo.py --source portwatch --model ensemble --refresh   # fresh events (~2 min)
python scripts/demo_acceptance.py                                        # 28 claims, none failing
uvicorn backend.app.main:app --port 8000                                 # terminal 1
cd india-portwatch-terminal && npm run dev                               # terminal 2
```

`PORTWATCH_LICENCE_MODE=DEMO`. The register's claims lapse about three days
after the refresh; if the action rail shows nothing marked ACT SOON, refresh
again. Sign in as `admin@portwatch.demo` (National Command). Have
`port@portwatch.demo` in a second tab.

---

## 00:00–00:20 — Sense and understand

`/admin/global-eye`. The action rail ranks what needs intervention.

> "Fourteen headlines about one Red Sea incident became one event with nine
> sources. It reaches Bab-el-Mandeb, the Europe–India lane, six hulls, two
> ports. MV Coromandel is six hours short of the strait and the option closes
> in five hours fifty. Nothing here is a probability the system has not
> earned: severity times corroboration, and it says so."

## 00:20–00:50 — Generate, simulate, optimise, critique

Press **What should we do?** on MV Coromandel.

> "Four options survived. Doing nothing was computed the same way as the
> others, on its own branch: plus thirty hours, exposure 0.68 at the strait.
> The Cape is not offered — the hull has entered the canal side of the lane
> and the routing branches at Gibraltar; it says why. Delay departure is not
> offered because the subject does not declare a departure port. Nothing was
> invented to fill the list."

Click **Compare**, then option **B**, then **A**.

> "The world changes with the option. Solid is the one selected, dashed the
> alternatives, thin and grey the current plan. The ring on the quay is that
> option's yard pressure, not a decoration."

Open **Frontier**.

> "Every point is a real evaluated option. Filled means nondominated. Hollow
> means some other option is no worse everywhere and better somewhere — hover
> and it names which. The recommendation is never a hollow point, and the
> balanced weights are printed under the chart, not hidden in it."

Open **Why**.

> "The Critic passed it with warnings, and each warning names the computation
> it read: weather confidence 0.23 on 46 per cent grid coverage; four cost
> components unpriced; and the option's zero exposure rests on the claim
> lapsing before the hull arrives — persistence beyond a claim is a stated
> weakness, not a hidden one."

## 00:50–01:10 — Money without invention

Open **Money**.

> "Cost of delay: unknown — no charter rate is configured, and the engine will
> not guess one. Port dues at Nhava Sheva: unknown — the hull declares no
> gross tonnage. Cost of action: zero, with the reason. Unknown is never zero
> here, and there is no total until every component is known."

Type a charter rate and a tonnage, press **Re-price with these assumptions**.

> "Now the delay is priced, labelled ASSUMPTION with my name on it. The port
> dues are priced at JNPA's own scale of rates — page six, verbatim, in force
> from May 2026 — and still labelled an assumption, because the tariff is
> public and the tonnage is mine. The computed problem in the ledger did not
> change; this is a new one."

## 01:10–01:30 — Human decision

Open **Decide**.

> "Decision is not execution. I mark it reviewed. I approve option A. And
> because I am National Command, not the shipping company, the approved option
> reaches the vessel as an advisory — never a command."

Press **Hand into advisory boundary**.

> "It is now a DRAFT advisory in the same boundary the port uses. Eleven
> states, role-gated, every transition audited. The hull sees nothing until a
> named person issues it."

(Thirty seconds spare: in the port tab, `/port/twin`, press **What should we
do?** — six berth plans on the same engine, and the 3D scene rewrites its
berths and cranes to whichever you select. Point at the one marked
*dominated*.)

## 01:30–02:00 — Observe the outcome, learn

`/admin/missions`. The clock reads 23 March 2021, 08:00Z.

> "The Ever Given has been aground for two hours. PortWatch can read only the
> two reports that existed then; nine more are hidden until the reveal. Three
> India-bound hulls are placed on the modelled lane — illustrative, and it
> says so."

Press **Decide** on MV Konkan.

> "The whole Cape diversion is drawn, from the Mediterranean round Africa.
> The engine recommends slowing and holding clear of Suez, expecting the
> canal to reopen inside its seventy-two-hour claim horizon."

Press **Choose this option**, then **Reveal outcome**.

> "The canal was blocked for a hundred and fifty-five hours. The seventy-two
> hour claim horizon understated it by eighty-one, and the scorecard says so
> in those words. Every option is scored against what actually happened —
> the Cape hull arrived when the engine said it would; the hull that waited
> then took its turn in a queue the sources put at four hundred ships. Regret
> is thirty-one hours against the
> realised best, and the ranking was wrong. That verdict is written to the
> ledger and it feeds the learning screen. The point of the product is not
> that it was right. It is that it can tell you, in numbers, when it was
> wrong."

---

## The questions you will be asked

**"Did an LLM produce those numbers?"** No. The Copilot orchestrates and
explains; every figure is a `Measure` with a basis from a simulator. Ask it
"What should MV Coromandel do?" and it opens the same panel on the same
problem.

**"Why is the Cape not offered?"** `route_topology`: the alternative routing
branches at Gibraltar; a hull past the branch cannot reach it. The row under
*Not offered* says exactly that.

**"Where do the tariffs come from?"** `data/tariffs/public_tariffs.json`:
JNPA Scale of Rates w.e.f. 1 May 2026 and the Chennai indexed SoR 2025-26,
transcribed verbatim with page, section, URL, retrieval date and sha256;
labelled `PUBLIC_TARIFF`, reuse `REQUIRES_REVIEW`. TAMP was unreachable when
investigated and the attempt is recorded.

**"Can it be gamed by an assumption?"** An assumption prices a component and
labels it; it never changes a constraint, a risk or an ETA, and the Critic's
`assumptions` check flags every option built on one.

**"What if no option survives?"** The problem says so and recommends nothing.
A rejected option is still shown, with the constraint that rejected it.

**"Is the mission real?"** The chronology and the outcome are transcribed from
cited sources; the hulls are illustrative and the screen says so on every
one. Nothing operational the sources do not state has been reconstructed.

## If something breaks mid-demo

- **No ACT SOON items:** the register lapsed; `python run_award_demo.py
  --source portwatch --model ensemble --refresh`, then reload.
- **The chart shows INITIALISING:** the pane was hidden while the map loaded;
  reload the tab with it visible.
- **The mission says "no observation is visible at the replay clock":** press
  *restart* on the rail; a replay is a run, not a page.
- **A decision id collides:** the ledger refuses to rewrite a resolved
  problem; press *What should we do?* again — the new instant makes a new id.
