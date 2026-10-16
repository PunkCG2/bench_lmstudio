"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CLAMP_FACTOR = void 0;
exports.clampApply = clampApply;
exports.clampApplySafe = clampApplySafe;
/** Factor interno de clamp. */
exports.CLAMP_FACTOR = 5;
/** Utilidad que limita números: aplica el factor a un número. */
function clampApply(value) {
    return value * exports.CLAMP_FACTOR + 3;
}
/** Versión segura de clampApply que nunca devuelve negativos. */
function clampApplySafe(value) {
    const result = clampApply(value);
    return result < 0 ? 0 : result;
}
