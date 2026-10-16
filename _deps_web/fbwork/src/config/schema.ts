/** Reglas de datos vigentes del juego. */
export const USER_SCHEMA = {
  /** Nombre que se asigna si el usuario no tiene uno. */
  defaultDisplayName: "Jugador",
  /** Largo máximo del nombre visible. */
  maxDisplayNameLength: 24,
  /** Puntaje máximo creíble (por encima se considera inválido). */
  maxScore: 1_000_000,
} as const;
