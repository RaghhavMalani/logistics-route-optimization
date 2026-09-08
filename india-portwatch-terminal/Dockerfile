# India PortWatch terminal.
#
# The API base URL is baked in at build time (Vite inlines VITE_* variables), so
# it is a build argument rather than a runtime environment variable:
#
#   docker build --build-arg VITE_PORTWATCH_API_BASE=https://api.example.com/api .

FROM node:22-slim AS build

WORKDIR /app

ARG VITE_PORTWATCH_API_BASE=/api
ENV VITE_PORTWATCH_API_BASE=$VITE_PORTWATCH_API_BASE

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-slim AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000

COPY --from=build /app/.output ./.output

EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
