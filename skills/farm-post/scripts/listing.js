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

/** Telegram HTML message for a post. */
function caption(post) {
  const price = [post.price_text, post.unit_price_text].filter(Boolean).join(" · ");
  const tags = (post.tags || []).filter(Boolean).map((t) => "#" + t.replace(/^#/, "").replace(/\s+/g, "")).join(" ");
  const parts = [`<b>${esc(post.title)}</b>` + (price ? `\n${esc(price)}` : ""), esc(post.body), esc(tags)];
  return parts.filter(Boolean).join("\n\n").slice(0, CAPTION_LIMIT);
}

/** Plain text version for copying into any app. */
function plainText(post) {
  const price = [post.price_text, post.unit_price_text].filter(Boolean).join(" · ");
  const tags = (post.tags || []).map((t) => "#" + t.replace(/^#/, "").replace(/\s+/g, "")).join(" ");
  return [post.title + (price ? `\n${price}` : ""), post.body, tags].filter(Boolean).join("\n\n");
}

function makePost({ title, body, tags, note }) {
  if (!title || !body) throw new Error("title and body are required");
  const [price_text, unit_price_text] = parsePrice(note);
  return {
    title: String(title).trim(), body: String(body).trim(),
    tags: Array.isArray(tags) ? tags.map(String) : String(tags || "").split(",").map((t) => t.trim()).filter(Boolean),
    note: note || "", price_text, unit_price_text,
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

/** "TOKEN @channel" -> {token, chat}; anything else -> null. */
function parseSecret(secret) {
  const [token, chat] = String(secret || "").trim().split(/\s+/);
  return token && chat ? { token, chat } : null;
}

async function sendTelegram(fetchFn, { token, chat }, text) {
  // Form-encoded body = "simple" CORS request (no preflight; Telegram answers OPTIONS with 501).
  const body = new URLSearchParams({ chat_id: chat, text, parse_mode: "HTML" });
  const res = await fetchFn(`https://api.telegram.org/bot${token}/sendMessage`, { method: "POST", body });
  const reply = await res.json();
  if (!reply.ok) throw new Error(`Telegram: ${reply.description}`);
}

/** Post every pending record; each is marked published right after its own send. */
async function flush(storage, fetchFn, secret, online) {
  const tg = parseSecret(secret);
  const pending = load(storage).filter((r) => r.status === "pending");
  if (!tg || !online || pending.length === 0) return { sent: 0, pending: pending.length, configured: !!tg };
  let sent = 0;
  for (const r of pending) {
    await sendTelegram(fetchFn, tg, caption(r.post));
    const records = load(storage);
    records.find((x) => x.id === r.id).status = "published";
    save(storage, records);
    sent++;
  }
  return { sent, pending: pending.length - sent, configured: true };
}

if (typeof module !== "undefined") {
  module.exports = { parsePrice, caption, plainText, makePost, load, addRecord, parseSecret, flush, STORAGE_KEY };
}
