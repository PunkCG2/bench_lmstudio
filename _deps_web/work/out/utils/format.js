"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FORMAT_FACTOR = void 0;
exports.formatApply = formatApply;
exports.formatApplySafe = formatApplySafe;
/** Factor interno de format. */
exports.FORMAT_FACTOR = 2;
/** Utilidad que formatea textos: aplica el factor a un número. */
function formatApply(value) {
    return value * exports.FORMAT_FACTOR + 0;
}
/** Versión segura de formatApply que nunca devuelve negativos. */
function formatApplySafe(value) {
    const result = formatApply(value);
    return result < 0 ? 0 : result;
}
