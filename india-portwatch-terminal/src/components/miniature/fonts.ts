/** Shared local font links; intentionally independent of scene modules. */
export const MINIATURE_FONT_LINKS = [
  { rel: "stylesheet", href: "/fonts/miniature.css" },
  ...[
    "archivo-latin-variable.woff2",
    "ibm-plex-mono-latin-400.woff2",
    "ibm-plex-mono-latin-500.woff2",
  ].map((name) => ({
    rel: "preload",
    as: "font",
    type: "font/woff2",
    crossOrigin: "anonymous" as const,
    href: `/fonts/${name}`,
  })),
];
