"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.migrateUsers = migrateUsers;
const schema_1 = require("./config/schema");
/**
 * Indica si el valor es un objeto simple (no nulo y no arreglo).
 * @param value Valor a comprobar.
 */
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
/**
 * Convierte un valor a número; devuelve NaN si no es numérico.
 * @param raw Valor original (número o texto numérico).
 */
function toNumber(raw) {
    if (typeof raw === "number")
        return raw;
    if (typeof raw === "string" && raw.trim() !== "")
        return Number(raw);
    return Number.NaN;
}
/**
 * Devuelve el puntaje como entero válido entre 0 y el máximo del esquema, o null.
 * @param raw Puntaje original.
 */
function parseScore(raw) {
    const value = toNumber(raw);
    const valid = Number.isInteger(value) && value >= 0 && value <= schema_1.USER_SCHEMA.maxScore;
    return valid ? value : null;
}
/**
 * Convierte milisegundos desde epoch a texto ISO, o null si no es una fecha válida.
 * @param raw Valor original en milisegundos.
 */
function parseLastLogin(raw) {
    if (typeof raw !== "number")
        return null;
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? null : date.toISOString();
}
/**
 * Convierte un valor booleano o su texto ("true"/"false") a boolean, o null si no se puede.
 * @param raw Valor original.
 */
function parseBoolean(raw) {
    if (raw === true || raw === "true")
        return true;
    if (raw === false || raw === "false")
        return false;
    return null;
}
/**
 * Normaliza el nombre visible: sin espacios extra, con valor por defecto y largo máximo.
 * @param raw Nombre original.
 */
function normalizeDisplayName(raw) {
    const trimmed = typeof raw === "string" ? raw.trim() : "";
    const name = trimmed === "" ? schema_1.USER_SCHEMA.defaultDisplayName : trimmed;
    return name.slice(0, schema_1.USER_SCHEMA.maxDisplayNameLength);
}
/**
 * Convierte el inventario de RTDB (arreglo con huecos u objeto con claves numéricas) en string[].
 * @param raw Inventario original.
 */
function normalizeInventory(raw) {
    if (Array.isArray(raw)) {
        return raw.filter((item) => typeof item === "string");
    }
    if (isRecord(raw)) {
        return Object.keys(raw)
            .filter((key) => /^\d+$/.test(key))
            .sort((a, b) => Number(a) - Number(b))
            .map((key) => raw[key])
            .filter((item) => typeof item === "string");
    }
    return [];
}
/**
 * Convierte las preferencias en booleanos, omitiendo las que no se puedan interpretar.
 * @param raw Preferencias originales.
 */
function normalizeSettings(raw) {
    if (!isRecord(raw))
        return {};
    const settings = {};
    for (const [key, value] of Object.entries(raw)) {
        const flag = parseBoolean(value);
        if (flag !== null)
            settings[key] = flag;
    }
    return settings;
}
/**
 * Convierte el export de Realtime Database en documentos de Firestore.
 * Ver docs/tasks/FB-601.md.
 * @param rtdb Export JSON de Realtime Database (no se modifica).
 */
function migrateUsers(rtdb) {
    const usersRaw = isRecord(rtdb) ? rtdb.users : undefined;
    if (!isRecord(usersRaw)) {
        return {
            users: {},
            errors: [{ uid: "*", field: "users", message: "El export no tiene 'users' como objeto" }],
        };
    }
    const users = {};
    const errors = [];
    for (const [uid, raw] of Object.entries(usersRaw)) {
        if (!isRecord(raw)) {
            errors.push({ uid, field: "users", message: "El usuario no es un objeto" });
            continue;
        }
        if (raw.banned === true)
            continue;
        const score = parseScore(raw.score);
        if (score === null) {
            errors.push({ uid, field: "score", message: "Puntaje inválido" });
        }
        const hasLastLogin = raw.lastLogin !== undefined && raw.lastLogin !== null;
        const lastLogin = hasLastLogin ? parseLastLogin(raw.lastLogin) : null;
        if (hasLastLogin && lastLogin === null) {
            errors.push({ uid, field: "lastLogin", message: "Fecha de último acceso inválida" });
        }
        users[uid] = {
            displayName: normalizeDisplayName(raw.displayName),
            score: score ?? 0,
            lastLogin,
            inventory: normalizeInventory(raw.inventory),
            settings: normalizeSettings(raw.settings),
        };
    }
    return { users, errors };
}
