// Tests de comportamiento FB-601 (migrateUsers). Uso: node fb601_tests.js <workDir>
"use strict";
const path = require("path");
const fs = require("fs");
const work = path.resolve(process.argv[2]);
const results = {}; const notes = [];
function check(name, fn) { try { results[name] = !!fn(); } catch (e) { results[name] = false; notes.push(name + ": " + (e && e.message)); } }
let migrateUsers;
try { ({ migrateUsers } = require(path.join(work, "out", "migrate.js"))); } catch (e) { notes.push("no carga migrate.js: " + e.message); }
const sample = () => JSON.parse(fs.readFileSync(path.join(work, "data", "rtdb_export.json"), "utf8"));
const run = (x) => migrateUsers(x);
check("migra los usuarios no baneados (y omite baneados sin error)", () => {
  const r = run(sample()); return Object.keys(r.users).sort().join(",") === "uA1,uB2,uD4" && !r.errors.some((e) => e.uid === "uC3");
});
check("displayName: trim, por defecto y recorte a 24", () => {
  const u = run(sample()).users; return u.uA1.displayName === "Ana María" && u.uB2.displayName === "Jugador" && u.uD4.displayName === "Un nombre larguísimo par" && u.uD4.displayName.length === 24;
});
check("score: texto numérico a entero, inválido → 0 con error", () => {
  const r = run(sample()); return r.users.uA1.score === 1200 && r.users.uB2.score === 860 && r.users.uD4.score === 0 &&
    r.errors.some((e) => e.uid === "uD4" && e.field === "score");
});
check("score fuera de rango o decimal → error", () => {
  const r = run({ users: { a: { score: 1000001 }, b: { score: "12.5" }, c: { score: -3 }, d: { score: 1000000 } } });
  return r.users.a.score === 0 && r.users.b.score === 0 && r.users.c.score === 0 && r.users.d.score === 1000000 &&
    ["a", "b", "c"].every((id) => r.errors.some((e) => e.uid === id && e.field === "score"));
});
check("lastLogin: ms → ISO, falta → null, inválido → null con error", () => {
  const r = run(sample()); return r.users.uA1.lastLogin === new Date(1728000000000).toISOString() &&
    r.users.uD4.lastLogin === null && r.errors.some((e) => e.uid === "uD4" && e.field === "lastLogin") &&
    run({ users: { x: { score: 1 } } }).users.x.lastLogin === null;
});
check("inventory: objeto indexado y arreglo con huecos → lista compacta en orden", () => {
  const u = run(sample()).users; const o = run({ users: { z: { score: 1, inventory: { "10": "c", "2": "b", "0": "a" } } } }).users.z;
  return JSON.stringify(u.uA1.inventory) === '["sword","potion","potion"]' && JSON.stringify(u.uB2.inventory) === '["shield","bow"]' &&
    JSON.stringify(u.uD4.inventory) === "[]" && JSON.stringify(o.inventory) === '["a","b","c"]';
});
check("settings: texto 'true'/'false' → booleanos, falta → {}", () => {
  const u = run(sample()).users; const s = run({ users: { y: { score: 1, settings: { a: "true", b: false, c: "quizás", d: 1 } } } }).users.y.settings;
  return u.uA1.settings.music === true && u.uA1.settings.sfx === false && u.uB2.settings.music === false &&
    JSON.stringify(u.uD4.settings) === "{}" && JSON.stringify(s) === '{"a":true,"b":false}';
});
check("no modifica la entrada", () => { const input = sample(); const before = JSON.stringify(input); run(input); return JSON.stringify(input) === before; });
check("entrada inválida → error users sin lanzar", () => [null, 42, "x", [], {}, { users: [] }, { users: null }].every((bad) => {
  const r = run(bad); return Object.keys(r.users).length === 0 && r.errors.length === 1 && r.errors[0].uid === "*" && r.errors[0].field === "users";
}));
check("score vacío o solo espacios → 0 con error (no es un 0 válido)", () => {
  const r = run({ users: { a: { score: "" }, b: { score: "   " }, c: { score: "0" } } });
  return r.users.a.score === 0 && r.users.b.score === 0 && r.users.c.score === 0 &&
    ["a", "b"].every((id) => r.errors.some((e) => e.uid === id && e.field === "score")) && !r.errors.some((e) => e.uid === "c");
});
check("lastLogin fuera del rango de Date → null con error, sin lanzar", () => {
  const r = run({ users: { a: { score: 1, lastLogin: 1e20 }, b: { score: 1, lastLogin: "no" }, c: { score: 1, lastLogin: 0 } } });
  return r.users.a.lastLogin === null && r.users.b.lastLogin === null && r.users.c.lastLogin === "1970-01-01T00:00:00.000Z" &&
    ["a", "b"].every((id) => r.errors.some((e) => e.uid === id && e.field === "lastLogin"));
});
check("uids como __proto__ o constructor no rompen ni contaminan", () => {
  const input = JSON.parse('{"users":{"__proto__":{"score":5},"constructor":{"score":6},"ok":{"score":1}}}');
  const r = run(input);
  return ({}).score === undefined && r.users.ok.score === 1 && Object.prototype.hasOwnProperty.call(r.users, "constructor");
});
check("usuario que no es un objeto no tumba la migración", () => {
  const r = run({ users: { a: null, b: 7, c: { score: 3 } } });
  return r.users.c.score === 3 && r.errors.length >= 0;
});
check("inventory: elementos no texto se descartan sin romper", () => {
  const r = run({ users: { a: { score: 1, inventory: ["a", 5, null, { x: 1 }, "b"] } } });
  return JSON.stringify(r.users.a.inventory) === '["a","b"]';
});
process.stdout.write("@@RESULT@@" + JSON.stringify({ checks: results, notes }) + "\n");
