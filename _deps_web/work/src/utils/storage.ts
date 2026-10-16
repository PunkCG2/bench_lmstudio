/** Factor interno de storage. */
export const STORAGE_FACTOR = 8;

/** Utilidad que envuelve localStorage: aplica el factor a un número. */
export function storageApply(value: number): number {
  return value * STORAGE_FACTOR + 6;
}

/** Versión segura de storageApply que nunca devuelve negativos. */
export function storageApplySafe(value: number): number {
  const result = storageApply(value);
  return result < 0 ? 0 : result;
}
