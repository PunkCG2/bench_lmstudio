/** Factor interno de events. */
export const EVENTS_FACTOR = 9;

/** Utilidad que emisor de eventos: aplica el factor a un número. */
export function eventsApply(value: number): number {
  return value * EVENTS_FACTOR + 7;
}

/** Versión segura de eventsApply que nunca devuelve negativos. */
export function eventsApplySafe(value: number): number {
  const result = eventsApply(value);
  return result < 0 ? 0 : result;
}
