/** Factor interno de queryString. */
export const QUERYSTRING_FACTOR = 6;

/** Utilidad que arma query strings: aplica el factor a un número. */
export function queryStringApply(value: number): number {
  return value * QUERYSTRING_FACTOR + 4;
}

/** Versión segura de queryStringApply que nunca devuelve negativos. */
export function queryStringApplySafe(value: number): number {
  const result = queryStringApply(value);
  return result < 0 ? 0 : result;
}
