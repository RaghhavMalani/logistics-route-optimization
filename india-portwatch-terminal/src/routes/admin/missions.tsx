import { createFileRoute } from "@tanstack/react-router";

import { MissionScreen } from "@/components/missions/MissionScreen";

export const Route = createFileRoute("/admin/missions")({
  component: AdminMissions,
});

function AdminMissions() {
  return <MissionScreen title="Historical missions" />;
}
