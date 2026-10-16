#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BENCH — lanzador único de los benchmarks de modelos locales (LM Studio).

  1. Pregunta qué modelo usar.
  2. Pregunta el tipo de benchmark: agente, asistente, chat o pareja (local + Claude).
  3. Si es pareja, pregunta el revisor: haiku o sonnet.
  4. Lanza el benchmark elegido.

Cada tipo sigue en su propio script (agente_/asistente_/chat_/pareja_benchmark.py) y guarda sus resultados en
la misma carpeta y con el mismo formato de siempre; este archivo solo decide qué ejecutar y con qué argumentos.

Uso interactivo:  python bench.py
Sin preguntas:    python bench.py --modelo qwen3.8 --tipo pareja --revisor sonnet
Todos los modelos: python bench.py --all --tipo agente --rapido     (uno tras otro; cada uno se descarga al terminar)

Argumentos comunes (se pasan al benchmark elegido; los que no aplican a ese tipo dan error de argparse):
  --categorias X..  agente/pareja: unity web cpp unreal rust dotnet firebase (mcp solo agente)
                    asistente: datos texto tts voz chatbot · chat: conocimiento razonamiento formato vision web
  --tareas ID..     agente/pareja: tareas concretas (p. ej. UE-302 RS-401)
  --intentos N      agente/asistente/chat: intentos por prueba (por defecto 1)
  --repetir         ignora resultados guardados
  --rapido          1 intento y un subconjunto representativo (minutos en vez de una hora)
  --rondas N        pareja: rondas de revisión (por defecto 2)
  --modos M..       pareja: "pareja" y/o "claude" (calcula la referencia Claude solo que falte)
  --referencia M    pareja: modelo de la referencia Claude solo (por defecto haiku; se guarda en referencia_claude/)
  --base URL        [avanzado] servidor de LM Studio (por defecto http://localhost:1235)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TIPOS = [
    ("agente", "Agente", "código con herramientas (Unity, Web, C++, Unreal, Rust, .NET, Firebase, MCP) · solo local"),
    ("asistente", "Asistente", "análisis de datos y texto, texto para voz, asistente de voz, chatbot · solo local"),
    ("chat", "Chat", "conocimiento, razonamiento, visión y búsqueda web · solo local"),
    ("pareja", "Pareja", "el modelo local escribe y Claude revisa (compara contra Claude solo)"),
]
REVISORES = [("sonnet", "Sonnet (por defecto)"), ("haiku", "Haiku (mas barato y rapido)"), ("opus", "Opus (mas profundo)"),
             ("fable", "Fable")]
DEFAULT_BASE = "http://localhost:1235"


def preguntar(titulo, opciones, defecto=None):
    """opciones: lista de (clave, texto). Devuelve la clave elegida; Enter acepta `defecto` (índice 0-based)."""
    print(f"\n{titulo}")
    for i, (_, texto) in enumerate(opciones, 1):
        print(f"   {i}. {texto}" + ("   [Enter]" if i - 1 == defecto else ""))
    while True:
        try:
            s = input("   Número (q para salir): ").strip().lower()
        except EOFError:
            sys.exit("Sin entrada interactiva: usa --modelo, --tipo y --revisor.")
        if s in ("q", "salir", "exit"):
            sys.exit(0)
        if not s and defecto is not None:
            return opciones[defecto][0]
        if s.isdigit() and 1 <= int(s) <= len(opciones):
            return opciones[int(s) - 1][0]
        print("   Opción no válida.")


def elegir_modelo(base, deseado):
    import agente_benchmark as core
    try:
        core.http_json(base + "/v1/models", timeout=15)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No pude conectar con LM Studio en {base}: {e}\nEnciende el servidor de LM Studio y vuelve a intentar.")
    models = core.list_models(base)
    if not models:
        sys.exit("El servidor no reporta modelos de chat.")
    if deseado:
        low = deseado.lower()
        hit = [m for m in models if m["id"].lower() == low] or [m for m in models if low in m["id"].lower()]
        if not hit:
            sys.exit(f"No encontré un modelo que contenga '{deseado}'.")
        return hit[0]["id"]
    loaded = [i for i, m in enumerate(models) if m.get("state") == "loaded"]
    if not loaded:
        ids = set(core.loaded_instances(base))
        loaded = [i for i, m in enumerate(models) if m.get("id") in ids]
    opciones = []
    for m in models:
        extra = ", ".join(x for x in ("cargado" if m.get("state") == "loaded" else None, m.get("quantization"),
                                      "visión" if str(m.get("type")).lower() == "vlm" else None) if x)
        opciones.append((m["id"], m["id"] + (f"  ({extra})" if extra else "")))
    return preguntar("¿Qué modelo quieres probar?", opciones, loaded[0] if len(loaded) == 1 else None)


