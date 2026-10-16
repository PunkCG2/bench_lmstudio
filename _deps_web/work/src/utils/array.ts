/** Factor interno de array. */
export const ARRAY_FACTOR = 10;

/** Utilidad que utilidades de arrays: aplica el factor a un número. */
export function arrayApply(value: number): number {
  return value * ARRAY_FACTOR + 8;
}

/** Versión segura de arrayApply que nunca devuelve negativos. */
export function arrayApplySafe(value: number): number {
  const result = arrayApply(value);
  return result < 0 ? 0 : result;
}
