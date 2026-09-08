/**
 * Session state for the whole terminal.
 *
 * One provider, one source of truth. Components ask `useAuth()` for the current
 * user and `useWorkspace()` for the context they are rendering in; nothing does
 * its own role arithmetic.
 *
 * Server and first client render both report `status: "restoring"`, so the
 * stored session is read only in an effect. That keeps SSR markup and the
 * hydrated tree identical.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { AUTH_MODE, resolveAdapter } from "./adapters";
import {
  ROLE_PROFILE,
  type Credentials,
  type Role,
  type Session,
} from "./types";

const SESSION_KEY = "portwatch.session.v1";
const VIEW_AS_KEY = "portwatch.viewAs.v1";
const PORT_KEY = "portwatch.port.v1";

export type AuthStatus = "restoring" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  session: Session | null;
  /** The signed-in user's real role. */
  role: Role | null;
  /**
   * The role whose workspace is being rendered. Equal to `role` for everyone
   * except an admin who has switched context with the workspace selector.
   */
  viewAs: Role | null;
  /** Port an operator is scoped to, or the port an admin is inspecting. */
  portCode: string;
  mode: typeof AUTH_MODE;
  adapterDescription: string;
  signIn(credentials: Credentials): Promise<Session>;
  signOut(): Promise<void>;
  setViewAs(role: Role): void;
  setPortCode(code: string): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStored<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStored(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    if (value == null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Private browsing or a blocked store: the session simply will not
       survive a reload, which is an acceptable degradation. */
  }
}

const DEFAULT_PORT = "INMAA";

export function AuthProvider({ children }: { children: ReactNode }) {
  const adapter = useMemo(() => resolveAdapter(AUTH_MODE), []);
  const [status, setStatus] = useState<AuthStatus>("restoring");
  const [session, setSession] = useState<Session | null>(null);
  const [viewAs, setViewAsState] = useState<Role | null>(null);
  const [portCode, setPortCodeState] = useState<string>(DEFAULT_PORT);

  useEffect(() => {
    let cancelled = false;
    const stored = readStored<Session>(SESSION_KEY);
    const storedPort = readStored<string>(PORT_KEY);
    if (storedPort) setPortCodeState(storedPort);

    if (!stored) {
      setStatus("anonymous");
      return () => {
        cancelled = true;
      };
    }

    void adapter
      .restore(stored)
      .then((restored) => {
        if (cancelled) return;
        if (!restored) {
          writeStored(SESSION_KEY, null);
          setStatus("anonymous");
          return;
        }
        const storedView = readStored<Role>(VIEW_AS_KEY);
        setSession(restored);
        setViewAsState(
          restored.user.role === "ADMIN" && storedView
            ? storedView
            : restored.user.role,
        );
        if (restored.user.portCode) setPortCodeState(restored.user.portCode);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        writeStored(SESSION_KEY, null);
        setStatus("anonymous");
      });

    return () => {
      cancelled = true;
    };
  }, [adapter]);

  const signIn = useCallback(
    async (credentials: Credentials) => {
      const next = await adapter.signIn(credentials);
      writeStored(SESSION_KEY, next);
      writeStored(VIEW_AS_KEY, next.user.role);
      setSession(next);
      setViewAsState(next.user.role);
      if (next.user.portCode) {
        setPortCodeState(next.user.portCode);
        writeStored(PORT_KEY, next.user.portCode);
      }
      setStatus("authenticated");
      return next;
    },
    [adapter],
  );

  const signOut = useCallback(async () => {
    await adapter.signOut(session);
    writeStored(SESSION_KEY, null);
    writeStored(VIEW_AS_KEY, null);
    setSession(null);
    setViewAsState(null);
    setStatus("anonymous");
  }, [adapter, session]);

  const setViewAs = useCallback(
    (next: Role) => {
      if (session?.user.role !== "ADMIN") return;
      setViewAsState(next);
      writeStored(VIEW_AS_KEY, next);
    },
    [session],
  );

  const setPortCode = useCallback((code: string) => {
    setPortCodeState(code);
    writeStored(PORT_KEY, code);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      role: session?.user.role ?? null,
      viewAs: viewAs ?? session?.user.role ?? null,
      portCode: session?.user.portCode ?? portCode,
      mode: AUTH_MODE,
      adapterDescription: adapter.description,
      signIn,
      signOut,
      setViewAs,
      setPortCode,
    }),
    [
      adapter.description,
      portCode,
      session,
      setPortCode,
      setViewAs,
      signIn,
      signOut,
      status,
      viewAs,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/** The workspace currently on screen, resolved once for every consumer. */
export function useWorkspace() {
  const { viewAs, role, session, portCode } = useAuth();
  const active = viewAs ?? role ?? "ADMIN";
  return {
    role: active,
    profile: ROLE_PROFILE[active],
    isImpersonating: role === "ADMIN" && viewAs !== null && viewAs !== "ADMIN",
    user: session?.user ?? null,
    portCode,
  };
}
