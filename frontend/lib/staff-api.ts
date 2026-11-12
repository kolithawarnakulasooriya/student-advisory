import createClient from "openapi-fetch";
import type { paths } from "./api-types";
import { ApiError, get } from "./api";

export const staffApi = createClient<paths>({
  credentials: "same-origin",
  cache: "no-store",
});
staffApi.use({
  async onRequest({ request }) {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const csrf = await get("/api/v1/auth/csrf");
      request.headers.set("X-CSRF-Token", csrf.csrf_token);
      if (!request.headers.has("Idempotency-Key"))
        request.headers.set("Idempotency-Key", crypto.randomUUID());
    }
    return request;
  },
  async onResponse({ response }) {
    if (!response.ok) {
      const error = await response
        .clone()
        .json()
        .catch(() => ({}));
      throw new ApiError(
        response.status,
        error.code ?? "UNAVAILABLE",
        error.message ?? "Service unavailable. Retry.",
      );
    }
  },
});
export const revision = (version: number) => ({ "If-Match": `"${version}"` });
