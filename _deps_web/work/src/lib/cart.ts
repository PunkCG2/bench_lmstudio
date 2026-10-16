import type { Cart, CartTotals, Coupon, Product } from "../types/product";
import { FREE_SHIPPING_THRESHOLD_CENTS, SHIPPING_FEE_CENTS } from "../config/shop";

/** Crea un carrito vacío. */
export function createCart(): Cart {
  return { lines: [] };
}

/**
 * Agrega `quantity` unidades de un producto. Si el producto ya está en el carrito, suma la cantidad
 * a esa línea. Cantidades no enteras o <= 0 se ignoran (devuelve el carrito sin cambios).
 */
export function addToCart(cart: Cart, product: Product, quantity: number): Cart {
  if (quantity <= 0) return cart;
  cart.lines.push({
    productId: product.id,
    name: product.name,
    unitPriceCents: product.priceCents,
    quantity,
  });
  return cart;
}

/**
 * Calcula los importes. El cupón se aplica sobre el subtotal (redondeando el descuento al centavo
 * más cercano). El envío es gratis si el subtotal ya descontado es >= FREE_SHIPPING_THRESHOLD_CENTS;
 * si el carrito está vacío no se cobra envío.
 */
export function cartTotals(cart: Cart, coupon?: Coupon): CartTotals {
  let subtotal = 0;
  for (const line of cart.lines) {
    subtotal += (line.unitPriceCents / 100) * line.quantity;
  }
  const shipping = subtotal * 100 >= FREE_SHIPPING_THRESHOLD_CENTS ? 0 : SHIPPING_FEE_CENTS;
  const gross = subtotal * 100 + shipping;
  const discount = coupon ? gross * (coupon.percentOff / 100) : 0;
  return {
    subtotalCents: subtotal * 100,
    discountCents: discount,
    shippingCents: shipping,
    totalCents: gross - discount,
  };
}
