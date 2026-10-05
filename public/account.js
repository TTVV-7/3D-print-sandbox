/* Accounts: sign in with Google, and every file you download is remembered.

   Supabase does both halves -- the Google sign-in and a `generations` table
   (supabase/schema.sql) that row-level security keeps to its owner -- so
   there is no server of our own to run and the Python functions stay as they
   are.  What is kept is the form, not the file: the generators rebuild the
   same part from the same inputs, so a row is a few kB of settings (more with
   an uploaded logo) and opening it puts them back in the boxes.

   Off until public/accounts.json names a project: with no URL and key there,
   the sign-in button never shows and the page is exactly as it was.

   A classic script, loaded after the page's own, so it shares that script's
   top-level names: $, FIELDS, COLOURS, formParams, slotMat, rebuild and the
   rest. */
"use strict";
(async () => {
  let cfg;
  try {
    const r = await fetch("/accounts.json");
    cfg = r.ok ? await r.json() : null;
  } catch (e) { cfg = null; }
  if (!cfg || !cfg.supabase_url || !cfg.supabase_anon_key) return;

  await new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.117.2/dist/umd/supabase.js";
    s.onload = ok;
    s.onerror = fail;
    document.head.append(s);
  }).catch(() => null);
  if (!window.supabase) return;
  const db = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

  const bar = $("account"), signIn = $("sign_in"), who = $("signed_in"), list = $("history_list");
  const dlg = $("history");
  let user = null, lastSaved = "";

  const KIND_NAMES = { card: "Logo card", name: "Name keyring", pet: "Pet tag",
                       sign: "Sign", stencil: "Stencil", fob: "Fob" };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function shown() {
    bar.hidden = false;
    signIn.hidden = !!user;
    who.hidden = !user;
    if (user) $("signed_name").textContent = user.user_metadata?.full_name || user.email || "Signed in";
  }

  db.auth.onAuthStateChange((_event, session) => { user = session?.user || null; shown(); });
  user = (await db.auth.getSession()).data.session?.user || null;
  shown();

  signIn.addEventListener("click", () => db.auth.signInWithOAuth({
    provider: "google", options: { redirectTo: location.origin + location.pathname },
  }));
  $("sign_out").addEventListener("click", async () => { await db.auth.signOut(); dlg.close(); });

  /* The page calls this after a download comes back.  The same settings
     downloaded twice -- the 3MF and then the STL -- are one row. */
  window.remember = async (params, format) => {
    if (!user) return;
    const kept = { ...params };
    delete kept.format;
    delete kept.gzip;
    const key = JSON.stringify(kept);
    if (key === lastSaved) return;
    lastSaved = key;
    const title = stem().replace(/_/g, " ");
    const { error } = await db.from("generations").insert({ site: location.hostname, kind: kept.kind, title, format, params: kept });
    if (error) { lastSaved = ""; console.warn("history not saved:", error.message); }
  };

  async function load() {
    list.innerHTML = `<p class="hint">Loading&hellip;</p>`;
    const { data, error } = await db.from("generations")
      .select("id, kind, title, format, created_at")
      .order("created_at", { ascending: false }).limit(100);
    if (error) { list.innerHTML = `<p class="hint">Could not load your history &mdash; ${esc(error.message)}</p>`; return; }
    if (!data.length) {
      list.innerHTML = `<p class="hint">Nothing yet. Every file you download while signed in shows up here.</p>`;
      return;
    }
    list.replaceChildren(...data.map(row => {
      const li = document.createElement("div");
      li.className = "past";
      const when = new Date(row.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
      li.innerHTML = `<div><b>${esc(row.title)}</b>
        <span>${esc(KIND_NAMES[row.kind] || row.kind)} &middot; ${esc((row.format || "").toUpperCase())} &middot; ${esc(when)}</span></div>
        <button type="button" class="button neutral">Open</button>
        <button type="button" class="button subtle" aria-label="Delete ${esc(row.title)}">&times;</button>`;
      const [open, del] = li.querySelectorAll("button");
      open.addEventListener("click", () => reopen(row.id));
      del.addEventListener("click", async () => {
        if (!confirm(`Delete “${row.title}” from your history?`)) return;
        const { error } = await db.from("generations").delete().eq("id", row.id);
        if (!error) li.remove();
      });
      return li;
    }));
  }

  /* Put a saved row back in the form: the shape first, through its tile so
     everything that hangs off picking a shape runs, then every box, then the
     uploads and the colours, which the shape's own defaults would otherwise
     have overwritten. */
  async function reopen(id) {
    const { data, error } = await db.from("generations").select("params").eq("id", id).single();
    if (error) { alert(`Could not open it: ${error.message}`); return; }
    const p = data.params;
    const tile = document.querySelector(`.tile[data-kind="${p.kind}"]`);
    if (tile) tile.click();
    const set = (el, v, prop = "value") => {
      if (!el || v === undefined || v === null) return;
      el[prop] = v;
      el.dispatchEvent(new Event("input"));
      el.dispatchEvent(new Event("change"));
    };
    for (const f of FIELDS) if (f !== "kind") set($(f), p[f]);
    set($("lid"), !!p.lid, "checked");
    set($("placeholder"), p.placeholder === "box", "checked");
    for (const id of ["outline", "pet_border", "pet_nfc", "card_bg", "card_holes",
                      "card_nfc", "card_both", "qr"])
      set($(id), !!p[id], "checked");
    set($("card_stepped"), !!p.card_rises, "checked");
    if (p.card_rises) for (const slot of STEP_SLOTS) set($(`card_rise_${slot}`), p.card_rises[slot]);

    logoText = p.logo || "";
    if (["stencil", "sign"].includes(p.kind)) stencilSvg = p.design || "";
    else designText = p.design || "";
    if (p.kind === "card" && p.art) {
      artData = p.art;
      artName = (p.name || "logo");
      $("art_note").textContent = "The logo from your history. Pick another to replace it.";
    }
    // The saved colours are the ones to keep, not the logo's fresh ones.
    artFresh = false;
    (p.colours || []).forEach((c, i) => { if (COLOURS[i]) $(COLOURS[i]).value = c; });
    (p.filaments || []).forEach((f, i) => { if (COLOURS[i] && f.material) slotMat[COLOURS[i]] = f.material; });
    spoolsChosen();
    clearTimeout(pending);
    rebuild();
    dlg.close();
  }

  $("history_open").addEventListener("click", () => { dlg.showModal(); load(); });
  dlg.querySelector(".close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });
})();
