/** Documento de usuario en Firestore (colección `users`, id = uid). */
export interface FirestoreUser {
  displayName: string;
  /** Puntaje entero >= 0. */
  score: number;
  /** Fecha ISO 8601 (UTC) o null si no se conoce. */
  lastLogin: string | null;
  /** Objetos del inventario, sin huecos, en el orden original. */
  inventory: string[];
  /** Preferencias booleanas. */
  settings: Record<string, boolean>;
}

/** Problema encontrado al migrar un usuario. */
export interface MigrationError {
  uid: string;
  field: string;
  message: string;
}

/** Resultado de la migración. */
export interface MigrationResult {
  users: Record<string, FirestoreUser>;
  errors: MigrationError[];
}
