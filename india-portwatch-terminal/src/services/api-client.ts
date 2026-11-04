/** Schema-checked requests using the existing authentication and home transport. */
import { getJson, postJson, type RequestOptions } from "./api";
import type { paths } from "./openapi.generated";

type Method = "get" | "post";
type PathFor<M extends Method> = {
  [P in keyof paths]: paths[P] extends Record<M, unknown> ? P : never;
}[keyof paths];

export type ApiResponse<P extends keyof paths, M extends keyof paths[P]> =
  paths[P][M] extends {
    responses: { 200: { content: { "application/json": infer Payload } } };
  }
    ? Payload
    : unknown;

type ApiBody<P extends PathFor<"post">> = paths[P]["post"] extends {
  requestBody: { content: { "application/json": infer Payload } };
}
  ? Payload
  : never;

export function getApi<P extends PathFor<"get">>(
  path: P,
  headers?: Record<string, string>,
  options?: RequestOptions,
) {
  return getJson<ApiResponse<P, "get">>(path.slice(4), headers, options);
}

export function postApi<P extends PathFor<"post">>(
  path: P,
  body: ApiBody<P>,
  headers?: Record<string, string>,
  options?: RequestOptions,
) {
  return postJson<ApiResponse<P, "post">>(path.slice(4), body, headers, options);
}
