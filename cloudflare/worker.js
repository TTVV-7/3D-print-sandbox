// The Cloudflare front for the sandbox: the pages in public/ are served from
// Cloudflare's edge, and /api/model and /api/case are forwarded to the Python
// functions still running on Vercel.
//
// The generators stay on Vercel because they need numpy, trimesh, shapely and
// manifold3d, which Cloudflare's Python Workers can't run reliably, and a
// mesh can take longer than a Worker's CPU limit. Nothing in api/, src/ or
// vercel.json changes, so the Vercel deployment keeps working on its own.
//
// Settings (wrangler.jsonc vars, or the dashboard):
//   VERCEL_API_ORIGIN     the Vercel deployment to forward to, e.g.
//                         https://3-d-print-sandbox.vercel.app
//   VERCEL_BYPASS_SECRET  (secret) Vercel's "Protection Bypass for Automation"
//                         secret, needed while the Vercel project sits behind
//                         Vercel Authentication

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);

    const origin = (env.VERCEL_API_ORIGIN || "").replace(/\/$/, "");
    if (!origin) {
      return Response.json({ error: "VERCEL_API_ORIGIN is not set" }, { status: 503 });
    }

    const headers = new Headers(request.headers);
    headers.delete("host");
    if (env.VERCEL_BYPASS_SECRET) headers.set("x-vercel-protection-bypass", env.VERCEL_BYPASS_SECRET);

    const hasBody = !["GET", "HEAD"].includes(request.method);
    return fetch(`${origin}${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      redirect: "manual",
    });
  },
};
