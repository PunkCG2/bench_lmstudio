/** Producto del catálogo. */
export interface Product {
  id: string;
  name: string;
  category: string;
  /** Precio unitario en centavos. */
  priceCents: number;
}

/** Línea del carrito. */
export interface CartLine {
  productId: string;
  name: string;
  unitPriceCents: number;
  quantity: number;
}

/** Carrito de compras (inmutable). */
export interface Cart {
  lines: CartLine[];
}

/** Cupón de descuento porcentual (0-100). */
export interface Coupon {
  code: string;
  percentOff: number;
}

/** Resumen de importes del carrito, en centavos. */
export interface CartTotals {
  subtotalCents: number;
  discountCents: number;
  shippingCents: number;
  totalCents: number;
}
