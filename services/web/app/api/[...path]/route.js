// Runtime proxy: forwards /api/* to the backend, reading API_URL on every request
// (unlike next.config rewrites, which are baked at build time). Cloud Run sets
// API_URL to the deployed API service URL; locally it defaults to :8000.
export const dynamic = "force-dynamic";

function apiBase() {
  return process.env.API_URL || "http://127.0.0.1:8000";
}

async function proxy(request, { params }) {
  const { path = [] } = await params;
  const search = new URL(request.url).search;
  const target = `${apiBase()}/api/${path.join("/")}${search}`;

  const init = { method: request.method, headers: {} };
  const ct = request.headers.get("content-type");
  if (ct) init.headers["content-type"] = ct;
  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = await request.text();
  }

  try {
    const resp = await fetch(target, init);
    const body = await resp.arrayBuffer();
    const headers = new Headers();
    const rct = resp.headers.get("content-type");
    if (rct) headers.set("content-type", rct);
    return new Response(body, { status: resp.status, headers });
  } catch (e) {
    return new Response(
      JSON.stringify({ detail: "proxy error", target, error: String(e) }),
      { status: 502, headers: { "content-type": "application/json" } });
  }
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
};
