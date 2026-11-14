import { readFileSync } from "node:fs";
import { loadEnv, type Plugin } from "vite";

const url = "/portwatch-study.pdf";
const asset = new URL("./assets/portwatch-study.pdf", import.meta.url);

export function paperDownload(): Plugin {
  let enabled = false;
  return {
    name: "portwatch-paper-download",
    configResolved(config) {
      enabled =
        loadEnv(config.mode, config.envDir, "VITE_PORTWATCH_PUBLIC_PAPER")
          .VITE_PORTWATCH_PUBLIC_PAPER === "true";
    },
    configureServer(server) {
      if (!enabled) return;
      server.middlewares.use((request, response, next) => {
        if (request.url?.split("?")[0] !== url) return next();
        response.setHeader("Content-Type", "application/pdf");
        response.end(readFileSync(asset));
      });
    },
    generateBundle() {
      if (!enabled || this.environment.name !== "client") return;
      this.emitFile({
        type: "asset",
        fileName: url.slice(1),
        source: readFileSync(asset),
      });
    },
  };
}
