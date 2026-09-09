/**
 * Identity and access model for the terminal.
 *
 * Four roles, because the product answers four different questions:
 *
 *   VESSEL_OPERATOR   "where should my ship go, and what am I exposed to?"
 *   SHIPPING_COMPANY  "which ships in my fleet need intervention in 72 hours?"
 *   PORT_AUTHORITY    "what is happening at my port, and what do I do about it?"
 *   NATIONAL_ADMIN    "where across the network does intervention matter?"
 *
 * A role is not a cosmetic filter. It selects the workspace, the navigation and
 * the routes that will render at all -- see `guards.tsx`.
 *
 * The pair that most needs keeping apart is PORT_AUTHORITY and SHIPPING_COMPANY.
 * They are the two sides of an advisory: the port recommends and the company
 * responds. Collapsing them into one "operator" role would make the human
 * approval step in the advisory workflow meaningless, because the same identity
 * would sit on both ends of it.
 */

export type Role =
  | "VESSEL_OPERATOR"
  | "SHIPPING_COMPANY"
  | "PORT_AUTHORITY"
  | "NATIONAL_ADMIN";

export const ROLES: Role[] = [
  "VESSEL_OPERATOR",
  "SHIPPING_COMPANY",
  "PORT_AUTHORITY",
  "NATIONAL_ADMIN",
];

/**
 * Which side of the advisory workflow a role sits on.
 *
 * Sent to the API as `X-PortWatch-Role`, where the advisory store turns it into
 * a principal. A role that is neither cannot act on an advisory at all.
 */
export type AdvisoryParty = "issuer" | "recipient" | null;

export interface RoleProfile {
  role: Role;
  /** Short name for the top bar context breadcrumb. */
  label: string;
  /** Workspace root this role lands on after sign-in. */
  home: string;
  /** Route prefixes this role may enter. */
  scope: string[];
  description: string;
  advisoryParty: AdvisoryParty;
}

export const ROLE_PROFILE: Record<Role, RoleProfile> = {
  VESSEL_OPERATOR: {
    role: "VESSEL_OPERATOR",
    label: "Vessel Bridge",
    home: "/vessel/overview",
    scope: ["/vessel"],
    description:
      "One vessel: surrounding traffic, weather ahead, destination risk and the advisories addressed to it.",
    advisoryParty: "recipient",
  },
  SHIPPING_COMPANY: {
    role: "SHIPPING_COMPANY",
    label: "Fleet Command",
    home: "/company/overview",
    scope: ["/company", "/vessel"],
    description:
      "A carrier's whole fleet: which ships need intervention, route risk, cargo connections and advisories received.",
    advisoryParty: "recipient",
  },
  PORT_AUTHORITY: {
    role: "PORT_AUTHORITY",
    label: "Port Authority",
    home: "/port/overview",
    scope: ["/port"],
    description:
      "One facility: queue, forecast, weather, the 3D digital twin, cargo assignment and the advisories it issues.",
    advisoryParty: "issuer",
  },
  NATIONAL_ADMIN: {
    role: "NATIONAL_ADMIN",
    label: "National Command",
    home: "/admin/radar",
    scope: ["/admin", "/port", "/vessel", "/company"],
    description:
      "The whole network: every port, Global Eye, the model bench, scenarios, learning and system state.",
    advisoryParty: "issuer",
  },
};

/**
 * Older role names, kept so a stored session from a previous build restores
 * rather than being thrown away.
 *
 * A session in localStorage outlives a deploy. Without this map, everyone who
 * had signed in before the four-role change would land on the sign-in screen
 * with no explanation, which reads as a bug rather than as a schema change.
 */
const LEGACY_ROLES: Record<string, Role> = {
  ADMIN: "NATIONAL_ADMIN",
  PORT_OPERATOR: "PORT_AUTHORITY",
  VESSEL_OPERATOR: "VESSEL_OPERATOR",
};

export function normaliseRole(value: string | null | undefined): Role | null {
  if (!value) return null;
  if ((ROLES as string[]).includes(value)) return value as Role;
  return LEGACY_ROLES[value] ?? null;
}

/** Where the identity came from. Never inferred — the adapter states it. */
export type AuthMode = "demo" | "production";

export interface User {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  organisation: string;
  /** Port authorities are scoped to one facility; null for the other roles. */
  portCode: string | null;
  /** Shipping companies and vessel operators are scoped to one carrier account. */
  companyId: string | null;
  /** Vessels this identity may respond to advisories for. */
  vesselIds: string[];
}

export interface Session {
  user: User;
  mode: AuthMode;
  issuedAt: string;
  expiresAt: string;
}

export interface Credentials {
  email: string;
  password: string;
}

export class AuthError extends Error {
  readonly code: "invalid_credentials" | "not_configured" | "expired";

  constructor(code: AuthError["code"], message: string) {
    super(message);
    this.name = "AuthError";
    this.code = code;
  }
}

/**
 * The seam a real identity provider plugs into. Everything above this line is
 * UI; everything below it is deployment-specific.
 */
export interface AuthAdapter {
  readonly mode: AuthMode;
  /** Human-readable statement of what is actually verifying the credentials. */
  readonly description: string;
  signIn(credentials: Credentials): Promise<Session>;
  signOut(session: Session | null): Promise<void>;
  /** Re-validate a restored session; return null to force a fresh sign-in. */
  restore(session: Session): Promise<Session | null>;
}

export function isRoleAllowed(role: Role, pathname: string): boolean {
  return ROLE_PROFILE[role].scope.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Identity headers for the advisory API.
 *
 * Built here rather than at each call site so there is one place that decides
 * what the backend is told about who is acting. The backend treats these as
 * asserted rather than verified and says so in `/advisories/policy`; replacing
 * them with a signed token is a change to this function and the API's
 * `principal_from_request`, and nothing else.
 */
export function advisoryHeaders(user: User | null): Record<string, string> {
  if (!user) return {};
  const party = ROLE_PROFILE[user.role].advisoryParty;
  if (!party) return {};
  const headers: Record<string, string> = {
    "X-PortWatch-Actor": user.displayName,
    "X-PortWatch-Role": user.role,
  };
  if (user.portCode) headers["X-PortWatch-Port"] = user.portCode;
  if (user.organisation) headers["X-PortWatch-Org"] = user.organisation;
  if (user.vesselIds.length) {
    headers["X-PortWatch-Vessels"] = user.vesselIds.join(",");
  }
  if (user.role === "NATIONAL_ADMIN") headers["X-PortWatch-Admin"] = "true";
  return headers;
}
