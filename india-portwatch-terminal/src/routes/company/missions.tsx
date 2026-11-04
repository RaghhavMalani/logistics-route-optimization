import { createFileRoute } from "@tanstack/react-router";

import { MissionScreen } from "@/components/missions/MissionScreen";

export const Route = createFileRoute("/company/missions")({
  head: () => ({ meta: [{ title: "PortWatch X — Historical missions" }] }),
  component: CompanyMissions,
});

function CompanyMissions() {
  return <MissionScreen title="Historical missions" />;
}
