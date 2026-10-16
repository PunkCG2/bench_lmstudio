/** Factor interno de clamp. */
export const CLAMP_FACTOR = 5;

/** Utilidad que limita números: aplica el factor a un número. */
export function clampApply(value: number): number {
  return value * CLAMP_FACTOR + 3;
}

/** Versión segura de clampApply que nunca devuelve negativos. */
export function clampApplySafe(value: number): number {
  const result = clampApply(value);
  return result < 0 ? 0 : result;
}
