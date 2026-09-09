/**
 * Identity and access model for the terminal.
 *
 * Three roles, because the product answers three different questions:
 *
 *   VESSEL_OPERATOR  "where should my ship go, and what am I exposed to?"
 *   PORT_OPERATOR    "what is happening at my port and what do I do?"
 *   ADMIN            "where across the network does intervention matter?"
 *
 * A role is not a cosmetic filter. It selects the workspace, the navigation and
 * the routes that will render at all -- see `guards.tsx`.
 */

export type Role = "VESSEL_OPERATOR" | "PORT_OPERATOR" | "ADMIN";

export const ROLES: Role[] = ["VESSEL_OPERATOR", "PORT_OPERATOR", "ADMIN"];

export interface RoleProfile {
  role: Role;
  /** Short name for the top bar context breadcrumb. */
  label: string;
  /** Workspace root this role lands on after sign-in. */
  home: string;
  /** Route prefixes this role may enter. */
  scope: string[];
  description: string;
}

export const ROLE_PROFILE: Record<Role, RoleProfile> = {
  VESSEL_OPERATOR: {
    role: "VESSEL_OPERATOR",
    label: "Vessel Operator",
    home: "/vessel/overview",
    scope: ["/vessel"],
    description:
      "Fleet-side view: arrival windows, port-wait exposure and routing advice for declared vessels.",
  },
  PORT_OPERATOR: {
    role: "PORT_OPERATOR",
    label: "Port Operator",
    home: "/port/overview",
    scope: ["/port"],
    description:
      "Single-port digital twin: queue, throughput, forecast, weather and the action queue for one facility.",
  },
  ADMIN: {
    role: "ADMIN",
    label: "National Command",
    home: "/admin/radar",
    scope: ["/admin", "/port", "/vessel"],
    description:
      "Whole-network command: every port, the model bench, scenarios, provenance and system state.",
  },
};

/** Where the identity came from. Never inferred — the adapter states it. */
export type AuthMode = "demo" | "production";

export interface User {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  organisation: string;
  /** Port operators are scoped to one facility; null for the other roles. */
  portCode: string | null;
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
