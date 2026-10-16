import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path.some(part => part === ".." || part === ".")) return new Response(null, { status: 400 });
  const upstream = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
  const target = `${upstream.replace(/\/$/, "")}/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  for (const key of ["content-type", "authorization", "cookie", "origin", "x-request-id"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD" && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > 1024 * 1024) {
        await reader.cancel();
        return Response.json({ detail: "Request exceeds the one-megabyte limit" }, { status: 413 });
      }
      chunks.push(value);
    }
    const combined = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { combined.set(chunk, offset); offset += chunk.length; }
    body = combined.buffer;
  }
  try {
    const response = await fetch(target, { method: request.method, headers, body,
      redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(18000) });
    const outgoing = new Headers(response.headers);
    for (const name of ["content-encoding", "content-length", "transfer-encoding", "set-cookie"]) outgoing.delete(name);
    for (const cookie of response.headers.getSetCookie()) outgoing.append("set-cookie", cookie);
    outgoing.set("cache-control", "no-store");
    return new Response(response.body, { status: response.status, headers: outgoing });
  } catch {
    return Response.json({ detail: "The API is unavailable. Check that the backend is running, then retry." }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as PATCH, proxy as OPTIONS };
