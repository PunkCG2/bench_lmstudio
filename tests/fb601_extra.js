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
