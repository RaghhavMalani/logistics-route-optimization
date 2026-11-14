import ports from "../miniature/ports.generated.json";

export const CHAPTERS = [
  {
    label: "Overview",
    kicker: "Maritime operations · Indian ports",
    title: "A port system you can read at a glance.",
    body: "PortWatch X models chokepoints, lanes, hulls, quays and cargo bound for Indian ports, then helps an operator compare what to do and why. Scroll to follow one illustrative voyage.",
    facts: [
      `${ports.length} registered ports`,
      "4 roles",
      "1 world per visitor",
    ],
    cam: { x: -78, z: 0, size: 300, az: 44, el: 33 },
  },
  {
    label: "Sense",
    kicker: "01 · Sense",
    title: "It starts with an event far from the berth.",
    body: "Source-linked forecasts, hazard reports and operational notices provide context for a declared voyage. PortWatch traces possible exposure through chokepoints and lanes, separating reported facts, inferred exposure and assumptions. Availability varies by source.",
    facts: ["event → chokepoint → lane → vessel → port"],
    cam: { x: -338, z: -4, size: 118, az: 36, el: 33 },
  },
  {
    label: "Decide",
    kicker: "02 · Decide",
    title: "Keep the plan unless an intervention survives the unknown.",
    body: "In the disruption scenario model, options run on separate simulated branches, pass feasibility checks and are compared over four labelled duration horizons. Minimax regret can favour keeping the current plan or waiting for information. These are scenario comparisons, not observed voyages.",
    facts: [],
    cam: { x: -214, z: 72, size: 150, az: 52, el: 34 },
  },
  {
    label: "Berth",
    kicker: "03 · Berth",
    title: "Three ships arriving, one quay, one plan.",
    body: "The Port workspace compares five simulated berth policies: first come first served, reassign by work, stagger arrivals, size crane gangs and prioritise a commitment. Modelled wait, turnaround and missed departures help explain the trade-off; they are not measured operational savings.",
    facts: [
      "5 simulated berth policies",
      "wait · turnaround · missed departures",
    ],
    cam: { x: -58, z: 4, size: 158, az: 34, el: 32 },
  },
  {
    label: "Cargo",
    kicker: "04 · Cargo",
    title: "Will this consignment make its connection?",
    body: "Compare declared delivery commitments, handling windows and cargo constraints against a frozen passage plan. Unverified capacity and bookings stay unknown. The miniature’s trains and trucks illustrate onward connections; they do not represent booked services.",
    facts: [
      "Money needs an applicable stated basis.",
      "Missing cost or coverage is unknown, never zero.",
    ],
    cam: { x: 96, z: -64, size: 182, az: 47, el: 34 },
  },
  {
    label: "Command",
    kicker: "05 · Command",
    title: "Four roles. One world. Every number traced.",
    body: "Company, Port, Vessel and Admin work within the same visitor’s isolated world and their permitted scope. Frozen comparisons, approvals and advisories remain inspectable through recovery. Demo outcomes are labelled simulation; learning stays collecting or shadow until evaluation supports adoption.",
    facts: [],
    cam: { x: 205, z: -18, size: 210, az: 30, el: 33 },
  },
] as const;

export const HOTSPOTS = [
  {
    ch: 1,
    p: [-340, 5, 0],
    t: "Chokepoint",
    d: "Source-linked reports are deduplicated. Syndicated copies are not independent corroboration; probabilities remain withheld without calibration.",
  },
  {
    ch: 1,
    p: [-338, 16, -112],
    t: "Structural exposure",
    d: "Reference geography connects possible event, lane and port exposure. Applicability and timing need evidence; the link alone establishes no closure or delay.",
  },
  {
    ch: 2,
    p: [-250, 14, 78],
    t: "Your hull",
    d: "This hull is illustrative. Available scenario actions have explicit constraints and are evaluated on their own simulated branch.",
  },
  {
    ch: 2,
    p: [-160, 2, 50],
    t: "Keep current plan",
    d: "A first-class candidate. Intervention is unnecessary when it adds regret across the stated disruption horizons.",
  },
  {
    ch: 2,
    p: [-236, 2, 112],
    t: "Wait for more information",
    d: "An option when the answer depends on the horizon and the decision can remain open until relevant information arrives.",
  },
  {
    ch: 2,
    p: [-128, 2, 134],
    t: "Act: reroute",
    d: "Strategic scenario comparison with a break-even duration. A port-approach advisory does not authorize an entire voyage reroute.",
  },
  {
    ch: 3,
    p: [-140, 12, 2],
    t: "Waiting at anchorage",
    d: "Illustrative waiting hulls and crane motions. Berth-policy comparisons use the simulator’s declared terminal state.",
  },
  {
    ch: 3,
    p: [8, 27, 0],
    t: "Port twin",
    d: "The tour is an invented composite. Operational port twins preserve their own schematic layouts, data bindings and time controls; neither is a surveyed plan.",
  },
  {
    ch: 4,
    p: [72, 9, 76],
    t: "Reefer block",
    d: "Handling compatibility and declared limits can constrain a plan. Unverified plug availability, bookings and actual cargo condition remain unknown.",
  },
  {
    ch: 4,
    p: [96, 20, -138],
    t: "Onward connection",
    d: "A declared cutoff and delivery-event definition support a connection calculation. Animated rail traffic is illustration, not a service timetable.",
  },
  {
    ch: 5,
    p: [236, 52, -30],
    t: "National Command",
    d: "The Admin workspace presents national context within authorized scope. It does not expose other visitors’ private commercial records.",
  },
  {
    ch: 5,
    p: [258, 36, -14],
    t: "Decide, observe, learn",
    d: "Forecasts and claims retain originals and suitable later outcomes. Corrections stay collecting or shadow until chronological evaluation supports adoption; rejected model artifacts remain rejected.",
  },
] as const;
