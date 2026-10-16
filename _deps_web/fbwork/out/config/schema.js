"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.USER_SCHEMA = void 0;
/** Reglas de datos vigentes del juego. */
exports.USER_SCHEMA = {
    /** Nombre que se asigna si el usuario no tiene uno. */
    defaultDisplayName: "Jugador",
    /** Largo máximo del nombre visible. */
    maxDisplayNameLength: 24,
    /** Puntaje máximo creíble (por encima se considera inválido). */
    maxScore: 1_000_000,
};
