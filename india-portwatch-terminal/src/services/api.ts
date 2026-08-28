// const API_BASE =
//   (import.meta.env.VITE_PORTWATCH_API_BASE as string | undefined)?.replace(
//     /\/$/,
//     "",
//   ) ?? "/api";

// function endpoint(path: string): string {
//   return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
// }

// export async function getJson<T>(path: string, fallback: () => T): Promise<T> {
//   try {
//     const response = await fetch(endpoint(path), {
//       headers: { Accept: "application/json" },
//     });
//     if (!response.ok)
//       throw new Error(`GET ${path} failed with ${response.status}`);
//     return (await response.json()) as T;
//   } catch {
//     return fallback();
//   }
// }

// export async function postJson<T>(
//   path: string,
//   body: unknown,
//   fallback: () => T,
// ): Promise<T> {
//   try {
//     const response = await fetch(endpoint(path), {
//       method: "POST",
//       headers: {
//         "Content-Type": "application/json",
//         Accept: "application/json",
//       },
//       body: JSON.stringify(body),
//     });
//     if (!response.ok)
//       throw new Error(`POST ${path} failed with ${response.status}`);
//     return (await response.json()) as T;
//   } catch {
//     return fallback();
//   }
// }

const API_BASE =
  (import.meta.env.VITE_PORTWATCH_API_BASE as string | undefined)?.replace(
    /\/$/,
    "",
  ) ?? "/api";

function endpoint(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function getJson<T>(path: string, _fallback: () => T): Promise<T> {
  const url = endpoint(path);

  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function postJson<T>(
  path: string,
  body: unknown,
  _fallback: () => T,
): Promise<T> {
  const url = endpoint(path);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`POST ${url} failed with ${response.status}`);
  }

  return (await response.json()) as T;
}