// Run: node --test tests/
const test = require("node:test");
const assert = require("node:assert");
const L = require("../skills/farm-post/scripts/listing.js");

const CASES = {
  "10 kg 12 Euro": ["€12.00", "€1.20/kg"],
  "10 eggs €3": ["€3.00", "€0.30/piece"],
  "500 g €2.50": ["€2.50", "€5.00/kg"],
  "3,50 € for 10 pieces": ["€3.50", "€0.35/piece"],
  "$5 a dozen eggs": ["$5.00", ""],
  "1 dozen $6": ["$6.00", "$0.50/piece"],
  "2 lb honey 9 dollars": ["$9.00", "$4.50/lb"],
  "£4 for 1 l of milk": ["£4.00", "£4.00/l"],
  "5 kg 1,000 KES": ["KES 1000.00", "KES 200.00/kg"],
  "2 kg ₹180": ["₹180.00", "₹90.00/kg"],
  "fresh from the field, 5 kg": ["", ""],
  "12 Euro": ["€12.00", ""],
  "": ["", ""],
};

// Same cases as tests/test_price.py, so the phone skill and the laptop version agree.
test("parsePrice matches the Python parser", () => {
  for (const [note, expected] of Object.entries(CASES)) assert.deepStrictEqual(L.parsePrice(note), expected, note);
});

function memStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

const POST = { title: "Warm Scarf <handmade>", body: "Soft wool.", tags: ["hand knitted", "#wool"], note: "scarf $25" };

test("makePost computes price and caption escapes HTML", () => {
  const p = L.makePost(POST);
  assert.strictEqual(p.price_text, "$25.00");
  const c = L.caption(p);
  assert.ok(c.startsWith("<b>Warm Scarf &lt;handmade&gt;</b>\n$25.00"));
  assert.ok(c.endsWith("#handknitted #wool"));
});

test("makePost requires title and body", () => {
  assert.throws(() => L.makePost({ title: "", body: "x" }));
});

test("offline: saved and kept pending", async () => {
  const s = memStorage();
  L.addRecord(s, L.makePost(POST));
  const fetchFn = () => assert.fail("must not call fetch when offline");
  assert.deepStrictEqual(await L.flush(s, fetchFn, "T @shop", false), { sent: 0, pending: 1, configured: true });
});

test("no secret: nothing is sent", async () => {
  const s = memStorage();
  L.addRecord(s, L.makePost(POST));
  assert.deepStrictEqual(await L.flush(s, null, "", true), { sent: 0, pending: 1, configured: false });
});

test("online: posts form-encoded to Telegram and marks published", async () => {
  const s = memStorage();
  L.addRecord(s, L.makePost(POST));
  const calls = [];
  const fetchFn = async (url, opts) => { calls.push([url, opts]); return { json: async () => ({ ok: true }) }; };
  assert.deepStrictEqual(await L.flush(s, fetchFn, " T  @shop ", true), { sent: 1, pending: 0, configured: true });
  assert.strictEqual(calls[0][0], "https://api.telegram.org/botT/sendMessage");
  assert.ok(calls[0][1].body instanceof URLSearchParams);
  assert.strictEqual(calls[0][1].body.get("chat_id"), "@shop");
  assert.strictEqual(L.load(s)[0].status, "published");
});

test("failure midway keeps the unsent one pending", async () => {
  const s = memStorage();
  L.addRecord(s, L.makePost(POST));
  L.addRecord(s, L.makePost(POST));
  let n = 0;
  const fetchFn = async () => ({ json: async () => (n++ === 0 ? { ok: true } : { ok: false, description: "Bad Request" }) });
  await assert.rejects(L.flush(s, fetchFn, "T @shop", true), /Bad Request/);
  assert.deepStrictEqual(L.load(s).map((r) => r.status), ["published", "pending"]);
});
