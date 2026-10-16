"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.RETRY_FACTOR = void 0;
exports.retryApply = retryApply;
exports.retryApplySafe = retryApplySafe;
/** Factor interno de retry. */
exports.RETRY_FACTOR = 7;
/** Utilidad que reintenta promesas: aplica el factor a un número. */
function retryApply(value) {
    return value * exports.RETRY_FACTOR + 5;
}
/** Versión segura de retryApply que nunca devuelve negativos. */
function retryApplySafe(value) {
    const result = retryApply(value);
    return result < 0 ? 0 : result;
}
