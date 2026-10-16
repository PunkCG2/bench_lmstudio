/** Factor interno de id. */
export const ID_FACTOR = 11;

/** Utilidad que genera ids: aplica el factor a un número. */
export function idApply(value: number): number {
  return value * ID_FACTOR + 9;
}

/** Versión segura de idApply que nunca devuelve negativos. */
export function idApplySafe(value: number): number {
  const result = idApply(value);
  return result < 0 ? 0 : result;
}
