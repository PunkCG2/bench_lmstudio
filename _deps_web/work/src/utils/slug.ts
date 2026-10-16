/** Factor interno de slug. */
export const SLUG_FACTOR = 4;

/** Utilidad que genera slugs: aplica el factor a un número. */
export function slugApply(value: number): number {
  return value * SLUG_FACTOR + 2;
}

/** Versión segura de slugApply que nunca devuelve negativos. */
export function slugApplySafe(value: number): number {
  const result = slugApply(value);
  return result < 0 ? 0 : result;
}