def correr_todos(base, args, extra):
    """--all: un subproceso por modelo (limpio, aislado); descarga cada modelo al terminar."""
    import agente_benchmark as core
    try:
        core.http_json(base + "/v1/models", timeout=15)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No pude conectar con LM Studio en {base}: {e}")
    ex = [e.lower() for e in args.excluir]
    models = [m["id"] for m in core.list_models(base) if not any(e in m["id"].lower() for e in ex)]
    if not models:
        sys.exit("LM Studio no reporta modelos de chat para probar.")
    tipo = args.tipo or preguntar("¿Qué tipo de benchmark para TODOS los modelos?", [(t, f"{n}: {d}") for t, n, d in TIPOS])
    revisor = (args.revisor or preguntar("¿Qué modelo de Claude revisa?", REVISORES, 0)) if tipo == "pareja" else None
    print(f"{chr(10)}--all: se probarán {len(models)} modelo(s) con el benchmark '{tipo}':")
    for i, m in enumerate(models, 1):
        print(f"   {i}. {m}")
    here = Path(__file__).resolve().parent
    resumen, t_all = [], time.time()
    try:
        for i, m in enumerate(models, 1):
            print(chr(10) + "#" * 74 + f"{chr(10)}#  [{i}/{len(models)}]  {m}{chr(10)}" + "#" * 74)
            core.unload_all(base)
            cmd = [sys.executable, "-u", str(Path(__file__).resolve()), "--modelo", m, "--tipo", tipo, "--base", base]
            if revisor:
                cmd += ["--revisor", revisor]
            t0 = time.time()
            r = subprocess.run(cmd + extra, cwd=str(here))
            reportes = sorted(here.glob(f"calificacion_*_{core.safe_name(m)}*.txt"), key=lambda p: p.stat().st_mtime)
            nuevo = [p.name for p in reportes if p.stat().st_mtime >= t0]
            resumen.append((m, r.returncode, nuevo[-1] if nuevo else "", time.time() - t0))
            print(f"Descargando {m}…")
            core.unload_all(base)
    finally:
        print(f"{chr(10)}RESUMEN --all ({(time.time() - t_all) / 60:.0f} min en total)")
        for m, rc, rep, secs in resumen:
            print(f"  {'✓' if rc == 0 and rep else '✗'} {m:52} {secs / 60:4.0f} min  {rep or 'sin reporte (código ' + str(rc) + ')'}")


def main():
    ap = argparse.ArgumentParser(description="Lanzador único de benchmarks (agente, asistente, chat, pareja).", add_help=True)
    ap.add_argument("--modelo", help="id (o parte) del modelo local")
    ap.add_argument("--tipo", choices=[t for t, _, _ in TIPOS], help="tipo de benchmark")
    ap.add_argument("--revisor", choices=[r for r, _ in REVISORES], help="con --tipo pareja: sonnet (por defecto), haiku, opus o fable")
    ap.add_argument("--all", action="store_true", help="probar TODOS los modelos de LM Studio, uno tras otro (nunca es el valor por defecto)")
    ap.add_argument("--excluir", nargs="*", default=[], metavar="TEXTO", help="con --all: omitir modelos cuyo id contenga estos textos")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"[avanzado] URL del servidor de LM Studio (por defecto {DEFAULT_BASE})")
    args, extra = ap.parse_known_args()
    base = args.base.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]

    print("=" * 74 + chr(10) + " BENCH — benchmarks de modelos locales" + chr(10) + "=" * 74)
    if args.all:
        return correr_todos(base, args, extra)
    modelo = elegir_modelo(base, args.modelo)
    tipo = args.tipo or preguntar("¿Qué tipo de benchmark?", [(t, f"{n}: {d}") for t, n, d in TIPOS])
    revisor = None
    if tipo == "pareja":
        revisor = args.revisor or preguntar("¿Qué modelo de Claude revisa?", REVISORES, 0)

    argv = ["--modelo", modelo]
    if tipo == "pareja":
        argv += ["--revisor", revisor, "--base", base]
    else:
        argv += ["--base", base]
    argv += extra
    print(f"\n→ {tipo} · modelo {modelo}" + (f" · revisor {revisor}" if revisor else "") + "\n")

    modulo = __import__(f"{tipo}_benchmark")
    sys.argv = [f"{tipo}_benchmark.py"] + argv
    modulo.main()


if __name__ == "__main__":
    main()
