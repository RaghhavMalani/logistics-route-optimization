import base from "./vercel.base.json" with { type: "json" };

const isolatedPreview =
  process.env.VERCEL_ENV === "preview" &&
  ["feat/theme-v2", "review/portwatch-weather-paradip"].includes(process.env.VERCEL_GIT_COMMIT_REF);

const rewrites = [...base.rewrites];
if (isolatedPreview) {
  // Keep the explicit production rule first. The last rule covers every
  // hostname assigned to this preview, including its generated URL.
  rewrites[rewrites.length - 1] = {
    source: "/api/:path*",
    destination: "https://api-integrated-20261102-integrated-preview-20261102.up.railway.app/api/:path*",
  };
}

export const config = { ...base, rewrites };
