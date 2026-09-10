import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  HeadContent,
  Outlet,
  Scripts,
  createRootRouteWithContext,
  useRouter,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import { AuthProvider } from "@/auth/AuthProvider";
import { WorldProvider } from "@/world/WorldContext";
import { Button } from "@/components/kit/layout";
import { Pill } from "@/components/kit/primitives";
import { reportLovableError } from "../lib/lovable-error-reporting";
import appCss from "../styles.css?url";

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-0 grid place-items-center bg-[var(--bg)] p-6">
      <div className="w-full max-w-[420px] rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)] p-5">
        {children}
      </div>
    </div>
  );
}

function NotFoundComponent() {
  return (
    <Centered>
      <div className="mb-2 flex items-center gap-2">
        <Pill tone="warn">Route not found</Pill>
      </div>
      <p className="text-[12.5px] leading-relaxed text-[var(--text-3)]">
        No screen is registered at this address. Sign in to reach your workspace.
      </p>
      <a
        href="/login"
        className="mt-3 inline-block rounded-[2px] border border-[var(--line-strong)] px-2.5 py-[5px] text-[11.5px] text-[var(--text-2)] hover:text-[var(--text)]"
      >
        Go to sign-in
      </a>
    </Centered>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  useEffect(() => {
    console.error(error);
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <Centered>
      <div className="mb-2 flex items-center gap-2">
        <Pill tone="crit">Interface fault</Pill>
      </div>
      <p className="mb-3 text-[12.5px] leading-relaxed text-[var(--text-2)]">{error.message}</p>
      <Button
        variant="default"
        onClick={() => {
          void router.invalidate();
          reset();
        }}
      >
        Reload this view
      </Button>
    </Centered>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "India PortWatch — Maritime Operations Intelligence" },
      {
        name: "description",
        content:
          "Predictive maritime digital twin and operations intelligence for Indian ports: national command radar, port digital twin, vessel routing, forecasting and provenance.",
      },
      { name: "author", content: "India PortWatch" },
      { property: "og:title", content: "India PortWatch" },
      {
        property: "og:description",
        content: "Predictive maritime operations intelligence for Indian ports.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <WorldProvider>
          <Outlet />
        </WorldProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
