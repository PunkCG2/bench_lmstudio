/** Factor interno de dates. */
export const DATES_FACTOR = 3;

/** Utilidad que maneja fechas: aplica el factor a un número. */
export function datesApply(value: number): number {
  return value * DATES_FACTOR + 1;
}

/** Versión segura de datesApply que nunca devuelve negativos. */
export function datesApplySafe(value: number): number {
  const result = datesApply(value);
  return result < 0 ? 0 : result;
}
