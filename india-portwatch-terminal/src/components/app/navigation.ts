/**
 * Navigation, keyed by role.
 *
 * The left rail is the clearest statement of what a role is allowed to think
 * about, so it is declared once here rather than assembled per screen.
 *
 * Each role's rail is ordered by how often a duty operator reaches for it, not
 * alphabetically and not by how impressive the screen is. The map-first
 * surfaces come first because that is where a shift actually starts.
 */

import {
  Activity,
  Anchor,
  Bell,
  Boxes,
  Building2,
  CloudRain,
  Database,
  Gauge,
  GitBranch,
  Globe2,
  GraduationCap,
  ListChecks,
  Network,
  Radar,
  Route,
  Server,
  Ship,
  SlidersHorizontal,
  TrendingUp,
  Waypoints,
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
    { to: "/vessel/overview", label: "Bridge", icon: Gauge, hint: "This vessel, right now" },
    { to: "/vessel/routes", label: "Route", icon: Route, hint: "Passage ahead and the alternative" },
    { to: "/vessel/ports", label: "Destination", icon: Anchor, hint: "Arrival port congestion and wait" },
    { to: "/vessel/advisories", label: "Advisories", icon: Bell, hint: "Recommendations from port authorities" },
    { to: "/vessel/alerts", label: "Alerts", icon: Globe2, hint: "Events touching this passage" },
  ],
  SHIPPING_COMPANY: [
    { to: "/company/overview", label: "Fleet Command", icon: Radar, hint: "Which ships need intervention now" },
    { to: "/company/fleet", label: "Fleet", icon: Ship, hint: "Every vessel, scored" },
    { to: "/company/routes", label: "Routes", icon: Route, hint: "Lane exposure across the fleet" },
    { to: "/company/global-eye", label: "Global Eye", icon: Globe2, hint: "What impacts my fleet" },
    { to: "/company/cargo", label: "Cargo", icon: Boxes, hint: "Transshipment connections" },
    { to: "/company/risk", label: "Risk", icon: Activity, hint: "Exposure windows and deadlines" },
    { to: "/company/advisories", label: "Advisories", icon: Bell, hint: "Port recommendations to answer" },
  ],
  PORT_AUTHORITY: [
    { to: "/port/overview", label: "Overview", icon: Gauge, hint: "The port's operating state" },
    { to: "/port/traffic", label: "Traffic", icon: Ship, hint: "Approaches, anchorage and berths" },
    { to: "/port/vessels", label: "Arrivals", icon: Anchor, hint: "Arrivals and expected wait" },
    { to: "/port/operations", label: "Operations", icon: Activity, hint: "Queue, throughput, turnaround" },
    { to: "/port/forecast", label: "Forecast", icon: TrendingUp, hint: "Ten days with calibrated bands" },
    { to: "/port/weather", label: "Weather", icon: CloudRain, hint: "Marine conditions and forward load" },
    { to: "/port/global-eye", label: "Global Eye", icon: Globe2, hint: "Events with measured exposure here" },
    { to: "/port/twin", label: "3D Twin", icon: Waypoints, hint: "Berths, yard and cranes in space" },
    { to: "/port/cargo", label: "Cargo", icon: Boxes, hint: "Transshipment assignment" },
    { to: "/port/decisions", label: "Decisions", icon: ListChecks, hint: "The action queue" },
    { to: "/port/advisories", label: "Advisories", icon: Bell, hint: "Recommendations to review and issue" },
  ],
  NATIONAL_ADMIN: [
    { to: "/admin/radar", label: "National Radar", icon: Radar, hint: "Where intervention matters now" },
    { to: "/admin/global-eye", label: "Global Eye", icon: Globe2, hint: "World events and maritime exposure" },
    { to: "/admin/ports", label: "Ports", icon: Anchor, hint: "Every port, ranked" },
    { to: "/admin/vessels", label: "Vessels", icon: Ship, hint: "Traffic and feed adapters" },
    { to: "/admin/companies", label: "Companies", icon: Building2, hint: "Carrier accounts and their fleets" },
    { to: "/admin/twins", label: "Port Twins", icon: Waypoints, hint: "3D digital twins by port" },
    { to: "/admin/scenarios", label: "Scenarios", icon: SlidersHorizontal, hint: "Shock propagation" },
    { to: "/admin/model", label: "Model Intelligence", icon: Network, hint: "Pipeline, bench and calibration" },
    { to: "/admin/learning", label: "Learning", icon: GraduationCap, hint: "Outcomes, reliability and policies" },
    { to: "/admin/agents", label: "Agents", icon: GitBranch, hint: "Orchestration, tools and the Critic" },
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
