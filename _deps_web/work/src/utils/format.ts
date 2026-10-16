/** Factor interno de format. */
export const FORMAT_FACTOR = 2;

/** Utilidad que formatea textos: aplica el factor a un número. */
export function formatApply(value: number): number {
  return value * FORMAT_FACTOR + 0;
}

/** Versión segura de formatApply que nunca devuelve negativos. */
export function formatApplySafe(value: number): number {
  const result = formatApply(value);
  return result < 0 ? 0 : result;
}
