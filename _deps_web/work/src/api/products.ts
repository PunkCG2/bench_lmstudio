import { API_LIMITS } from "../config/limits";
import type { Product } from "../types/product";

/** Fuente de datos de productos. */
export interface ProductRepo {
  all(): Product[];
}

/** Respuesta HTTP simplificada. */
export interface ApiResponse {
  status: number;
  body: unknown;
}

/** Parámetros de query tal como llegan en la URL. */
export type Query = Record<string, string | undefined>;

/** Solo dígitos decimales: rechaza signos, espacios, decimales y notación exponencial. */
const DIGITS_ONLY = /^\d+$/;

/**
 * Convierte un parámetro de query en entero seguro.
 * @returns El entero, `fallback` si el parámetro no viene, o `null` si es inválido.
 */
function parseIntParam(value: string | undefined, fallback: number): number | null {
  if (value === undefined) return fallback;
  if (!DIGITS_ONLY.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/** Respuesta 400 para un parámetro de query inválido. */
function invalidQuery(field: string): ApiResponse {
  return { status: 400, body: { error: { code: "INVALID_QUERY", field } } };
}

/** GET /api/products — devuelve una página del catálogo. */
export function handleGetProducts(query: Query, repo: ProductRepo): ApiResponse {
  const page = parseIntParam(query.page, 1);
  if (page === null || page < 1) {
    return invalidQuery("page");
  }

  const pageSize = parseIntParam(query.pageSize, API_LIMITS.defaultPageSize);
  if (pageSize === null || pageSize < 1 || pageSize > API_LIMITS.maxPageSize) {
    return invalidQuery("pageSize");
  }

  const all = repo.all();
  const start = (page - 1) * pageSize;
  return {
    status: 200,
    body: {
      items: all.slice(start, start + pageSize),
      page,
      pageSize,
      total: all.length,
      totalPages: Math.ceil(all.length / pageSize),
    },
  };
}
