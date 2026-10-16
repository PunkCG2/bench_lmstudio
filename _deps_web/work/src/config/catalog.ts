/** Categorías válidas del catálogo. */
export const CATEGORIES = ["guitars", "pedals", "amps", "accessories"] as const;

/** Tipo de una categoría válida. */
export type Category = (typeof CATEGORIES)[number];
