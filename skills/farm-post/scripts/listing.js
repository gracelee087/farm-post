// Farm Post logic shared by index.html (skill runner) and node tests.
// Prices are computed here from the seller's note, never by the model.

const STORAGE_KEY = "farm-post-outbox";
const CAPTION_LIMIT = 4096; // Telegram sendMessage text limit

const NUM = String.raw`(\d+(?:[.,]\d+)?)`;
const SYMBOLS = "€$£₹¥₱₦₩₺₫₴₪";
const WORDS = {
  eur: "€", euro: "€", euros: "€", usd: "$", dollar: "$", dollars: "$",
  gbp: "£", pound: "£", pounds: "£", inr: "₹", rupee: "₹", rupees: "₹",
};
const PRICE_RE = new RegExp(String.raw`(?:([${SYMBOLS}])\s*${NUM})|(?:${NUM}\s*(?:([${SYMBOLS}])|([A-Za-z]{3,7})\b))`, "g");
const QTY_RE = new RegExp(String.raw`${NUM}\s*(kg|g|lb|lbs|ml|l|liter|litre|pieces|piece|pcs|eggs|egg|dozen)\b`, "i");
const PIECE = ["piece", 1];
const UNITS = {
  kg: ["kg", 1], g: ["kg", 1000], lb: ["lb", 1], lbs: ["lb", 1], l: ["l", 1], liter: ["l", 1],
  litre: ["l", 1], ml: ["l", 1000], pieces: PIECE, piece: PIECE, pcs: PIECE, eggs: PIECE, egg: PIECE,
  dozen: ["piece", 1 / 12],
};

function num(s) {
  // "1,000" -> 1000 (thousands separator), "3,50" -> 3.5 (decimal comma)
  if (/^\d+,\d{3}$/.test(s)) return parseFloat(s.replace(",", ""));
  return parseFloat(s.replace(",", "."));
}

function findPrice(note) {
  for (const m of note.matchAll(PRICE_RE)) {
    if (m[1]) return [num(m[2]), m[1]];
    if (m[4]) return [num(m[3]), m[4]];
    const word = m[5];
    if (WORDS[word.toLowerCase()]) return [num(m[3]), WORDS[word.toLowerCase()]];
    if (word.length === 3 && word === word.toUpperCase()) return [num(m[3]), word + " "];
  }
  return null;
}

