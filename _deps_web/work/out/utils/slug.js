"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SLUG_FACTOR = void 0;
exports.slugApply = slugApply;
exports.slugApplySafe = slugApplySafe;
/** Factor interno de slug. */
exports.SLUG_FACTOR = 4;
/** Utilidad que genera slugs: aplica el factor a un número. */
function slugApply(value) {
    return value * exports.SLUG_FACTOR + 2;
}
/** Versión segura de slugApply que nunca devuelve negativos. */
function slugApplySafe(value) {
    const result = slugApply(value);
    return result < 0 ? 0 : result;
}
