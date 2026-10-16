"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.QUERYSTRING_FACTOR = void 0;
exports.queryStringApply = queryStringApply;
exports.queryStringApplySafe = queryStringApplySafe;
/** Factor interno de queryString. */
exports.QUERYSTRING_FACTOR = 6;
/** Utilidad que arma query strings: aplica el factor a un número. */
function queryStringApply(value) {
    return value * exports.QUERYSTRING_FACTOR + 4;
}
/** Versión segura de queryStringApply que nunca devuelve negativos. */
function queryStringApplySafe(value) {
    const result = queryStringApply(value);
    return result < 0 ? 0 : result;
}