/** Returns [priceText, unitPriceText] from the note only. */
function parsePrice(note) {
  const found = findPrice(note || "");
  if (!found) return ["", ""];
  const [price, cur] = found;
  const priceText = `${cur}${price.toFixed(2)}`;
  const q = (note || "").match(QTY_RE);
  if (!q || num(q[1]) === 0) return [priceText, ""];
  const [unit, factor] = UNITS[q[2].toLowerCase()];
  return [priceText, `${cur}${(price / (num(q[1]) / factor)).toFixed(2)}/${unit}`];
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function stockText(post) {
  if (post.stock === 0) return "❌ SOLD OUT";
  return typeof post.stock === "number" ? `Available: ${post.stock}` : "";
}

function tagText(post) {
  return (post.tags || []).filter(Boolean).map((t) => "#" + t.replace(/^#/, "").replace(/\s+/g, "")).join(" ");
}

/** Telegram HTML message for a post. */
function caption(post) {
  const price = [post.price_text, post.unit_price_text].filter(Boolean).join(" · ");
  const head = [`<b>${esc(post.title)}</b>`, esc(price), esc(stockText(post))].filter(Boolean).join("\n");
  return [head, esc(post.body), esc(tagText(post))].filter(Boolean).join("\n\n").slice(0, CAPTION_LIMIT);
}

/** Plain text version for copying into any app. */
function plainText(post) {
  const price = [post.price_text, post.unit_price_text].filter(Boolean).join(" · ");
  const head = [post.title, price, stockText(post)].filter(Boolean).join("\n");
  return [head, post.body, tagText(post)].filter(Boolean).join("\n\n");
}

function makePost({ title, body, tags, note, stock }) {
  if (!title || !body) throw new Error("title and body are required");
  const [price_text, unit_price_text] = parsePrice(note);
  return {
    title: String(title).trim(), body: String(body).trim(),
    tags: Array.isArray(tags) ? tags.map(String) : String(tags || "").split(",").map((t) => t.trim()).filter(Boolean),
    note: note || "", price_text, unit_price_text,
    stock: Number.isInteger(stock) && stock >= 0 ? stock : null,
  };
}

// ---- outbox (stored on the phone) ----

function load(storage) {
  try { return JSON.parse(storage.getItem(STORAGE_KEY) || "[]"); } catch (e) { return []; }
}

function save(storage, records) {
  storage.setItem(STORAGE_KEY, JSON.stringify(records));
}

function addRecord(storage, post, now = new Date()) {
  const records = load(storage);
  const record = { id: now.getTime().toString(36) + Math.random().toString(36).slice(2, 6),
                   created_at: now.toISOString(), status: "pending", post };
  records.push(record);
  save(storage, records);
  return record;
}

/** Find a listing by id, else the newest whose title contains all given words, else the newest. */
function findRecord(records, ref) {
  const byId = records.find((r) => r.id === ref);
  if (byId) return byId;
  const words = String(ref || "").toLowerCase().split(/\s+/).filter(Boolean);
  const newest = [...records].reverse();
  return newest.find((r) => words.length && words.every((w) => r.post.title.toLowerCase().includes(w))) || newest[0];
}

/** Update stock with {sold: n} | {remaining: n} | {sold_out: true}; a posted listing is marked for a Telegram edit. */
function updateStock(storage, { listing, sold, remaining, sold_out }) {
  const records = load(storage);
  const r = findRecord(records, listing);
  if (!r) throw new Error("There are no listings yet.");
  const p = r.post;
  if (sold_out) p.stock = 0;
  else if (Number.isInteger(remaining) && remaining >= 0) p.stock = remaining;
  else if (Number.isInteger(sold) && sold > 0) {
    if (typeof p.stock !== "number") throw new Error(`I don't know how many "${p.title}" you had. Tell me how many are left.`);
    p.stock = Math.max(0, p.stock - sold);
  } else throw new Error("Tell me how many were sold, how many are left, or that it is sold out.");
  if (r.message_id) r.needs_edit = true;
  save(storage, records);
  return r;
}

/** "TOKEN @channel" -> {token, chat}; anything else -> null. */
function parseSecret(secret) {
  const [token, chat] = String(secret || "").trim().split(/\s+/);
  return token && chat ? { token, chat } : null;
}

async function telegram(fetchFn, { token }, method, params) {
  // Form-encoded body = "simple" CORS request (no preflight; Telegram answers OPTIONS with 501).
  const res = await fetchFn(`https://api.telegram.org/bot${token}/${method}`,
                            { method: "POST", body: new URLSearchParams(params) });
  const reply = await res.json();
  if (!reply.ok) throw new Error(`Telegram: ${reply.description}`);
  return reply.result;
}

/** Post every pending record and apply stock edits; each record is saved right after its own call. */
async function flush(storage, fetchFn, secret, online) {
  const tg = parseSecret(secret);
  const waiting = () => load(storage).filter((r) => r.status === "pending").length;
  const todo = load(storage).filter((r) => r.status === "pending" || r.needs_edit);
  if (!tg || !online || todo.length === 0) return { sent: 0, edited: 0, pending: waiting(), configured: !!tg };
  let sent = 0, edited = 0;
  for (const r of todo) {
    const text = caption(r.post);
    let messageId = r.message_id;
    if (r.status === "pending") {
      messageId = (await telegram(fetchFn, tg, "sendMessage", { chat_id: tg.chat, text, parse_mode: "HTML" })).message_id;
      sent++;
    } else {
      await telegram(fetchFn, tg, "editMessageText", { chat_id: tg.chat, message_id: r.message_id, text, parse_mode: "HTML" });
      edited++;
    }
    const records = load(storage);
    Object.assign(records.find((x) => x.id === r.id), { status: "published", message_id: messageId, needs_edit: false });
    save(storage, records);
  }
  return { sent, edited, pending: waiting(), configured: true };
}

// ---- market prices (needs internet) ----

// Our small proxy on Render (price-proxy/ in the repo): SerpApi blocks browser calls to protect the key.
const PRICE_URL = "https://farm-post-price-proxy.onrender.com";

/** Online-shop prices for similar items, as a short sentence for the model. */
async function marketPrice(fetchFn, query, country = "us") {
  const url = `${PRICE_URL}/price?` + new URLSearchParams({ q: String(query).slice(0, 100), gl: country || "us" });
  const res = await fetchFn(url); // simple GET: no CORS preflight; the free server may take ~1 min to wake up
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  if (!data.count) return `No online prices found for "${data.query}".`;
  const cur = data.currency_hint || "";
  const money = (x) => `${cur}${Number(x).toFixed(2)}`;
  const examples = data.examples.slice(0, 3).map((e) => `${e.title} (${e.price}, ${e.source})`).join("; ");
  return `Online shops (${data.gl.toUpperCase()}), ${data.count} offers for "${data.query}": ` +
    `${money(data.min)} to ${money(data.max)}, typical ${money(data.median)}. Examples: ${examples}.`;
}

if (typeof module !== "undefined") {
  module.exports = { parsePrice, caption, plainText, makePost, load, addRecord, updateStock, parseSecret, flush,
                     marketPrice, STORAGE_KEY, PRICE_URL };
}
