// Tests de comportamiento para W-201..W-203 (W-204 se retiró del benchmark en v4; su test queda por si se reactiva). Uso: node tests/run.js W-20x <workDir>
"use strict";
const path = require("path");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const task = process.argv[2];
const work = path.resolve(process.argv[3]);
const out = path.join(work, "out");
const results = {};
const notes = [];

async function check(name, fn) {
  try {
    results[name] = !!(await fn());
  } catch (e) {
    results[name] = false;
    notes.push(`${name}: ${e && e.message ? e.message : e}`);
  }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Errores no manejados del código evaluado: se registran pero no tumban el proceso.
let unhandled = 0;
process.on("unhandledRejection", (e) => { unhandled++; if (unhandled <= 3) notes.push("promesa rechazada sin manejar: " + (e && e.message ? e.message : e)); });
process.on("uncaughtException", (e) => { unhandled++; if (unhandled <= 3) notes.push("excepción no capturada: " + (e && e.message ? e.message : e)); });
const req = (rel) => require(path.join(out, rel));

// ---------------------------------------------------------------- W-201
async function w201() {
  const cart = req("lib/cart.js");
  const P = (id, cents, cat = "guitars") => ({ id, name: "P" + id, category: cat, priceCents: cents });
  const build = (items) => items.reduce((c, [p, q]) => cart.addToCart(c, p, q), cart.createCart());
  const allInt = (t) => Object.values(t).every(Number.isInteger);

  await check("addToCart no muta el carrito original", () => {
    const c0 = cart.createCart();
    const c1 = cart.addToCart(c0, P("a", 100), 1);
    return c0.lines.length === 0 && c1 !== c0 && c1.lines.length === 1;
  });
  await check("mismo producto suma cantidad (sin mutar la línea anterior)", () => {
    const c1 = cart.addToCart(cart.createCart(), P("a", 100), 1);
    const c2 = cart.addToCart(c1, P("a", 100), 2);
    return c2.lines.length === 1 && c2.lines[0].quantity === 3 && c1.lines[0].quantity === 1;
  });
  await check("cantidades inválidas se ignoran (1.5, NaN, 0, -1, Infinity)", () => {
    let c = cart.addToCart(cart.createCart(), P("a", 100), 1);
    for (const q of [1.5, NaN, 0, -1, Infinity]) c = cart.addToCart(c, P("b", 100), q);
    return c.lines.length === 1 && c.lines[0].quantity === 1;
  });
  await check("10+20+30 centavos = 60 exactos (enteros)", () => {
    const t = cart.cartTotals(build([[P("a", 10), 1], [P("b", 20), 1], [P("c", 30), 1]]));
    return t.subtotalCents === 60 && t.totalCents === 659 && allInt(t);
  });
  await check("cupón 10% sobre $30: no descuenta el envío", () => {
    const t = cart.cartTotals(build([[P("a", 3000), 1]]), { code: "X", percentOff: 10 });
    return t.subtotalCents === 3000 && t.discountCents === 300 && t.shippingCents === 599 && t.totalCents === 3299;
  });
  await check("cupón 10% sobre $52: el envío se calcula con el subtotal descontado", () => {
    const t = cart.cartTotals(build([[P("a", 5200), 1]]), { code: "X", percentOff: 10 });
    return t.discountCents === 520 && t.shippingCents === 599 && t.totalCents === 5279;
  });
  await check("cupón 10% sobre $60: envío gratis", () => {
    const t = cart.cartTotals(build([[P("a", 6000), 1]]), { code: "X", percentOff: 10 });
    return t.discountCents === 600 && t.shippingCents === 0 && t.totalCents === 5400;
  });
  await check("umbral exacto: $50 gratis, $49.99 paga envío", () => {
    const a = cart.cartTotals(build([[P("a", 5000), 1]]));
    const b = cart.cartTotals(build([[P("a", 4999), 1]]));
    return a.shippingCents === 0 && a.totalCents === 5000 && b.shippingCents === 599 && b.totalCents === 5598;
  });
  await check("descuento redondeado al centavo (15% de 3333 = 500)", () => {
    const t = cart.cartTotals(build([[P("a", 3333), 1]]), { code: "X", percentOff: 15 });
    return t.discountCents === 500 && t.totalCents === 3432 && allInt(t);
  });
  await check("cupón 100%: descuenta todo y cobra el envío (subtotal descontado < umbral)", () => {
    const t = cart.cartTotals(build([[P("a", 6000), 1]]), { code: "X", percentOff: 100 });
    return t.discountCents === 6000 && t.shippingCents === 599 && t.totalCents === 599;
  });
  await check("sumar a una línea existente conserva el orden de las líneas", () => {
    const c = build([[P("a", 100), 1], [P("b", 200), 1], [P("a", 100), 2]]);
    return c.lines.map((l) => l.productId).join() === "a,b" && c.lines[0].quantity === 3;
  });
  await check("la línea no comparte estado con el producto recibido", () => {
    const p = P("a", 100);
    const c = cart.addToCart(cart.createCart(), p, 1);
    p.priceCents = 999; p.name = "otro";
    return c.lines[0].unitPriceCents === 100 && c.lines[0].name === "Pa";
  });
  await check("carrito vacío = todo en cero", () => {
    const t = cart.cartTotals(cart.createCart());
    return t.subtotalCents === 0 && t.shippingCents === 0 && t.totalCents === 0 && t.discountCents === 0;
  });
  await check("cantidades múltiples y varias líneas", () => {
    const t = cart.cartTotals(build([[P("a", 1999), 2], [P("b", 550), 3], [P("a", 1999), 1]]));
    return t.subtotalCents === 1999 * 3 + 550 * 3 && t.shippingCents === 0;
  });
}

// ---------------------------------------------------------------- W-202
function setupDom() {
  const dom = new JSDOM(`<!doctype html><body><div class="search-box" id="root">
    <input class="search-box__input" type="search">
    <ul class="search-box__results" id="search-results"></ul>
    <p class="search-box__status"></p></div></body>`);
  const g = global;
  g.window = dom.window;
  g.document = dom.window.document;
  for (const k of ["HTMLElement", "HTMLInputElement", "HTMLUListElement", "Event", "InputEvent", "Node", "KeyboardEvent"])
    g[k] = dom.window[k];
  const root = document.getElementById("root");
  return {
    root,
    input: root.querySelector(".search-box__input"),
    list: root.querySelector(".search-box__results"),
    status: root.querySelector(".search-box__status"),
    type(v) { this.input.value = v; this.input.dispatchEvent(new window.Event("input", { bubbles: true })); },
  };
}

async function w202() {
  const modPath = path.join(out, "ui/searchBox.js");
  await check("existe src/ui/searchBox.ts con initSearchBox", () => fs.existsSync(modPath) && typeof require(modPath).initSearchBox === "function");
  if (!fs.existsSync(modPath)) return;
  const { initSearchBox } = require(modPath);
  const mk = (resultsFor, delays = {}) => {
    const calls = [];
    const fn = (q) => { calls.push(q); return new Promise((res, rej) => setTimeout(() => {
      const r = resultsFor(q); if (r instanceof Error) rej(r); else res(r); }, delays[q] || 0)); };
    return { fn, calls };
  };

  await check("debounce: varias teclas → una sola búsqueda con el último texto", async () => {
    const d = setupDom(); const s = mk(() => []);
    initSearchBox(d.root, s.fn, { debounceMs: 20 });
    d.type("gu"); d.type("gui"); d.type("guit");
    await sleep(60);
    return s.calls.length === 1 && s.calls[0] === "guit";
  });
  await check("recorta espacios del texto", async () => {
    const d = setupDom(); const s = mk(() => []);
    initSearchBox(d.root, s.fn, { debounceMs: 10 });
    d.type("  amp  "); await sleep(40);
    return s.calls[0] === "amp";
  });
  await check("menos de 2 caracteres: no busca y limpia", async () => {
    const d = setupDom(); const s = mk(() => [{ id: "1", name: "Amp", category: "amps", priceCents: 100 }]);
    initSearchBox(d.root, s.fn, { debounceMs: 10 });
    d.type("amp"); await sleep(40);
    const had = d.list.children.length;
    d.type("a"); await sleep(40);
    return had === 1 && s.calls.length === 1 && d.list.children.length === 0 && d.status.textContent.trim() === "";
  });
  await check("renderiza items con nombre y precio formateado", async () => {
    const d = setupDom();
    const s = mk(() => [{ id: "1", name: "Strat", category: "guitars", priceCents: 129999 }, { id: "2", name: "Cable", category: "accessories", priceCents: 500 }]);
    initSearchBox(d.root, s.fn, { debounceMs: 10 });
    d.type("st"); await sleep(40);
    const li = [...d.list.querySelectorAll("li.search-box__item")];
    return li.length === 2 && li[0].textContent.trim() === "Strat — $1299.99" && li[1].textContent.trim() === "Cable — $5.00";
  });
  await check("XSS: el nombre con HTML se muestra como texto", async () => {
    const d = setupDom(); const evil = '<img src=x onerror="window.__xss=1">';
    const s = mk(() => [{ id: "1", name: evil, category: "amps", priceCents: 100 }]);
    initSearchBox(d.root, s.fn, { debounceMs: 10 });
    d.type("xx"); await sleep(40);
    const li = d.list.querySelector("li");
    return li && li.textContent.includes(evil) && !d.list.querySelector("img");
  });
  await check("sin resultados → 'Sin resultados'", async () => {
    const d = setupDom(); const s = mk(() => []);
    initSearchBox(d.root, s.fn, { debounceMs: 10 });
    d.type("zz"); await sleep(40);
    return d.list.children.length === 0 && d.status.textContent.trim() === "Sin resultados";
  });
  await check("error → 'Error al buscar'", async () => {
    const d = setupDom(); const s = mk(() => new Error("boom"));
    initSearchBox(d.root, s.fn, { debounceMs: 10 });
    d.type("zz"); await sleep(40);
    return d.list.children.length === 0 && d.status.textContent.trim() === "Error al buscar";
  });
  await check("respuestas fuera de orden: gana la última búsqueda", async () => {
    const d = setupDom();
    const s = mk((q) => [{ id: q, name: q.toUpperCase(), category: "amps", priceCents: 100 }], { gui: 120, guit: 10 });
    initSearchBox(d.root, s.fn, { debounceMs: 5 });
    d.type("gui"); await sleep(20);
    d.type("guit"); await sleep(200);
    const li = [...d.list.querySelectorAll("li")];
    return s.calls.length === 2 && li.length === 1 && li[0].textContent.startsWith("GUIT");
  });
  await check("bajar de 2 caracteres cancela la búsqueda pendiente", async () => {
    const d = setupDom(); const s = mk(() => [{ id: "1", name: "Amp", category: "amps", priceCents: 100 }]);
    initSearchBox(d.root, s.fn, { debounceMs: 30 });
    d.type("amp"); await sleep(5); d.type("a"); await sleep(80);
    return s.calls.length === 0 && d.list.children.length === 0;
  });
  await check("una respuesta lenta no pisa el estado de 'menos de 2 caracteres'", async () => {
    const d = setupDom(); const s = mk(() => [{ id: "1", name: "Amp", category: "amps", priceCents: 100 }], { amp: 80 });
    initSearchBox(d.root, s.fn, { debounceMs: 5 });
    d.type("amp"); await sleep(25); d.type("a"); await sleep(150);
    return d.list.children.length === 0;
  });
  await check("tras un error, una búsqueda correcta limpia el estado", async () => {
    const d = setupDom(); let fail = true;
    const s = mk(() => (fail ? new Error("x") : [{ id: "1", name: "Amp", category: "amps", priceCents: 100 }]));
    initSearchBox(d.root, s.fn, { debounceMs: 5 });
    d.type("zz"); await sleep(30); fail = false; d.type("amp"); await sleep(30);
    return d.status.textContent.trim() === "" && d.list.children.length === 1;
  });
  await check("accesibilidad: aria-controls y aria-live", async () => {
    const d = setupDom(); initSearchBox(d.root, mk(() => []).fn, { debounceMs: 10 });
    return d.input.getAttribute("aria-controls") === "search-results" && d.status.getAttribute("aria-live") === "polite";
  });
  await check("debounce por defecto ~300 ms", async () => {
    const d = setupDom(); const s = mk(() => []);
    initSearchBox(d.root, s.fn);
    d.type("guit"); await sleep(150);
    const early = s.calls.length; await sleep(300);
    return early === 0 && s.calls.length === 1;
  });
}

// ---------------------------------------------------------------- W-203
async function w203() {
  const api = req("api/products.js");
  const cats = ["guitars", "pedals", "amps", "accessories"];
  const counts = { guitars: 13, pedals: 9, amps: 5, accessories: 3 };
  const products = [];
  for (const c of cats) for (let i = 0; i < counts[c]; i++) products.push({ id: `${c}-${i}`, name: `${c} ${i}`, category: c, priceCents: 1000 + i });
  const repo = { all: () => products.slice() };
  const get = (q, r = repo) => api.handleGetProducts(q, r);
  const bad = (res, field) => res.status === 400 && res.body && res.body.error && res.body.error.code === "INVALID_QUERY" && res.body.error.field === field;

  await check("por defecto: página 1 de 12, total 30, 3 páginas", () => {
    const r = get({});
    return r.status === 200 && r.body.page === 1 && r.body.pageSize === 12 && r.body.total === 30 && r.body.totalPages === 3 && r.body.items.length === 12 && r.body.items[0].id === products[0].id;
  });
  await check("página 3 tiene 6 items; página 4 → 200 vacía", () => {
    const a = get({ page: "3" }), b = get({ page: "4" });
    return a.body.items.length === 6 && a.body.items[0].id === products[24].id && b.status === 200 && b.body.items.length === 0;
  });
  await check("pageSize 48 permitido (máximo vigente)", () => { const r = get({ pageSize: "48" }); return r.status === 200 && r.body.items.length === 30 && r.body.totalPages === 1; });
  await check("pageSize 49 → 400 pageSize", () => bad(get({ pageSize: "49" }), "pageSize"));
  await check("pageSize 0 / abc / 2.5 → 400 pageSize", () => ["0", "abc", "2.5", "-3"].every((v) => bad(get({ pageSize: v }), "pageSize")));
  await check("page 0 / -1 / x / 1.5 → 400 page", () => ["0", "-1", "x", "1.5"].every((v) => bad(get({ page: v }), "page")));
  await check("sin productos → total 0 y totalPages 0", () => {
    const r = get({}, { all: () => [] });
    return r.status === 200 && r.body.total === 0 && r.body.totalPages === 0 && r.body.items.length === 0;
  });
  await check("page y pageSize combinados cortan bien (page=2, pageSize=5)", () => {
    const r = get({ page: "2", pageSize: "5" });
    return r.status === 200 && r.body.page === 2 && r.body.pageSize === 5 && r.body.totalPages === 6 &&
      r.body.items.map((p) => p.id).join() === products.slice(5, 10).map((p) => p.id).join();
  });
  await check("solo dígitos: ' 2', '+2', '1e1', '' y '007x' son inválidos", () =>
    [" 2", "+2", "1e1", "", "007x"].every((v) => bad(get({ page: v }), "page")) &&
    [" 2", "+2", "1e1", ""].every((v) => bad(get({ pageSize: v }), "pageSize")));
  await check("enteros enormes (no seguros) → 400", () =>
    bad(get({ page: "99999999999999999999" }), "page") && bad(get({ pageSize: "99999999999999999999" }), "pageSize"));
  await check("el error nombra el campo que falla aunque el otro sea válido", () =>
    bad(get({ page: "2", pageSize: "x" }), "pageSize") && bad(get({ page: "x", pageSize: "5" }), "page"));
  await check("no muta lo que devuelve el repo", () => {
    const arr = products.slice(); const before = JSON.stringify(arr);
    get({}, { all: () => arr });
    return JSON.stringify(arr) === before;
  });
}

// ---------------------------------------------------------------- W-204
async function w204() {
  const htmlPath = path.join(work, "public/contact.html");
  const cssPath = path.join(work, "public/css/contact.css");
  const html = fs.readFileSync(htmlPath, "utf8");
  const doc = new JSDOM(html).window.document;
  const css = fs.existsSync(cssPath) ? fs.readFileSync(cssPath, "utf8") : "";
  const form = doc.getElementById("contact-form");
  const field = (id) => doc.getElementById(id);
  const labelFor = (id) => !!doc.querySelector(`label[for="${id}"]`) || !!(field(id) && field(id).closest("label"));

  await check("formulario conserva id, action y method", () => form && form.getAttribute("action") === "/api/contact" && (form.getAttribute("method") || "").toLowerCase() === "post");
  await check("campos conservan name", () => ["name", "email", "message"].every((n) => form && form.querySelector(`[name="${n}"]`)));
  await check("cada campo tiene label asociado", () => ["name", "email", "message"].every(labelFor));
  await check("los 3 campos son required y el correo es type=email", () =>
    ["name", "email", "message"].every((id) => field(id) && field(id).hasAttribute("required")) && field("email").getAttribute("type") === "email");
  await check("botón real type=submit dentro del form", () => form && !!form.querySelector('button[type="submit"]'));
  await check("sin JavaScript en línea (onclick, etc.)", () => ![...doc.querySelectorAll("*")].some((el) => [...el.attributes].some((a) => a.name.startsWith("on"))));
  await check("#form-errors con aria-live=polite", () => doc.getElementById("form-errors") && doc.getElementById("form-errors").getAttribute("aria-live") === "polite");
  await check("sin estilos en línea", () => !doc.querySelector("[style]") && !doc.querySelector("body style"));
  await check("incluye css/contact.css y conserva site.css", () => {
    const hrefs = [...doc.querySelectorAll('link[rel="stylesheet"]')].map((l) => l.getAttribute("href"));
    return hrefs.includes("css/contact.css") && hrefs.includes("css/site.css");
  });
  await check("contact.css existe y define clases contact-form__*", () => /\.contact-form__[a-z]/.test(css));
  await check("clases del HTML siguen BEM y las contact-form* existen en el CSS", () => {
    const classes = new Set([...doc.querySelectorAll("[class]")].flatMap((el) => [...el.classList]));
    const bem = /^[a-z]+(-[a-z]+)*(__[a-z]+(-[a-z]+)*)?(--[a-z]+(-[a-z]+)*)?$/;
    const used = [...classes].filter((c) => c.startsWith("contact-form") && /__|--/.test(c));
    return classes.size > 0 && [...classes].every((c) => bem.test(c)) && used.length > 0 &&
      used.every((c) => new RegExp("\\." + c.replace(/[-_]/g, (m) => "\\" + m) + "(?![\\w-])").test(css));
  });
}

(async () => {
  try {
    if (task === "W-201") await w201();
    else if (task === "W-202") await w202();
    else if (task === "W-203") await w203();
    else if (task === "W-204") await w204();
    else notes.push("tarea desconocida");
  } catch (e) {
    notes.push("fatal: " + (e && e.stack ? e.stack.split("\n").slice(0, 3).join(" | ") : e));
  }
  process.stdout.write("@@RESULT@@" + JSON.stringify({ checks: results, notes }) + "\n");
  process.exit(0);
})();
