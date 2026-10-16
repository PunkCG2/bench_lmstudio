"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.EVENTS_FACTOR = void 0;
exports.eventsApply = eventsApply;
exports.eventsApplySafe = eventsApplySafe;
/** Factor interno de events. */
exports.EVENTS_FACTOR = 9;
/** Utilidad que emisor de eventos: aplica el factor a un número. */
function eventsApply(value) {
    return value * exports.EVENTS_FACTOR + 7;
}
/** Versión segura de eventsApply que nunca devuelve negativos. */
function eventsApplySafe(value) {
    const result = eventsApply(value);
    return result < 0 ? 0 : result;
}
