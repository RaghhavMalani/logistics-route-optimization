/**
 * Navigation, keyed by role.
 *
 * The left rail is the clearest statement of what a role is allowed to think
 * about, so it is declared once here rather than assembled per screen.
 */

import {
  Activity,
  Anchor,
  Bell,
  CloudRain,
  Database,
  Gauge,
  Globe2,
  ListChecks,
  Network,
  Radar,
  Route,
  Server,
  Ship,
  SlidersHorizontal,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "@/auth/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** One line of what the screen answers, used as the rail tooltip. */
  hint: string;
}

export const NAVIGATION: Record<Role, NavItem[]> = {
  VESSEL_OPERATOR: [
    { to: "/vessel/overview", label: "Overview", icon: Gauge, hint: "Fleet exposure right now" },
    { to: "/vessel/fleet", label: "Fleet", icon: Ship, hint: "Every vessel scored against the forecast" },
    { to: "/vessel/routes", label: "Routes", icon: Route, hint: "Intended call versus the alternative" },
    { to: "/vessel/ports", label: "Ports", icon: Anchor, hint: "Destination congestion and wait" },
    { to: "/vessel/alerts", label: "Alerts", icon: Bell, hint: "Events touching the fleet's lanes" },
  ],
  PORT_OPERATOR: [
    { to: "/port/overview", label: "Overview", icon: Gauge, hint: "The port's operating state" },
    { to: "/port/operations", label: "Operations", icon: Activity, hint: "Queue, throughput, turnaround" },
    { to: "/port/forecast", label: "Forecast", icon: TrendingUp, hint: "Ten days with calibrated bands" },
    { to: "/port/vessels", label: "Vessels", icon: Ship, hint: "Arrivals and expected wait" },
    { to: "/port/weather", label: "Weather", icon: CloudRain, hint: "Marine conditions and forward load" },
    { to: "/port/events", label: "Events", icon: Globe2, hint: "Shocks with measured exposure here" },
    { to: "/port/decisions", label: "Decisions", icon: ListChecks, hint: "The action queue" },
  ],
  ADMIN: [
    { to: "/admin/radar", label: "National Radar", icon: Radar, hint: "Where intervention matters now" },
    { to: "/admin/ports", label: "Ports", icon: Anchor, hint: "Every port, ranked" },
    { to: "/admin/vessels", label: "Vessels", icon: Ship, hint: "AIS activity and feed adapters" },
    { to: "/admin/model", label: "Model Intelligence", icon: Network, hint: "Pipeline, bench and calibration" },
    { to: "/admin/scenarios", label: "Scenarios", icon: SlidersHorizontal, hint: "Shock propagation" },
    { to: "/admin/intelligence", label: "Intelligence", icon: Globe2, hint: "Events, chokepoints, sentiment" },
    { to: "/admin/data", label: "Data Sources", icon: Database, hint: "Provenance of every feed" },
    { to: "/admin/system", label: "System", icon: Server, hint: "Artefacts and service state" },
  ],
};

/** Longest-prefix match, so a detail route keeps its parent item lit. */
export function activeNavItem(items: NavItem[], pathname: string): NavItem | null {
  let best: NavItem | null = null;
  for (const item of items) {
    if (pathname === item.to || pathname.startsWith(`${item.to}/`)) {
      if (!best || item.to.length > best.to.length) best = item;
    }
  }
  return best;
}
