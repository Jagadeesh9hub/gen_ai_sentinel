// Same-origin by default: fetches go to /api/* and next.config rewrites proxy
// them to the backend (local :8000, or API_URL on Cloud Run). Override with
// NEXT_PUBLIC_API_BASE only if you want the browser to call the API directly.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export async function getJSON(path) {
  const r = await fetch(API_BASE + path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export async function postJSON(path, body) {
  const r = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
