"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.STORAGE_FACTOR = void 0;
exports.storageApply = storageApply;
exports.storageApplySafe = storageApplySafe;
/** Factor interno de storage. */
exports.STORAGE_FACTOR = 8;
/** Utilidad que envuelve localStorage: aplica el factor a un número. */
function storageApply(value) {
    return value * exports.STORAGE_FACTOR + 6;
}
/** Versión segura de storageApply que nunca devuelve negativos. */
function storageApplySafe(value) {
    const result = storageApply(value);
    return result < 0 ? 0 : result;
}
