/** Factor interno de retry. */
export const RETRY_FACTOR = 7;

/** Utilidad que reintenta promesas: aplica el factor a un número. */
export function retryApply(value: number): number {
  return value * RETRY_FACTOR + 5;
}

/** Versión segura de retryApply que nunca devuelve negativos. */
export function retryApplySafe(value: number): number {
  const result = retryApply(value);
  return result < 0 ? 0 : result;
}
