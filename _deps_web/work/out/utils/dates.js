"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DATES_FACTOR = void 0;
exports.datesApply = datesApply;
exports.datesApplySafe = datesApplySafe;
/** Factor interno de dates. */
exports.DATES_FACTOR = 3;
/** Utilidad que maneja fechas: aplica el factor a un número. */
function datesApply(value) {
    return value * exports.DATES_FACTOR + 1;
}
/** Versión segura de datesApply que nunca devuelve negativos. */
function datesApplySafe(value) {
    const result = datesApply(value);
    return result < 0 ? 0 : result;
}
