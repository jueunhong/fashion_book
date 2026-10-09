// Runway Book - Supabase Edge Function
// 보그 런웨이 페이지를 읽어 DB에 저장한다. vogue.py 의 TypeScript 이식판.
// 모든 요청은 로그인한 사용자의 토큰(Authorization: Bearer <access_token>)이 필요하다.

const VOGUE = "https://www.vogue.com";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const ALLOWED_EMAILS = (Deno.env.get("ALLOWED_EMAILS") ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);

// 토큰으로 사용자를 확인한다 (GoTrue /user). 실패하면 null.
async function currentUser(req: Request): Promise<{ id: string; email: string } | null> {
  const auth = req.headers.get("authorization") ?? "";
  if (!auth.toLowerCase().startsWith("bearer ")) return null;
  const r = await fetch(`${SUPABASE_URL}/auth/v1/user`, { headers: { apikey: ANON_KEY, Authorization: auth } });
  if (!r.ok) return null;
  const u = await r.json();
  if (!u?.id || !u?.email) return null;
  if (ALLOWED_EMAILS.length && !ALLOWED_EMAILS.includes(u.email.toLowerCase())) return null;
  return { id: u.id, email: u.email };
}

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (obj: unknown, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" } });

// ---------------------------------------------------------------- DB (PostgREST)
async function db(path: string, init: RequestInit & { prefer?: string } = {}) {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}`,
      "Content-Type": "application/json", Prefer: init.prefer ?? "return=minimal",
      ...(init.headers ?? {}),
    },
  });
  if (!r.ok) throw new Error(`DB ${r.status}: ${await r.text()}`);
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}
const upsert = (table: string, rows: unknown) =>
  db(table, { method: "POST", body: JSON.stringify(rows), prefer: "resolution=merge-duplicates,return=minimal" });

// ---------------------------------------------------------------- 보그 페이지
async function fetchState(url: string): Promise<any> {
  const r = await fetch(url, { headers: { "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9" } });
  if (!r.ok) throw new Error(`Vogue ${r.status} (${url})`);
  const html = await r.text();
  const m = html.match(/window\.__PRELOADED_STATE__\s*=\s*/);
  if (!m) throw new Error("페이지에서 __PRELOADED_STATE__ 를 찾지 못했습니다: " + url);
  const start = m.index! + m[0].length;
  const end = html.indexOf("</script>", start);
  let text = html.slice(start, end).trim();
  if (text.endsWith(";")) text = text.slice(0, -1);
  return JSON.parse(text);
}

function parsePhoto(url: string): { id: string; file: string } | null {
  const m = url.match(/^https:\/\/assets\.vogue\.com\/photos\/([a-f0-9]+)\/[^/]+\/[^/]+\/(.+)$/);
  return m ? { id: m[1], file: m[2] } : null;
}
function imageFrom(obj: any) {
  const src = obj?.sources?.md ?? obj?.sources?.lg ?? obj?.sources?.sm;
  if (!src?.url) return null;
  const p = parsePhoto(src.url);
  if (!p) return { url: src.url };
  const out: any = { id: p.id, file: p.file };
  if (src.width && src.height) { out.w = src.width; out.h = src.height; }
  return out;
}
function seasonTitle(text: string): string {
  const t = text.trim().toLowerCase().replace("ready-to-wear", "ready_to_wear").replace("pre-fall", "pre_fall");
  return t.split(/[\s-]+/).filter(Boolean).map((w) =>
    w === "ready_to_wear" ? "Ready-to-Wear" : w === "pre_fall" ? "Pre-Fall" : w[0].toUpperCase() + w.slice(1)).join(" ");
}
const ALLOWED = new Set(["p", "em", "strong", "b", "i", "a", "h2", "h3", "h4", "br", "ul", "ol", "li", "blockquote", "span", "div"]);
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" } as any)[c]);
function jsonmlToHtml(node: any): string {
  if (node == null) return "";
  if (typeof node === "string") return esc(node);
  if (Array.isArray(node) && typeof node[0] === "string") {
    const tag = node[0].toLowerCase();
    let rest = node.slice(1), attrs: any = {};
    if (rest.length && rest[0] && typeof rest[0] === "object" && !Array.isArray(rest[0])) { attrs = rest[0]; rest = rest.slice(1); }
    const inner = rest.map(jsonmlToHtml).join("");
    if (!ALLOWED.has(tag)) return inner;
    if (tag === "br") return "<br>";
    let a = "";
    if (tag === "a" && attrs.href) { const h = attrs.href.startsWith("/") ? VOGUE + attrs.href : attrs.href; a = ` href="${esc(h)}" target="_blank" rel="noopener"`; }
    return `<${tag}${a}>${inner}</${tag}>`;
  }
  if (Array.isArray(node)) return node.map(jsonmlToHtml).join("");
  return "";
}
function normalizeShowPath(ref: string): string {
  let s = ref.trim();
  if (s.startsWith("http")) s = new URL(s).pathname;
  s = s.replace(/^\/+|\/+$/g, "");
  if (s.startsWith("fashion-shows/")) s = s.slice("fashion-shows/".length);
  const parts = s.split("/").filter(Boolean);
  if (parts.length < 2) throw new Error("쇼 경로 형식이 아닙니다: " + ref);
  return `/fashion-shows/${parts[0]}/${parts[1]}`;
}

// ---------------------------------------------------------------- 작업
async function fetchShow(ref: string, force: boolean) {
  const path = normalizeShowPath(ref);
  const [season, brand] = path.split("/").slice(2);
  const key = `${season}__${brand}`;
  if (!force) {
    const ex = await db(`shows?key=eq.${encodeURIComponent(key)}&select=key,looks`, { prefer: "return=representation" });
    if (ex?.length) return { key, looks: ex[0].looks, existed: true };
  }
  const state = await fetchState(VOGUE + path);
  const t = state.transformed ?? {};
  const content = t.runwayShowContent ?? {};
  const header = content.sectionHeader ?? {};
  const strip = (s: string) => (s ?? "").replace(/<[^>]+>/g, "");
  const galleries: any[] = [];
  for (const g of t.runwayShowGalleries?.galleries ?? []) {
    const items: any[] = [];
    (g.items ?? []).forEach((it: any, i: number) => {
      const img = imageFrom(it.image);
      if (img) items.push({ n: i + 1, caption: it.caption || `Look ${i + 1}`, ...img });
    });
    if (items.length) galleries.push({ id: g.id || `gallery-${galleries.length}`, title: g.title || "Gallery", items });
  }
  if (!galleries.length) throw new Error("룩 사진 목록이 비어 있습니다: " + path);
  const authors = (content.contributors?.author?.items ?? []).map((a: any) => a.name).filter(Boolean);
  const cover = galleries[0].items[0];
  const counts: Record<string, number> = {};
  for (const g of galleries) counts[g.title] = g.items.length;
  const row = {
    key, url: VOGUE + path, season, season_name: seasonTitle(strip(header.subHed) || season),
    brand, brand_name: strip(header.hed) || content.brand || brand,
    designers: content.designersDek ?? "", event_date: content.eventDate ?? "", pub_date: content.pubDate ?? "",
    authors, review_html: jsonmlToHtml(content.review), cover: { id: cover.id, file: cover.file },
    galleries, looks: galleries.reduce((a, g) => a + g.items.length, 0), counts, fetched_at: new Date().toISOString(),
  };
  await upsert("shows", row);
  return { key, looks: row.looks, existed: false, counts };
}

async function fetchSeason(slug: string) {
  slug = slug.replace(/^\/+|\/+$/g, "").split("/").pop()!;
  const state = await fetchState(`${VOGUE}/fashion-shows/${slug}`);
  const sc = state.transformed?.runwaySeasonContent ?? {};
  const covers: Record<string, any> = {};
  for (const c of sc.curatedShows ?? []) { const img = imageFrom(c.image); if (img && c.url) covers[c.url.replace(/\/+$/, "").split("/").pop()] = img; }
  const shows: any[] = [];
  for (const group of sc.allShows ?? []) for (const link of group.links ?? []) {
    const url: string = link.url ?? "";
    if (!url.startsWith("/fashion-shows/")) continue;
    const parts = url.replace(/^\/+|\/+$/g, "").split("/");
    if (parts.length < 3) continue;
    const s: any = { name: link.text || parts[2], brand: parts[2], path: `/fashion-shows/${parts[1]}/${parts[2]}` };
    if (covers[parts[2]]) s.cover = covers[parts[2]];
    shows.push(s);
  }
  const row = { slug, name: sc.name || seasonTitle(slug), shows, fetched_at: new Date().toISOString() };
  await upsert("seasons", row);
  return row;
}

async function fetchDesigner(slug: string) {
  slug = slug.replace(/^\/+|\/+$/g, "").split("/").pop()!;
  const state = await fetchState(`${VOGUE}/fashion-shows/designer/${slug}`);
  const dc = state.transformed?.runwayDesignerContent ?? {};
  const collections: any[] = [];
  for (const c of dc.designerCollections ?? []) {
    const parts = (c.url ?? "").replace(/^\/+|\/+$/g, "").split("/");
    if (parts.length < 3) continue;
    const item: any = { name: c.hed || seasonTitle(parts[1]), season: parts[1], path: `/fashion-shows/${parts[1]}/${parts[2]}` };
    const img = imageFrom(c.image); if (img) item.cover = img;
    collections.push(item);
  }
  const row = { slug, name: dc.name || slug, bio_html: jsonmlToHtml(dc.body), collections, fetched_at: new Date().toISOString() };
  await upsert("designers", row);
  return row;
}

// ---------------------------------------------------------------- HTTP
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  const user = await currentUser(req);
  if (!user) return json({ error: "로그인이 필요합니다" }, 401);
  let body: any;
  try { body = await req.json(); } catch { return json({ error: "JSON body 필요" }, 400); }
  try {
    switch (body.action) {
      case "ping": return json({ ok: true, email: user.email });
      case "show": return json(await fetchShow(body.ref, !!body.force));
      case "season": return json(await fetchSeason(body.slug));
      case "designer": return json(await fetchDesigner(body.slug));
      case "delete":
        await db(`shows?key=eq.${encodeURIComponent(body.key)}`, { method: "DELETE" });
        await db(`favorites?show_key=eq.${encodeURIComponent(body.key)}`, { method: "DELETE" });
        return json({ ok: true });
      case "fav": {
        const f = body.fav;
        const id = `${user.id}|${f.id}`;   // 사용자별로 분리
        if (body.op === "remove") { await db(`favorites?id=eq.${encodeURIComponent(id)}&user_id=eq.${user.id}`, { method: "DELETE" }); return json({ ok: true }); }
        await upsert("favorites", { id, user_id: user.id, show_key: f.showKey, gid: f.gid, n: f.n, item: f.it, brand: f.brand ?? "", season: f.season ?? "" });
        return json({ ok: true });
      }
      default: return json({ error: "알 수 없는 action" }, 400);
    }
  } catch (e) { return json({ error: String((e as Error).message ?? e) }, 500); }
});
