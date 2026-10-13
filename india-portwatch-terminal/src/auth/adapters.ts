/**
 * Production (default): verify server-managed credentials and revocable sessions.
 * Demonstration: opaque server sessions own isolated visitor worlds. Their
 * roles are demonstration permissions and never authenticate operational APIs.
 * Direct role entry is available in production; the demo adapter also keeps
 * compatibility with the published fictional roster.
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
import { ApiError, getJson, postJson } from "@/services/api";

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

function expired(session: Session): boolean {
  const at = Date.parse(session.expiresAt);
  return Number.isFinite(at) ? at <= Date.now() : true;
}

export const demoAdapter: AuthAdapter = {
  mode: "demo",
  description:
    "Server-issued session scoped to a visitor-owned demonstration world.",

  async signIn({ email, password }: Credentials): Promise<Session> {
    const account = DEMO_ACCOUNTS[email.trim().toLowerCase()];
    if (!account || account.password !== password) {
      throw new AuthError(
        "invalid_credentials",
        "Unrecognised account or password for this demo environment.",
      );
    }
    return postJson<Session>("/demo/session", { role: account.user.role });
  },

  async signOut(session): Promise<void> {
    if (!session?.accessToken) return;
    try {
      await postJson(
        "/demo/logout",
        {},
        { Authorization: `Bearer ${session.accessToken}` },
      );
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
    }
  },

  async restore(session: Session): Promise<Session | null> {
    if (session.mode !== "demo" || !session.accessToken || expired(session))
      return null;
    try {
      return {
        ...(await getJson<Session>("/demo/session", {
          Authorization: `Bearer ${session.accessToken}`,
        })),
        accessToken: session.accessToken,
      };
    } catch {
      return null;
    }
  },
};

export const productionAdapter: AuthAdapter = {
  mode: "production",
  description:
    "Server-managed accounts with verified sessions and server-assigned membership.",

  async signIn(credentials: Credentials): Promise<Session> {
    try {
      return await postJson<Session>("/auth/login", credentials);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401)
        throw new AuthError(
          "invalid_credentials",
          "Invalid email or password.",
        );
      throw error;
    }
  },

  async signOut(session: Session | null): Promise<void> {
    if (session?.accessToken) {
      try {
        await postJson(
          "/auth/logout",
          {},
          { Authorization: `Bearer ${session.accessToken}` },
        );
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error;
      }
    }
  },

  async restore(session: Session): Promise<Session | null> {
    if (
      session.mode !== "production" ||
      !session.accessToken ||
      expired(session)
    )
      return null;
    try {
      const verified = await getJson<Session>("/auth/session", {
        Authorization: `Bearer ${session.accessToken}`,
      });
      return { ...verified, accessToken: session.accessToken };
    } catch {
      return null;
    }
  },
};

export function resolveAdapter(mode?: string): AuthAdapter {
  return mode === "demo" ? demoAdapter : productionAdapter;
}

export const AUTH_MODE: AuthMode =
  (import.meta.env.VITE_PORTWATCH_AUTH_MODE as AuthMode | undefined) === "demo"
    ? "demo"
    : "production";
