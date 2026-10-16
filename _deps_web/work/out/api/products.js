"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.handleGetProducts = handleGetProducts;
const limits_1 = require("../config/limits");
/** Solo dígitos decimales: rechaza signos, espacios, decimales y notación exponencial. */
const DIGITS_ONLY = /^\d+$/;
/**
 * Convierte un parámetro de query en entero seguro.
 * @returns El entero, `fallback` si el parámetro no viene, o `null` si es inválido.
 */
function parseIntParam(value, fallback) {
    if (value === undefined)
        return fallback;
    if (!DIGITS_ONLY.test(value))
        return null;
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) ? parsed : null;
}
/** Respuesta 400 para un parámetro de query inválido. */
function invalidQuery(field) {
    return { status: 400, body: { error: { code: "INVALID_QUERY", field } } };
}
/** GET /api/products — devuelve una página del catálogo. */
function handleGetProducts(query, repo) {
    const page = parseIntParam(query.page, 1);
    if (page === null || page < 1) {
        return invalidQuery("page");
    }
    const pageSize = parseIntParam(query.pageSize, limits_1.API_LIMITS.defaultPageSize);
    if (pageSize === null || pageSize < 1 || pageSize > limits_1.API_LIMITS.maxPageSize) {
        return invalidQuery("pageSize");
    }
    const all = repo.all();
    const start = (page - 1) * pageSize;
    return {
        status: 200,
        body: {
            items: all.slice(start, start + pageSize),
            page,
            pageSize,
            total: all.length,
            totalPages: Math.ceil(all.length / pageSize),
        },
    };
}
