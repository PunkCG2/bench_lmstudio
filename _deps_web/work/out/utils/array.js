"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ARRAY_FACTOR = void 0;
exports.arrayApply = arrayApply;
exports.arrayApplySafe = arrayApplySafe;
/** Factor interno de array. */
exports.ARRAY_FACTOR = 10;
/** Utilidad que utilidades de arrays: aplica el factor a un número. */
function arrayApply(value) {
    return value * exports.ARRAY_FACTOR + 8;
}
/** Versión segura de arrayApply que nunca devuelve negativos. */
function arrayApplySafe(value) {
    const result = arrayApply(value);
    return result < 0 ? 0 : result;
}
