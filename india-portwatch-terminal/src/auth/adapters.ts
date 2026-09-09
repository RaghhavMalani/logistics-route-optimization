/**
 * Authentication adapters.
 *
 * There are exactly two, and they are not interchangeable:
 *
 *   demoAdapter        Local role selection with published credentials. It
 *                      performs NO security function whatsoever -- the account
 *                      list and its passwords are in this file and shipped to
 *                      the browser. It exists so the four workspaces can be
 *                      demonstrated, and it says so on the sign-in screen.
 *
 *   productionAdapter  The seam for a real identity provider (OIDC, the port
 *                      authority's directory, whatever the deployment uses).
 *                      It is deliberately inert until wired: it refuses every
 *                      sign-in with `not_configured` rather than falling back
 *                      to the demo path, because an auth layer that silently
 *                      degrades to "everyone is an admin" is worse than none.
 *
 * `VITE_PORTWATCH_AUTH_MODE=production` selects the second one.
 */

import {
  AuthError,
  normaliseRole,
  type AuthAdapter,
  type AuthMode,
  type Credentials,
  type Role,
  type Session,
  type User,
} from "./types";

const SESSION_HOURS = 12;

interface DemoAccount {
  password: string;
  user: User;
}

/** The fictional carrier the company and vessel accounts belong to. */
export const DEMO_COMPANY_ID = "portwatch-demo-shipping";
export const DEMO_COMPANY_NAME = "PortWatch Demo Shipping";

/**
 * Published demo accounts. Anyone reading the bundle can see these; that is
 * intended, and it is why this adapter must never be used to protect anything.
 *
 * The company and the vessel accounts share an organisation on purpose: they are
 * the same carrier at two altitudes, and the advisory workflow needs both to
 * resolve to the same recipient organisation.
 */
export const DEMO_ACCOUNTS: Record<string, DemoAccount> = {
  "vessel@portwatch.demo": {
    password: "portwatch",
    user: {
      id: "demo-vessel",
      email: "vessel@portwatch.demo",
      displayName: "R. Nayar",
      role: "VESSEL_OPERATOR",
      organisation: DEMO_COMPANY_NAME,
      portCode: null,
      companyId: DEMO_COMPANY_ID,
      vesselIds: ["PWD-001"],
    },
  },
  "company@portwatch.demo": {
    password: "portwatch",
    user: {
      id: "demo-company",
      email: "company@portwatch.demo",
      displayName: "M. Fernandes",
      role: "SHIPPING_COMPANY",
      organisation: DEMO_COMPANY_NAME,
      portCode: null,
      companyId: DEMO_COMPANY_ID,
      // Empty means "every vessel this organisation owns": the advisory store
      // falls back to matching on organisation, which is what a fleet desk
      // actually has authority over.
      vesselIds: [],
    },
  },
  "port@portwatch.demo": {
    password: "portwatch",
    user: {
      id: "demo-port",
      email: "port@portwatch.demo",
      displayName: "S. Iyer",
      role: "PORT_AUTHORITY",
      organisation: "Chennai Port Authority — Control Room",
      portCode: "INMAA",
      companyId: null,
      vesselIds: [],
    },
  },
  "admin@portwatch.demo": {
    password: "portwatch",
    user: {
      id: "demo-admin",
      email: "admin@portwatch.demo",
      displayName: "A. Deshmukh",
      role: "NATIONAL_ADMIN",
      organisation: "National Maritime Operations Centre",
      portCode: null,
      companyId: null,
      vesselIds: [],
    },
  },
};

export const DEMO_ROSTER: Array<{ email: string; role: Role; label: string }> =
  Object.values(DEMO_ACCOUNTS).map((account) => ({
    email: account.user.email,
    role: account.user.role,
    label: account.user.organisation,
  }));

function issue(user: User, mode: AuthMode): Session {
  const now = Date.now();
  return {
    user,
    mode,
    issuedAt: new Date(now).toISOString(),
    expiresAt: new Date(now + SESSION_HOURS * 3_600_000).toISOString(),
  };
}

function expired(session: Session): boolean {
  const at = Date.parse(session.expiresAt);
  return Number.isFinite(at) ? at <= Date.now() : true;
}

export const demoAdapter: AuthAdapter = {
  mode: "demo",
  description:
    "Demo access — credentials are published in the client bundle and verify nothing.",

  async signIn({ email, password }: Credentials): Promise<Session> {
    const account = DEMO_ACCOUNTS[email.trim().toLowerCase()];
    if (!account || account.password !== password) {
      throw new AuthError(
        "invalid_credentials",
        "Unrecognised account or password for this demo environment.",
      );
    }
    return issue(account.user, "demo");
  },

  async signOut(): Promise<void> {
    /* Nothing to revoke: the session never left the browser. */
  },

  async restore(session: Session): Promise<Session | null> {
    if (session.mode !== "demo" || expired(session)) return null;
    const account = DEMO_ACCOUNTS[session.user.email];
    // The account record is the authority, not the stored copy: a session
    // written before the role model changed restores with today's shape rather
    // than carrying a stale role into the guards.
    if (account) return { ...session, user: account.user };

    // No matching account, but the role may still be a recognisable legacy one.
    const role = normaliseRole(session.user.role as unknown as string);
    return role ? { ...session, user: { ...session.user, role } } : null;
  },
};

export const productionAdapter: AuthAdapter = {
  mode: "production",
  description:
    "Production identity provider — not configured in this deployment.",

  async signIn(): Promise<Session> {
    throw new AuthError(
      "not_configured",
      "This build runs in production auth mode but no identity provider is wired. " +
        "Implement AuthAdapter against your OIDC/SSO endpoint, or start the terminal " +
        "with VITE_PORTWATCH_AUTH_MODE=demo.",
    );
  },

  async signOut(): Promise<void> {},

  async restore(): Promise<Session | null> {
    return null;
  },
};

export function resolveAdapter(mode?: string): AuthAdapter {
  return mode === "production" ? productionAdapter : demoAdapter;
}

export const AUTH_MODE: AuthMode =
  (import.meta.env.VITE_PORTWATCH_AUTH_MODE as AuthMode | undefined) === "production"
    ? "production"
    : "demo";
