import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

const root = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "node_modules/cesium/Build/Cesium",
);
const directories = ["Assets", "ThirdParty", "Widgets", "Workers"];

/** Ship workers and imagery locally; the globe needs no CDN or provider token. */
export function cesiumAssets(): Plugin {
  return {
    name: "portwatch-cesium-assets",
    configureServer(server) {
      server.middlewares.use("/cesium", (request, response, next) => {
        const requested = decodeURIComponent((request.url ?? "").split("?")[0]);
        const target = path.resolve(root, `.${requested}`);
        if (
          !target.startsWith(`${root}${path.sep}`) ||
          !directories.some((d) => target.startsWith(path.join(root, d)))
        )
          return next();
        try {
          if (!statSync(target).isFile()) return next();
          const ext = path.extname(target);
          response.setHeader(
            "Content-Type",
            ext === ".js"
              ? "text/javascript"
              : ext === ".json"
                ? "application/json"
                : ext === ".png"
                  ? "image/png"
                  : ext === ".jpg"
                    ? "image/jpeg"
                    : "application/octet-stream",
          );
          response.end(readFileSync(target));
        } catch {
          next();
        }
      });
    },
    generateBundle() {
      if (this.environment.name !== "client") return;
      const emit = (relative: string) => {
        const target = path.join(root, relative);
        for (const entry of readdirSync(target, { withFileTypes: true })) {
          const name = path.join(relative, entry.name);
          if (entry.isDirectory()) emit(name);
          else
            this.emitFile({
              type: "asset",
              fileName: `cesium/${name.replaceAll(path.sep, "/")}`,
              source: readFileSync(path.join(root, name)),
            });
        }
      };
      directories.forEach(emit);
    },
  };
}
