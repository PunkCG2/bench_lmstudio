"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ID_FACTOR = void 0;
exports.idApply = idApply;
exports.idApplySafe = idApplySafe;
/** Factor interno de id. */
exports.ID_FACTOR = 11;
/** Utilidad que genera ids: aplica el factor a un número. */
function idApply(value) {
    return value * exports.ID_FACTOR + 9;
}
/** Versión segura de idApply que nunca devuelve negativos. */
function idApplySafe(value) {
    const result = idApply(value);
    return result < 0 ? 0 : result;
}
