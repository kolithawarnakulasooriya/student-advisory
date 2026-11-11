import type { components, paths } from "./api-types";
export type Me = components["schemas"]["MeOut"];
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
type Route = keyof paths;
type GetRoute = {
  [P in Route]: paths[P] extends { get: unknown } ? P : never;
}[Route];
type PostRoute = {
  [P in Route]: paths[P] extends { post: unknown } ? P : never;
}[Route];
type GetResult<P extends GetRoute> = paths[P] extends {
  get: { responses: { 200: { content: { "application/json": infer T } } } };
}
  ? T
  : never;
type PostBody<P extends PostRoute> = paths[P] extends {
  post: { requestBody: { content: { "application/json": infer T } } };
}
  ? T
  : undefined;

type PostResult<P extends PostRoute> = paths[P] extends {
  post: { responses: infer R };
}
  ? R extends { 200: { content: { "application/json": infer T } } }
    ? T
    : R extends { 201: { content: { "application/json": infer T } } }
      ? T
      : never
  : never;

async function read<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok)
    throw new ApiError(
      response.status,
      data.code ?? "UNAVAILABLE",
      data.message ?? "Service unavailable. Retry.",
    );
  return data as T;
}
export async function get<P extends GetRoute>(
  path: P,
  query = "",
): Promise<GetResult<P>> {
  return read<GetResult<P>>(
    await fetch(path + query, {
      credentials: "same-origin",
      cache: "no-store",
    }),
  );
}
export async function post<P extends PostRoute>(
  path: P,
  body?: PostBody<P>,
): Promise<PostResult<P>> {
  const csrf = await get("/api/v1/auth/csrf");
  return read<PostResult<P>>(
    await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf.csrf_token,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}
