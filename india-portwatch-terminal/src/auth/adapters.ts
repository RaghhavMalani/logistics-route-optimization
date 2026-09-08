/**
 * Authentication adapters.
 *
 * There are exactly two, and they are not interchangeable:
 *
 *   demoAdapter        Local role selection with published credentials. It
 *                      performs NO security function whatsoever -- the account
 *                      list and its passwords are in this file and shipped to
 *                      the browser. It exists so the three workspaces can be
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
  user: Omit<User, "id"> & { id: string };
}

/**
 * Published demo accounts. Anyone reading the bundle can see these; that is
 * intended, and it is why this adapter must never be used to protect anything.
 */
export const DEMO_ACCOUNTS: Record<string, DemoAccount> = {
  "vessel@portwatch.demo": {
    password: "portwatch",
    user: {
      id: "demo-vessel",
      email: "vessel@portwatch.demo",
      displayName: "R. Nayar",
      role: "VESSEL_OPERATOR",
      organisation: "Konkan Line — Fleet Operations",
      portCode: null,
    },
  },
  "port@portwatch.demo": {
    password: "portwatch",
    user: {
      id: "demo-port",
      email: "port@portwatch.demo",
      displayName: "S. Iyer",
      role: "PORT_OPERATOR",
      organisation: "Chennai Port Authority — Control Room",
      portCode: "INMAA",
    },
  },
  "admin@portwatch.demo": {
    password: "portwatch",
    user: {
      id: "demo-admin",
      email: "admin@portwatch.demo",
      displayName: "A. Deshmukh",
      role: "ADMIN",
      organisation: "National Maritime Operations Centre",
      portCode: null,
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
    return account ? { ...session, user: account.user } : null;
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
