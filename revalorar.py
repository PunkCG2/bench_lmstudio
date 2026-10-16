#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REVALORAR — vuelve a calificar con los tests ACTUALES los archivos que dejaron ejecuciones guardadas
(resultados_pareja/*/*/<TAREA>.json), sin llamar a ningún modelo. Sirve para validar cambios en tareas y
calificadores: muestra cómo cambia la nota de cada ejecución (sola / pareja / Claude solo).

Uso:  python revalorar.py                      (todas las carpetas y las tareas vigentes)
      python revalorar.py --tareas T-102 W-202 --modelo qwen
"""
import argparse
import json
import sys
from pathlib import Path

import agente_benchmark as core

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def calificar(task, files, node):
    g = core.grade_run(task, dict(files), [], {"steps": 0, "seconds": 0, "changed": sorted(files), "deleted": []}, [], node)
    return g, core.score10(core.task_score(g))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tareas", nargs="*")
    ap.add_argument("--modelo", help="filtra carpetas de resultados por texto")
    ap.add_argument("--detalle", action="store_true", help="muestra los checks que fallan")
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    node = core.node_ready()
    tasks = args.tareas or [t for c, _, ts in core.CATEGORIES if c != "mcp" for t in ts]
    for d in sorted((here / "resultados_pareja").glob("*/*")):
        if args.modelo and args.modelo.lower() not in d.parent.name.lower():
            continue
        print(f"\n== {d.parent.name} / {d.name}")
        for t in tasks:
            f = d / f"{t}.json"
            if not f.exists():
                continue
            r = json.loads(f.read_text(encoding="utf-8"))
            partes = []
            for etiqueta, clave, sub in (("pareja", "pair_files", None), ("claude", "claude_solo", "files")):
                files = r.get(clave) if sub is None else (r.get(clave) or {}).get(sub)
                if not files:
                    continue
                g, s = calificar(t, files, node)
                ant = (r.get("pair") if etiqueta == "pareja" else r.get("claude_solo") or {}).get("score")
                partes.append(f"{etiqueta} {ant}→{s}")
                if args.detalle:
                    fallos = [k for k, v in {**g["tests"], **g["conventions"]}.items() if not v]
                    if fallos:
                        partes.append("falla: " + "; ".join(fallos)[:300])
            print(f"  {t:8} " + "   ".join(partes))


if __name__ == "__main__":
    main()
