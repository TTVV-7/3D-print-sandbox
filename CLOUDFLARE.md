# The sandbox on Cloudflare

`wrangler.jsonc` + `cloudflare/worker.js` serve `public/` from Cloudflare and
forward `/api/model` and `/api/case` to the Python functions on Vercel. The
generators can't move to Cloudflare as-is: they need numpy, trimesh, shapely
and manifold3d, and a mesh can outlast a Worker's CPU limit. Nothing Vercel
uses has changed.

Setup:

1. Cloudflare dashboard → Workers & Pages → Create → Import a repository →
   this repo and branch. No build command; deploy command `npx wrangler deploy`.
2. Set `VERCEL_API_ORIGIN` (in `wrangler.jsonc`) to the Vercel deployment that
   should do the generating.
3. The Vercel project is behind Vercel Authentication, so the Worker needs a
   way in: Vercel → project → Settings → Deployment Protection → Protection
   Bypass for Automation → create a secret, then add it to the Worker as the
   secret `VERCEL_BYPASS_SECRET`.

Model data still flows out of Vercel's functions, so this doesn't reduce
Vercel usage much on its own; it gets the pages onto Cloudflare and leaves the
door open to moving the lighter generators over later.
