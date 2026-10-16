#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QWEN-LOCAL — servidor MCP para usar tu modelo local de LM Studio desde Claude Code.

Herramientas que ve Claude:
  qwen_escribir   Qwen escribe un archivo nuevo completo a partir de instrucciones (+ archivos de contexto).
  qwen_corregir   Qwen aplica una lista de correcciones a un archivo y devuelve el diff.
  qwen_estado     Comprueba LM Studio y el modelo que se usará.

Sin dependencias (solo Python 3). Variables de entorno opcionales:
  LMSTUDIO_URL    (por defecto http://localhost:1235)
  QWEN_MODEL      id del modelo (por defecto el que esté cargado en LM Studio)
  QWEN_MCP_ROOT   carpeta(s) donde puede escribir (por defecto la carpeta donde abres Claude Code)

Registro en Claude Code (una vez):
  claude mcp add --scope user --transport stdio qwen-local -- python C:\\Users\\punkc\\Documents\\bench_lmstudio\\qwen_mcp.py
Prueba rápida:  python qwen_mcp.py --probar
"""
# ============================================================================= SERVIDOR MCP MÍNIMO (stdio, sin dependencias)
# Implementa lo justo del protocolo MCP (JSON-RPC 2.0, un mensaje JSON por línea) para exponer herramientas a
# Claude Code: initialize, tools/list, tools/call y ping.
def mcp_serve(server_name, tools, handlers):
    """tools: lista de {"name","description","inputSchema"}; handlers: {nombre: función(args) -> (texto, es_error)}."""
    import json as _json
    import sys as _sys
    stdin = _sys.stdin.buffer
    out = _sys.stdout.buffer

    def send(obj):
        out.write((_json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        out.flush()

    for raw in stdin:
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            msg = _json.loads(line)
        except Exception:
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:          # notificaciones (initialized, cancelled…): no llevan respuesta
            continue
        try:
            if method == "initialize":
                result = {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": server_name, "version": "1.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "tools/call":
                name = params.get("name")
                fn = handlers.get(name)
                if not fn:
                    send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"herramienta desconocida: {name}"}})
                    continue
                try:
                    text, is_err = fn(params.get("arguments") or {})
                except Exception as e:  # noqa: BLE001
                    text, is_err = f"ERROR: {type(e).__name__}: {e}", True
                result = {"content": [{"type": "text", "text": str(text)}], "isError": bool(is_err)}
            else:
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"método no soportado: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": mid, "result": result})
        except Exception as e:  # noqa: BLE001
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})

# ============================================================================= QWEN LOCAL COMO HERRAMIENTA DE CLAUDE CODE
import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("LMSTUDIO_URL", "http://localhost:1235").rstrip("/")
MODEL_ENV = os.environ.get("QWEN_MODEL", "").strip()
ROOTS = [Path(p).resolve() for p in os.environ.get("QWEN_MCP_ROOT", "").split(os.pathsep) if p.strip()] or [Path.cwd().resolve()]
MAX_CTX_CHARS = 60000
TIMEOUT = int(os.environ.get("QWEN_TIMEOUT", "900"))

SYSTEM = ("Eres un programador experto. Escribes archivos de código completos, correctos y listos para usar, siguiendo "
          "exactamente los requisitos y las convenciones que te den. Responde SOLO con un bloque de código "
          "(```lenguaje ... ```) que contenga el archivo ENTERO, sin explicaciones antes ni después.")


def _http(path, payload=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _model():
    if MODEL_ENV:
        return MODEL_ENV
    try:
        for m in _http("/api/v0/models", timeout=10).get("data", []):
            if m.get("state") == "loaded" and str(m.get("type", "llm")) in ("llm", "vlm"):
                return m["id"]
    except Exception:
        pass
    return "qwen3.8-27b"


def _resolve(p):
    path = Path(p)
    if not path.is_absolute():
        path = ROOTS[0] / path
    path = path.resolve()
    if not any(path == r or r in path.parents for r in ROOTS):
        raise ValueError(f"ruta fuera de la carpeta permitida ({', '.join(map(str, ROOTS))}): {p}")
    return path


def _context(files):
    parts, total = [], 0
    for f in files or []:
        try:
            path = _resolve(f)
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            parts.append(f"### {f}\n(no se pudo leer: {e})")
            continue
        text = text[:max(0, MAX_CTX_CHARS - total)]
        total += len(text)
        parts.append(f"### {f}\n```\n{text}\n```")
        if total >= MAX_CTX_CHARS:
            parts.append("(contexto recortado por tamaño)")
            break
    return "\n\n".join(parts)


def _ask_qwen(user):
    model = _model()
    t0 = time.time()
    resp = _http("/v1/chat/completions", {"model": model, "messages": [{"role": "system", "content": SYSTEM},
                                                                       {"role": "user", "content": user}],
                                          "max_tokens": 16384, "stream": False}, timeout=TIMEOUT)
    el = time.time() - t0
    msg = (resp.get("choices") or [{}])[0].get("message") or {}
    content = msg.get("content") or ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    ct = (resp.get("usage") or {}).get("completion_tokens") or 0
    blocks = re.findall(r"```[\w.+#-]*[ \t]*\n(.*?)```", content, re.S)
    code = max(blocks, key=len) if blocks else content.strip()
    if not code.strip():
        raise RuntimeError("Qwen no devolvió código (respuesta vacía; ¿se le acabaron los tokens razonando?)")
    return code.rstrip() + "\n", {"model": model, "seconds": round(el, 1), "tokens": ct,
                                  "tok_s": round(ct / el, 1) if el and ct else None}


def tool_escribir(a):
    out = _resolve(a["archivo_salida"])
    if out.exists() and not a.get("sobrescribir"):
        return f"ERROR: {out} ya existe. Usa qwen_corregir para modificarlo o pasa sobrescribir=true.", True
    user = "## Tarea\n" + a["instrucciones"].strip()
    if a.get("lenguaje"):
        user += f"\n\nLenguaje: {a['lenguaje']}"
    user += f"\n\nArchivo a escribir: {a['archivo_salida']}"
    ctx = _context(a.get("archivos_contexto"))
    if ctx:
        user += "\n\n## Archivos de contexto (léelos para respetar firmas, tipos y convenciones)\n" + ctx
    code, st = _ask_qwen(user)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code, encoding="utf-8")
    lines = code.count("\n")
    preview = "" if not a.get("incluir_contenido") else "\n\n```\n" + code[:20000] + "\n```"
    return (f"Qwen ({st['model']}) escribió {out} — {lines} líneas en {st['seconds']} s ({st['tokens']} tokens, "
            f"{st['tok_s']} tok/s). Léelo y revísalo antes de darlo por bueno; si hay problemas usa qwen_corregir." + preview), False


def tool_corregir(a):
    path = _resolve(a["archivo"])
    if not path.exists():
        return f"ERROR: no existe {path}", True
    old = path.read_text(encoding="utf-8", errors="replace")
    user = ("## Archivo actual: " + a["archivo"] + "\n```\n" + old + "\n```\n\n## Correcciones que debes aplicar\n"
            + a["correcciones"].strip() + "\n\nAplica SOLO esas correcciones y devuelve el archivo COMPLETO corregido.")
    ctx = _context(a.get("archivos_contexto"))
    if ctx:
        user += "\n\n## Archivos de contexto\n" + ctx
    code, st = _ask_qwen(user)
    path.write_text(code, encoding="utf-8")
    diff = list(difflib.unified_diff(old.splitlines(), code.splitlines(), "antes", "después", lineterm="", n=2))
    shown = "\n".join(diff[:400]) + ("\n… (diff recortado)" if len(diff) > 400 else "")
    return (f"Qwen corrigió {path} en {st['seconds']} s ({st['tokens']} tokens). Cambios (diff unificado):\n```diff\n"
            f"{shown or '(sin cambios)'}\n```\nRevisa el diff; si algo sigue mal, vuelve a llamar qwen_corregir o corrígelo tú."), False


def tool_estado(_a):
    try:
        models = _http("/api/v0/models", timeout=10).get("data", [])
    except Exception as e:  # noqa: BLE001
        return f"ERROR: LM Studio no responde en {BASE}: {e}. Abre LM Studio y enciende el servidor.", True
    loaded = [m["id"] for m in models if m.get("state") == "loaded"]
    return (f"LM Studio en {BASE}. Cargado: {', '.join(loaded) or 'ninguno'}. Modelo que se usará: {_model()}. "
            f"Carpeta permitida: {', '.join(map(str, ROOTS))}"), False


TOOLS_DEF = [
    {"name": "qwen_escribir",
     "description": "Delega en Qwen (modelo local, gratis) la escritura de UN archivo nuevo completo (script, clase, componente, "
                    "utilidad). Da instrucciones precisas: propósito, firmas públicas, convenciones, casos borde. Qwen escribe el "
                    "archivo en disco; después léelo y revísalo tú. Tarda de 20 s a 3 min.",
     "inputSchema": {"type": "object", "properties": {
         "instrucciones": {"type": "string", "description": "Qué debe hacer el archivo, con requisitos concretos"},
         "archivo_salida": {"type": "string", "description": "Ruta del archivo a crear (relativa al proyecto)"},
         "archivos_contexto": {"type": "array", "items": {"type": "string"}, "description": "Archivos que Qwen debe leer (interfaces, convenciones, ejemplos)"},
         "lenguaje": {"type": "string"},
         "sobrescribir": {"type": "boolean", "description": "true para reemplazar un archivo existente"},
         "incluir_contenido": {"type": "boolean", "description": "true para recibir el código en la respuesta"}},
         "required": ["instrucciones", "archivo_salida"]}},
    {"name": "qwen_corregir",
     "description": "Pide a Qwen que aplique una lista de correcciones concretas a un archivo y lo reescriba. Devuelve el diff "
                    "de los cambios para que lo revises.",
     "inputSchema": {"type": "object", "properties": {
         "archivo": {"type": "string"},
         "correcciones": {"type": "string", "description": "Lista numerada de problemas y cómo corregirlos"},
         "archivos_contexto": {"type": "array", "items": {"type": "string"}}},
         "required": ["archivo", "correcciones"]}},
    {"name": "qwen_estado", "description": "Comprueba si LM Studio responde y qué modelo local se usará.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _handlers():
    return {"qwen_escribir": tool_escribir, "qwen_corregir": tool_corregir, "qwen_estado": tool_estado}


if __name__ == "__main__":
    if "--probar" in sys.argv:
        print(tool_estado({})[0])
    else:
        mcp_serve("qwen-local", TOOLS_DEF, _handlers())
