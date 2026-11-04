export const TWIN_RAMP = ["#daebee", "#73a6b2", "#205c6e"] as const;

/** What the operator is colouring the scene by. */
export type TwinOverlay =
  "utilisation" | "dwell" | "workload" | "queue" | "storage";

export const OVERLAYS: Array<{
  key: TwinOverlay;
  label: string;
  hint: string;
}> = [
  {
    key: "utilisation",
    label: "Utilisation",
    hint: "Berth occupancy and yard fill",
  },
  {
    key: "dwell",
    label: "Dwell",
    hint: "How long cargo has been sitting in each block",
  },
  {
    key: "workload",
    label: "Crane workload",
    hint: "Working hours accrued per crane",
  },
  {
    key: "queue",
    label: "Queue",
    hint: "Waiting hours at each anchorage position",
  },
  {
    key: "storage",
    label: "Storage pressure",
    hint: "Yard and shed capacity headroom",
  },
];

export interface TwinSelection {
  kind:
    | "berth"
    | "yard"
    | "shed"
    | "crane"
    | "vessel"
    | "gate"
    | "vehicle"
    | "rail"
    | "quay";
  id: string;
  label: string;
  fields: Array<[string, string]>;
}
