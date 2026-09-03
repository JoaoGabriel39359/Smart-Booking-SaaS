const TOKEN_KEY = "agenda_token";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export const auth = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

function extractMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (payload && typeof payload === "object") {
    const value = payload as Record<string, unknown>;
    if (typeof value.detail === "string") return value.detail;
    if (typeof value.message === "string") return value.message;
    if (typeof value.msg === "string") return value.msg;
  }
  return fallback;
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  protectedRoute = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  const token = auth.get();

  if (!(options.body instanceof FormData) && options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (protectedRoute && token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(path, { ...options, headers });
  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    if (response.status === 401 && protectedRoute) {
      auth.clear();
      if (location.pathname !== "/login") location.assign("/login");
    }
    throw new ApiError(
      extractMessage(payload, `Erro ${response.status} ao acessar o servidor.`),
      response.status,
    );
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, protectedRoute = true) =>
    request<T>(path, {}, protectedRoute),
  post: <T>(path: string, body?: unknown, protectedRoute = true) =>
    request<T>(
      path,
      {
        method: "POST",
        body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
      },
      protectedRoute,
    ),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string) => request<T>(path, { method: "PATCH" }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function query(path: string, params: Record<string, string | number | boolean | null | undefined>) {
  const url = new URL(path, location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return `${url.pathname}${url.search}`;
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Ocorreu um erro inesperado.";
}
