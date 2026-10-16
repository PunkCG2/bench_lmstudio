#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BENCHMARK PAREJA — el modelo local (LM Studio) escribe el código y Claude (tu suscripción, vía Claude Code) lo revisa.

Por cada tarea de código del benchmark de agente (Unity, Web, C++, Unreal, Rust, .NET, JSON/Firebase):
  1. El modelo local implementa la tarea con herramientas (leer, buscar, escribir, compilar)  -> nota "Qwen solo".
  2. Claude revisa tarea + convenciones + build + archivos y dicta correcciones concretas.
  3. El modelo local aplica las correcciones (hasta 2 rondas)                                -> nota "pareja".
  4. Referencia: Claude hace la tarea solo con las mismas herramientas                       -> nota "Claude solo".
Todo se califica con los mismos tests reales. El reporte compara nota, tiempo y tokens de Claude usados.

Las tareas, el sandbox, el build y los calificadores viven en agente_benchmark.py (una sola copia): este
archivo solo añade la revisión de Claude. Requisitos: LM Studio con el modelo local y Claude Code con sesión iniciada.

Uso:  python pareja_benchmark.py                         (modelo cargado + revisión de Haiku + Haiku solo)
      python pareja_benchmark.py --revisor sonnet --rondas 1
      python pareja_benchmark.py --modos pareja --tareas NET-501 UE-302
"""
import argparse
import datetime
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import agente_benchmark as _core

# Todo lo del benchmark de agente (tareas, Sandbox, build, calificadores, chat, etc.) se reutiliza tal cual.
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__") and k != "main"})

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

# ============================================================================= BENCHMARK PAREJA: Qwen escribe, Claude revisa
# Flujo por tarea (las 13 tareas de código del benchmark de agente):
#   1. El modelo local (LM Studio) implementa la tarea con las herramientas de siempre  → nota "Qwen solo".
#   2. Claude (tu suscripción, vía `claude -p`) revisa tarea + convenciones + build + archivos y dicta correcciones.
#   3. El modelo local aplica las correcciones (hasta N rondas)                          → nota "pareja".
#   4. Referencia: Claude hace la tarea solo, con las mismas herramientas de build      → nota "Claude solo".
# Todo se califica con los mismos tests reales del benchmark de agente.
import shutil as _shutil
import subprocess as _subprocess

PAIR_VERSION = "v2"
# Alias que acepta --revisor / --referencia -> valor de `claude --model`.
CLAUDE_MODEL_IDS = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus", "fable": "claude-fable-5-1"}
CLAUDE_CHOICES = list(CLAUDE_MODEL_IDS)
REFERENCIA_DIR = Path(__file__).resolve().parent / "referencia_claude"
CLAUDE_SOLO_PROMPT_VERSION = 1   # sube este numero si cambias el prompt de run_claude_solo
FIX_WALL_SECONDS = 180
CODE_TASKS = [t for c, _, ts in CATEGORIES if c != "mcp" for t in ts]


def task_score(g):
    if not g["metrics"].get("changed") and not g["metrics"].get("deleted"):
        return 0.0
    return 0.65 * g["functional"] + 0.25 * g["convention"] + 0.10 * (1.0 if g["compiles"] else 0.0)


def _json_from_text(text):
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    i = t.find("{")
    while i != -1:
        depth = 0
        for j in range(i, len(t)):
            if t[j] == "{":
                depth += 1
            elif t[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[i:j + 1])
                    except Exception:
                        break
        i = t.find("{", i + 1)
    return None


# ----------------------------------------------------------------------------- Claude Code por línea de comandos
_CLAUDE = {"path": None}
_UNSUPPORTED = set()


def claude_exe():
    if _CLAUDE["path"] is None:
        home = Path.home()
        cands = [_shutil.which("claude"), _shutil.which("claude.exe"), _shutil.which("claude.cmd"),
                 str(home / ".local" / "bin" / "claude.exe"), str(home / ".local" / "bin" / "claude")]
        _CLAUDE["path"] = next((c for c in cands if c and Path(c).exists()), "")
    return _CLAUDE["path"]


def claude_auth():
    exe = claude_exe()
    if not exe:
        return None, "no encontré el comando `claude` (instala Claude Code: irm https://claude.ai/install.ps1 | iex)"
    try:
        r = _subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        data = _json_from_text(r.stdout) or {}
        return data, ""
    except Exception as e:  # noqa: BLE001
        return None, f"no pude ejecutar `claude auth status`: {e}"


def claude_call(prompt, stdin_text, model, cwd, flags, timeout=600):
    """Ejecuta `claude -p` y devuelve el JSON de salida (+ 'seconds'), o {'error': ...}."""
    exe = claude_exe()
    for _ in range(6):
        args = []
        for name, value in flags:
            if name in _UNSUPPORTED:
                continue
            args.append(name)
            if value is not None:
                args.append(value)
        cmd = [exe, "-p", prompt, "--model", CLAUDE_MODEL_IDS.get(model, model), "--output-format", "json"] + args
        t0 = time.time()
        try:
            r = _subprocess.run(cmd, input=stdin_text or "", capture_output=True, text=True, encoding="utf-8",
                                errors="replace", cwd=str(cwd), timeout=timeout)
        except _subprocess.TimeoutExpired:
            return {"error": f"Claude no terminó en {timeout} s", "seconds": float(timeout)}
        el = round(time.time() - t0, 1)
        err = r.stderr or ""
        bad = re.search(r"unknown option '?(--[\w-]+)", err, re.I)
        if r.returncode != 0 and bad and bad.group(1) not in _UNSUPPORTED and any(bad.group(1) == n for n, _ in flags):
            _UNSUPPORTED.add(bad.group(1))
            continue
        out = (r.stdout or "").strip()
        data = None
        try:
            data = json.loads(out)
        except Exception:
            for line in reversed(out.splitlines()):
                if line.strip().startswith("{"):
                    try:
                        data = json.loads(line)
                        break
                    except Exception:
                        pass
        if not isinstance(data, dict):
            return {"error": (err.strip() or out or f"código de salida {r.returncode}")[:500], "seconds": el}
        data["seconds"] = el
        if data.get("is_error") and not data.get("error"):
            data["error"] = str(data.get("result") or data.get("subtype") or "error de Claude")[:300]
        return data
    return {"error": "tu versión de Claude Code no admite las opciones necesarias (actualízala con: claude update)", "seconds": 0}


def claude_usage(data):
    u = data.get("usage") or {}
    tok = sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return {"tokens": tok, "output_tokens": int(u.get("output_tokens") or 0), "cost": float(data.get("total_cost_usd") or 0.0),
            "turns": data.get("num_turns"), "seconds": data.get("seconds", 0),
            # desglose (campos nuevos): entrada nueva = entrada + escritura de caché; la lectura de caché pesa mucho menos
            "fresh_input": int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0),
            "cache_read": int(u.get("cache_read_input_tokens") or 0)}


# ----------------------------------------------------------------------------- sesión del modelo local sobre un sandbox
def qwen_session(base, model, sb, project, user_text, wall):
    msgs = [{"role": "system", "content": system_prompt(project)}, {"role": "user", "content": user_text}]
    m = {"steps": 0, "tool_calls": 0, "tool_errors": 0, "finished": False, "text_tool_leaks": 0, "error": None,
         "seconds": 0.0, "completion_tokens": 0, "tools_used": {}}
    t0 = time.time()
    seq, retried = 0, False
    while m["steps"] < MAX_STEPS:
        if time.time() - t0 > wall:
            m["error"] = "tiempo máximo agotado"
            break
        m["steps"] += 1
        try:
            resp, _ = chat(base, model, msgs, tools=TOOLS, temperature=None)
        except HttpError as e:
            if not retried:
                retried = True
                for x in msgs:
                    if x.get("role") == "assistant" and x.get("content") is None:
                        x["content"] = ""
                continue
            m["error"] = str(e)[:300]
            break
        except Exception as e:  # noqa: BLE001
            m["error"] = f"{type(e).__name__}: {e}"[:300]
            break
        m["completion_tokens"] += (resp.get("usage") or {}).get("completion_tokens") or 0
        msg = ((resp.get("choices") or [{}])[0]).get("message") or {}
        calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""
        if not calls:
            if re.search(r"<tool_call>|\"name\"\s*:\s*\"(read_file|write_file|replace_in_file|list_dir|search|finish)\"", content):
                m["text_tool_leaks"] += 1
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content": "Esa llamada no se ejecutó: usa el mecanismo de tool calling."})
                continue
            m["finished"] = bool(content.strip())
            msgs.append({"role": "assistant", "content": content})
            break
        fixed = []
        for c in calls:
            seq += 1
            fn = c.get("function") or {}
            fixed.append({"id": f"call_{seq}", "type": "function", "function": {"name": fn.get("name"), "arguments": fn.get("arguments") or "{}"}})
        msgs.append({"role": "assistant", "content": content or "", "tool_calls": fixed})
        done = False
        for c in fixed:
            m["tool_calls"] += 1
            name = c["function"]["name"]
            m["tools_used"][name] = m["tools_used"].get(name, 0) + 1
            try:
                args = json.loads(c["function"]["arguments"])
                if not isinstance(args, dict):
                    raise ValueError
                result = sb.exec(name, args)
            except Exception:
                result = "ERROR: los argumentos no son JSON válido"
            if result.startswith("ERROR"):
                m["tool_errors"] += 1
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            if name == "finish":
                done = True
        if done:
            m["finished"] = True
            break
    m["seconds"] = round(time.time() - t0, 1)
    return m, msgs


def _changed_clean(sb):
    changed, deleted = sb.changed()
    changed = {k: v for k, v in changed.items() if not k.startswith(".claude/") and not k.endswith(".orig")}
    return changed, deleted


def _grade(task, changed, deleted, metrics, transcript, node):
    metrics = dict(metrics)
    metrics["changed"], metrics["deleted"] = sorted(changed), deleted
    try:
        return grade_run(task, changed, deleted, metrics, transcript, node)
    except Exception as e:  # noqa: BLE001
        return {"task": task, "compiles": False, "compile_errors": [f"error del calificador: {e}"], "tests": {}, "notes": [],
                "mode": "", "conventions": {}, "functional": 0.0, "convention": 0.0, "out_of_scope": [], "used_build": False,
                "metrics": metrics}


def _brief(g):
    return {"score": score10(task_score(g)), "compiles": g["compiles"],
            "tests": f"{sum(g['tests'].values())}/{len(g['tests'])}", "conv": f"{sum(g['conventions'].values())}/{len(g['conventions'])}",
            "failed": [k for k, v in g["tests"].items() if not v][:6],
            "conv_failed": [k for k, v in g["conventions"].items() if not v][:6],
            "errors": [str(e)[:160] for e in g["compile_errors"][:2]],
            "failed_all": [k for k, v in {**g["tests"], **g["conventions"]}.items() if not v],
            "tests_failed_all": [k for k, v in g["tests"].items() if not v]}


# ----------------------------------------------------------------------------- revisión
REVIEW_RULES = (
    "Eres un revisor de código senior. Otro agente (un modelo local más pequeño) implementó la tarea de abajo en un "
    "proyecto real. Tu trabajo es encontrar problemas CONCRETOS que harían fallar la tarea: requisitos no cumplidos o "
    "mal implementados, casos borde que la tarea pide, errores de compilación o de ejecución (dependencias que no se "
    "pueden inyectar, nulos, concurrencia, firmas cambiadas), y convenciones del proyecto incumplidas. No propongas "
    "mejoras opcionales de estilo ni reescribas el código completo. Si todo cumple, aprobado = true y la lista vacía.\n"
    "Responde SOLO con JSON válido, sin texto extra:\n"
    '{"aprobado": true o false, "correcciones": [{"archivo": "ruta", "problema": "qué está mal", "como_corregir": "qué cambiar"}]}\n'
    "Máximo 8 correcciones, las más importantes primero.\n")


def review_material(task, project, sb, build_out):
    files = PROJECTS[project]
    changed, deleted = _changed_clean(sb)
    parts = [REVIEW_RULES, f"# TAREA ({task})\n" + files.get(f"docs/tasks/{task}.md", ""),
             "# CONVENCIONES DEL PROYECTO\n" + files.get("docs/CONVENTIONS.md", ""),
             "# RESULTADO DEL BUILD\n" + (build_out or "")[:4000],
             "# ARCHIVOS CREADOS O MODIFICADOS POR EL AGENTE"]
    for rel in sorted(changed):
        parts.append(f"## {rel}\n```\n{changed[rel][:15000]}\n```")
    if deleted:
        parts.append("Archivos borrados por el agente: " + ", ".join(deleted))
    parts.append("# RESTO DEL PROYECTO (sin cambios, solo como contexto)")
    for rel in sorted(files):
        if rel in changed or rel in deleted or (rel.startswith("docs/tasks/") and not rel.endswith(f"{task}.md")) \
                or rel in ("docs/CONVENTIONS.md", f"docs/tasks/{task}.md"):
            continue
        parts.append(f"## {rel}\n```\n{files[rel][:6000]}\n```")
    return "\n\n".join(parts)


def correction_message(task, fixes):
    lines = [f"Un revisor revisó tu implementación de docs/tasks/{task}.md y pidió estas correcciones:", ""]
    for i, f in enumerate(fixes, 1):
        lines.append(f"{i}. [{f.get('archivo', '?')}] {f.get('problema', '')}")
        if f.get("como_corregir"):
            lines.append(f"   Cómo corregir: {f['como_corregir']}")
    lines += ["", "Aplica SOLO estas correcciones (lee los archivos antes de editarlos), verifica con build y llama a finish. "
              "Si alguna corrección contradice la tarea o las convenciones, ignórala y dilo en el resumen de finish."]
    return "\n".join(lines)


def run_pair(base, model, task, reviewer, rounds, node, log):
    project = project_of(task)
    sb = Sandbox(project)
    out = {"task": task, "rounds": [], "qwen_seconds": 0.0,
           "claude": {"tokens": 0, "cost": 0.0, "seconds": 0.0, "output_tokens": 0, "fresh_input": 0, "cache_read": 0}}
    try:
        m0, msgs = qwen_session(base, model, sb, project,
                                f"Implementa la tarea descrita en docs/tasks/{task}.md. La raíz del proyecto es '.'.", TASK_WALL_SECONDS)
        out["qwen_seconds"] += m0["seconds"]
        transcript = list(msgs)
        changed, deleted = _changed_clean(sb)
        g0 = _grade(task, changed, deleted, m0, transcript, node)
        out["solo"] = _brief(g0)
        out["solo"]["seconds"] = m0["seconds"]
        out["local"] = {"steps": m0["steps"], "tool_calls": m0["tool_calls"], "tool_errors": m0["tool_errors"],
                        "text_tool_leaks": m0["text_tool_leaks"], "finished": m0["finished"], "error": m0["error"],
                        "completion_tokens": m0["completion_tokens"], "used_build": bool(g0.get("used_build"))}
        log(f"Qwen solo {out['solo']['score']}/10 ({m0['seconds']:.0f} s)")
        metrics = dict(m0)
        for r in range(1, rounds + 1):
            if not changed and not deleted:
                break
            build_out = run_build(sb.root)
            tmp = Path(tempfile.mkdtemp(prefix="bench_rev_"))
            rev = claude_call("Revisa el trabajo que llega por la entrada estándar y responde solo con el JSON pedido.",
                              review_material(task, project, sb, build_out), reviewer, tmp,
                              [("--tools", ""), ("--safe-mode", None), ("--no-session-persistence", None), ("--max-turns", "3")],
                              timeout=300)
            _shutil.rmtree(tmp, ignore_errors=True)
            u = claude_usage(rev)
            for k in ("tokens", "cost", "seconds", "output_tokens", "fresh_input", "cache_read"):
                out["claude"][k] += u.get(k) or 0
            if rev.get("error"):
                out["rounds"].append({"round": r, "error": rev["error"]})
                log(f"revisión {r}: ⚠ {rev['error'][:120]}")
                break
            verdict = _json_from_text(rev.get("result")) or {}
            fixes = [f for f in (verdict.get("correcciones") or []) if isinstance(f, dict)][:8]
            approved = bool(verdict.get("aprobado")) or not fixes
            out["rounds"].append({"round": r, "approved": approved, "fixes": fixes, "claude": u,
                                  "parse_error": None if verdict else (rev.get("result") or "")[:300]})
            log(f"revisión {r}: " + ("✓ aprobado" if approved else f"{len(fixes)} correcciones") + f" ({u['seconds']:.0f} s, {u['tokens']} tok Claude)")
            if approved:
                break
            mf, msgs_f = qwen_session(base, model, sb, project, correction_message(task, fixes), FIX_WALL_SECONDS)
            out["qwen_seconds"] += mf["seconds"]
            transcript += msgs_f
            for k in ("steps", "tool_calls", "tool_errors", "text_tool_leaks", "completion_tokens"):
                metrics[k] = metrics.get(k, 0) + mf.get(k, 0)
            metrics["finished"] = mf["finished"]
            metrics["error"] = mf["error"] or metrics.get("error")
            out["rounds"][-1]["fix_seconds"] = mf["seconds"]
            changed, deleted = _changed_clean(sb)
            log(f"corrección {r}: {mf['seconds']:.0f} s, {mf['steps']} pasos")
        metrics["seconds"] = round(out["qwen_seconds"] + out["claude"]["seconds"], 1)
        gf = _grade(task, changed, deleted, metrics, transcript, node)
        out["pair"] = _brief(gf)
        out["pair"]["seconds"] = metrics["seconds"]
        out["local"]["total_steps"] = metrics.get("steps", 0)
        out["local"]["total_tool_errors"] = metrics.get("tool_errors", 0)
        out["files"] = changed
    finally:
        sb.cleanup()
    return out


# ----------------------------------------------------------------------------- Claude solo (referencia)
def _build_server_main(root, counter):
    def build(_args):
        try:
            n = int(Path(counter).read_text() or "0") if Path(counter).exists() else 0
        except Exception:
            n = 0
        Path(counter).write_text(str(n + 1))
        res = run_build(Path(root))
        return res, False
    mcp_serve("bench", [{"name": "build", "description": "Compila/verifica el proyecto completo y devuelve los errores del "
                         "compilador (o 'Build OK'). Úsalo antes de terminar.", "inputSchema": {"type": "object", "properties": {}}}],
              {"build": build})


def run_claude_solo(task, model, node, log):
    project = project_of(task)
    sb = Sandbox(project)
    meta = Path(tempfile.mkdtemp(prefix="bench_meta_"))
    counter = meta / "builds.txt"
    cfg = meta / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"bench": {"type": "stdio", "command": sys.executable,
                                                        "args": [str(Path(__file__).resolve()), "--servidor-build", str(sb.root), str(counter)]}}}),
                   encoding="utf-8")
    prompt = (f"Implementa la tarea descrita en docs/tasks/{task}.md de este proyecto (la carpeta actual). Lee primero "
              "docs/CONVENTIONS.md y respétalas estrictamente; lee los archivos antes de editarlos; haz los cambios mínimos; "
              "no crees archivos auxiliares ni de prueba y no toques nada fuera de esta carpeta. Para compilar y verificar usa "
              "la herramienta build (mcp__bench__build) y corrige lo que reporte. Termina con un resumen de 2 líneas.")
    try:
        data = claude_call(prompt, "", model, sb.root,
                           [("--tools", "Read,Edit,Write,Glob,Grep"), ("--permission-mode", "acceptEdits"),
                            ("--allowedTools", "Read,Edit,Write,Glob,Grep,mcp__bench__build"), ("--strict-mcp-config", None),
                            ("--mcp-config", str(cfg)), ("--no-session-persistence", None), ("--max-turns", "40")],
                           timeout=TASK_WALL_SECONDS + 120)
        u = claude_usage(data)
        builds = int(counter.read_text()) if counter.exists() else 0
        changed, deleted = _changed_clean(sb)
        metrics = {"steps": data.get("num_turns") or 0, "tool_calls": 0, "tool_errors": 0, "finished": not data.get("error"),
                   "text_tool_leaks": 0, "error": data.get("error"), "seconds": u["seconds"], "completion_tokens": u["output_tokens"]}
        transcript = [{"role": "assistant", "tool_calls": [{"function": {"name": "build"}}]}] if builds else []
        g = _grade(task, changed, deleted, metrics, transcript, node)
        res = _brief(g)
        res.update(seconds=u["seconds"], claude=u, builds=builds, error=data.get("error"), files=changed)
        log(f"Claude solo {res['score']}/10 ({u['seconds']:.0f} s, {u['tokens']} tok)" + (f" ⚠ {data['error'][:100]}" if data.get("error") else ""))
        return res
    finally:
        sb.cleanup()
        _shutil.rmtree(meta, ignore_errors=True)


# ----------------------------------------------------------------------------- reporte
def referencia_huella(task):
    """Huella de todo lo que define la tarea (proyecto, tests, version del benchmark y prompt): si cambia, la referencia caduca."""
    import hashlib
    project = project_of(task)
    tests = UNITY_TESTS_CS if project == "unity" else WEB_TESTS_JS if project == "web" else EXTRA_TESTS.get(task, "")
    blob = json.dumps({"task": task, "bench": BENCH_VERSION, "project": PROJECTS[project], "tests": tests,
                       "prompt": CLAUDE_SOLO_PROMPT_VERSION}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def referencia_guardada(task, ref):
    """Resultado de 'Claude solo' guardado para esta tarea y modelo, o None si no existe o la tarea cambio."""
    f = REFERENCIA_DIR / ref / f"{task}.json"
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return d.get("resultado") if d.get("huella") == referencia_huella(task) else None


def referencia_calcular(task, ref, node, log):
    res = run_claude_solo(task, ref, node, log)
    if not res.get("error"):
        f = REFERENCIA_DIR / ref / f"{task}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"huella": referencia_huella(task), "modelo": ref, "benchmark": BENCH_VERSION,
                                 "fecha": f"{datetime.datetime.now():%Y-%m-%d %H:%M}", "resultado": res},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def pair_diagnostics(results, reviewer):
    """Líneas del reporte sobre la calidad de la revisión, la eficiencia frente a Claude solo y la disciplina del modelo local."""
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    pr = [r for r in results if r.get("pair") and r.get("pair_run", {}).get("solo")]
    if not pr:
        return []
    L = []
    kinds = {"util": [], "sin_efecto": [], "perjudicial": [], "falsa_alarma": [], "innecesaria": []}
    fixed_tests = broken_tests = 0
    have_names = True
    requested = 0
    for r in pr:
        run, so, pa = r["pair_run"], r["pair_run"]["solo"], r["pair"]
        rounds = [x for x in run.get("rounds", []) if not x.get("error")]
        asked = [x for x in rounds if not x.get("approved")]
        requested += sum(len(x.get("fixes", [])) for x in asked)
        diff = pa["score"] - so["score"]
        if "tests_failed_all" in so and "tests_failed_all" in pa:
            a, b = set(so["tests_failed_all"]), set(pa["tests_failed_all"])
            fixed_tests += len(a - b)
            broken_tests += len(b - a)
        else:
            have_names = False
        if diff < -0.05:
            kinds["perjudicial"].append(r)
        elif so["score"] >= 9.5:
            kinds["falsa_alarma" if asked else "innecesaria"].append(r)
        elif diff > 0.05:
            kinds["util"].append(r)
        else:
            kinds["sin_efecto"].append(r)

    def cost_of(rs):
        return sum(x["pair_run"]["claude"].get("cost", 0) for x in rs), sum(x["pair_run"]["claude"].get("tokens", 0) for x in rs)

    L += ["  CALIDAD DE LA REVISIÓN", "  " + "-" * 88,
          f"  (Qué hizo la revisión de {reviewer} con cada tarea, comparando la nota de Qwen solo con la nota final de la pareja)"]
    rows = [("util", "Útil: Qwen solo fallaba y la revisión subió la nota"),
            ("sin_efecto", "Sin efecto: Qwen solo fallaba y la nota no cambió"),
            ("perjudicial", "Perjudicial: la nota BAJÓ tras aplicar las correcciones"),
            ("falsa_alarma", "Falsa alarma: Qwen solo ya sacaba >= 9.5 y aun así pidió cambios"),
            ("innecesaria", "Innecesaria: Qwen solo ya sacaba >= 9.5 (la revisión solo aprobó)")]
    for k, label in rows:
        rs = kinds[k]
        c, t = cost_of(rs)
        L.append(f"  {len(rs):>2} tarea(s)  {label}" + (f"   [{', '.join(x['task'] for x in rs)}]" if rs and len(rs) <= 6 else "")
                 + (f"   ({t:,} tok, {c:.3f}$)" if rs else ""))
    if have_names:
        L.append(f"  Tests reales que la revisión hizo pasar: {fixed_tests} · tests que rompió: {broken_tests}")
    L.append(f"  Correcciones pedidas en total: {requested} ({requested / len(pr):.1f} por tarea)")
    n_bad = len(kinds["falsa_alarma"]) + len(kinds["perjudicial"])
    n_useful = len(kinds["util"])
    L.append(f"  Utilidad: {n_useful} de {n_useful + len(kinds['sin_efecto']) + len(kinds['perjudicial'])} tareas con fallos mejoraron; "
             f"{n_bad} tarea(s) con revisión que molestó (falsa alarma o empeoró).")
    L.append("")

    cs = [r for r in results if r.get("claude_solo")]
    L += ["  EFICIENCIA FRENTE A CLAUDE SOLO", "  " + "-" * 88]
    s_pair = avg([r["pair"]["score"] for r in pr])
    c_pair = avg([r["pair_run"]["claude"].get("cost", 0) for r in pr])
    out_pair = avg([r["pair_run"]["claude"].get("output_tokens", 0) for r in pr])
    gain = sum(max(0.0, r["pair"]["score"] - r["pair_run"]["solo"]["score"]) for r in pr)
    tot_cost = sum(r["pair_run"]["claude"].get("cost", 0) for r in pr)
    if any("fresh_input" in r["pair_run"]["claude"] for r in pr):
        L.append(f"  Tokens de Claude por tarea (pareja): salida {out_pair:,.0f} · entrada nueva "
                 f"{avg([r['pair_run']['claude'].get('fresh_input', 0) for r in pr]):,.0f} · lectura de caché "
                 f"{avg([r['pair_run']['claude'].get('cache_read', 0) for r in pr]):,.0f}")
    else:
        L.append(f"  Tokens de salida de Claude por tarea (pareja): {out_pair:,.0f}")
    if cs:
        s_c = avg([r["claude_solo"]["score"] for r in cs])
        c_c = avg([r["claude_solo"]["claude"].get("cost", 0) for r in cs])
        out_c = avg([r["claude_solo"]["claude"].get("output_tokens", 0) for r in cs])
        if any("fresh_input" in r["claude_solo"]["claude"] for r in cs):
            L.append(f"  Tokens de Claude por tarea (solo):   salida {out_c:,.0f} · entrada nueva "
                     f"{avg([r['claude_solo']['claude'].get('fresh_input', 0) for r in cs]):,.0f} · lectura de caché "
                     f"{avg([r['claude_solo']['claude'].get('cache_read', 0) for r in cs]):,.0f}")
        else:
            L.append(f"  Tokens de salida de Claude por tarea (solo):   {out_c:,.0f}")
        if s_c:
            L.append(f"  La pareja conserva {s_pair / s_c:.0%} de la nota de Claude solo"
                     + (f" gastando {c_pair / c_c:.0%} del costo equivalente y {out_pair / out_c:.0%} de los tokens de salida."
                        if c_c and out_c else "."))
        if c_c and c_pair:
            L.append(f"  Nota por dólar equivalente: pareja {s_pair / c_pair:,.0f} vs Claude solo {s_c / c_c:,.0f}"
                     " (más alto = más eficiente; con suscripción léelo como 'cuota de uso').")
    if gain > 0.05 and tot_cost:
        L.append(f"  Cada punto de nota que aporta la revisión cuesta {tot_cost / gain:.3f}$ equivalentes (ganancia bruta {gain:.1f} puntos).")
    elif tot_cost:
        L.append(f"  La revisión no subió ninguna nota y costó {tot_cost:.3f}$ equivalentes en total.")
    L.append("")

    loc = [r["pair_run"]["local"] for r in pr if r["pair_run"].get("local")]
    if loc:
        L += ["  DISCIPLINA DEL MODELO LOCAL (primera pasada)", "  " + "-" * 88,
              f"  Pasos por tarea: {avg([x['steps'] for x in loc]):.1f} · llamadas a herramientas: {avg([x['tool_calls'] for x in loc]):.1f} · "
              f"errores de herramienta: {avg([x['tool_errors'] for x in loc]):.1f}",
              f"  Compiló con `build` antes de terminar: {sum(1 for x in loc if x['used_build'])}/{len(loc)} · "
              f"terminó sin error ni timeout: {sum(1 for x in loc if x['finished'] and not x['error'])}/{len(loc)} · "
              f"llamadas a herramientas escritas como texto: {sum(x['text_tool_leaks'] for x in loc)}", ""]
    return L


def write_pair_report(path, model, reviewer, results, modes, reference="haiku"):
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    pr = [r for r in results if r.get("pair")]
    cs = [r for r in results if r.get("claude_solo")]
    L = ["=" * 92, "  BENCHMARK PAREJA — modelo local escribe, Claude revisa", "=" * 92,
         f"  Modelo local:  {model.get('id')} ({model.get('quantization', '?')})",
         f"  Revisor:       Claude {reviewer} (tu suscripción, vía Claude Code)",
         f"  Claude solo:   {reference} (referencia compartida; se calcula una vez por tarea)",
         f"  Fecha:         {datetime.datetime.now():%Y-%m-%d %H:%M}    Benchmark: {PAIR_VERSION}    Tareas: {len(results)}", ""]
    if pr:
        s_solo = avg([r["pair_run"]["solo"]["score"] for r in pr])
        s_pair = avg([r["pair"]["score"] for r in pr])
        t_solo = avg([r["pair_run"]["solo"]["seconds"] for r in pr])
        t_pair = avg([r["pair"]["seconds"] for r in pr])
        tok_pair = avg([r["pair_run"]["claude"]["tokens"] for r in pr])
        cost_pair = avg([r["pair_run"]["claude"]["cost"] for r in pr])
        better = sum(1 for r in pr if r["pair"]["score"] > r["pair_run"]["solo"]["score"] + 0.05)
        worse = sum(1 for r in pr if r["pair"]["score"] < r["pair_run"]["solo"]["score"] - 0.05)
        approved_first = sum(1 for r in pr if r["pair_run"]["rounds"] and r["pair_run"]["rounds"][0].get("approved"))
        L += ["  RESUMEN", "  " + "-" * 88,
              f"  {'':26}{'nota':>8}{'tiempo/tarea':>15}{'tokens Claude/tarea':>22}{'costo API equiv.':>19}",
              f"  {'Qwen solo':26}{s_solo:8.1f}{t_solo:13.0f} s{0:>22}{'—':>19}",
              f"  {'Qwen + revisión ' + reviewer:26}{s_pair:8.1f}{t_pair:13.0f} s{tok_pair:22,.0f}{cost_pair:18.3f}$"]
        if cs:
            s_c = avg([r["claude_solo"]["score"] for r in cs])
            t_c = avg([r["claude_solo"]["seconds"] for r in cs])
            tok_c = avg([r["claude_solo"]["claude"]["tokens"] for r in cs])
            cost_c = avg([r["claude_solo"]["claude"]["cost"] for r in cs])
            L.append(f"  {'Claude ' + reference + ' solo':26}{s_c:8.1f}{t_c:13.0f} s{tok_c:22,.0f}{cost_c:18.3f}$")
        L += ["", f"  La revisión mejoró {better} tarea(s), empeoró {worse} y {approved_first} quedaron aprobadas en la primera revisión.",
              "  Tokens de Claude = entrada + salida + caché. Con suscripción no pagas por token: cuentan contra tus límites",
              "  de uso; el costo es solo una referencia de lo que valdría por API.", ""]
        verdict = []
        if cs:
            saving = 1 - tok_pair / tok_c if tok_c else 0
            gap = s_c - s_pair
            verdict.append(f"  · La pareja usa {saving:.0%} menos tokens de Claude que dejar a Claude hacerlo solo, "
                           f"con {abs(gap):.1f} puntos {'menos' if gap > 0 else 'más'} de nota.")
            verdict.append(f"  · En tiempo: pareja {t_pair:.0f} s vs Claude solo {t_c:.0f} s por tarea.")
        verdict.append(f"  · La revisión aporta {s_pair - s_solo:+.1f} puntos sobre Qwen solo.")
        L += ["  LECTURA RÁPIDA", "  " + "-" * 88] + verdict + [""]
        L += pair_diagnostics(results, reviewer)
    L += ["  DETALLE POR TAREA", "  " + "-" * 88,
          f"  {'tarea':9}{'Qwen solo':>11}{'pareja':>9}{'rondas':>8}{'tok Claude':>12}{'Claude solo':>13}{'tok Claude':>12}"]
    for r in results:
        p = r.get("pair_run") or {}
        rounds = len([x for x in p.get("rounds", []) if not x.get("approved") and not x.get("error")])
        c = r.get("claude_solo")
        tok_p = "{:,}".format(p["claude"]["tokens"]) if p else "—"
        tok_c = "{:,}".format(c["claude"]["tokens"]) if c else "—"
        s_solo = str((p.get("solo") or {}).get("score", "—"))
        s_pair = str((r.get("pair") or {}).get("score", "—"))
        s_cs = str((c or {}).get("score", "—"))
        L.append(f"  {r['task']:9}{s_solo:>11}{s_pair:>9}{(str(rounds) if p else '—'):>8}{tok_p:>12}{s_cs:>13}{tok_c:>12}")
        for x in p.get("rounds", []):
            if x.get("error"):
                L.append(f"      ⚠ revisión {x['round']}: {x['error'][:110]}")
            elif not x.get("approved"):
                for f in x.get("fixes", [])[:4]:
                    L.append(f"      · revisión {x['round']}: [{f.get('archivo', '?')}] {str(f.get('problema', ''))[:100]}")
        if r.get("pair") and r["pair"]["failed"]:
            L.append(f"      ✗ tras la pareja sigue fallando: {', '.join(r['pair']['failed'][:3])[:110]}")
        if c and c.get("failed"):
            L.append(f"      ✗ Claude solo falla: {', '.join(c['failed'][:3])[:110]}")
    L += ["", "  Nota: cada tarea usa los mismos tests reales del benchmark de agente. 'Qwen solo' es la primera pasada de la",
          "  pareja (antes de la revisión), así que ambas notas salen de la misma ejecución.", ""]
    text = "\n".join(L)
    Path(path).write_text(text, encoding="utf-8")
    return text


def main():
    if "--servidor-build" in sys.argv:
        i = sys.argv.index("--servidor-build")
        _build_server_main(sys.argv[i + 1], sys.argv[i + 2])
        return
    ap = argparse.ArgumentParser(description="Benchmark PAREJA: el modelo local escribe y Claude revisa.")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"[avanzado] URL del servidor de LM Studio (por defecto {DEFAULT_BASE})")
    ap.add_argument("--modelo", help="modelo local (por defecto el cargado)")
    ap.add_argument("--revisor", default="sonnet", choices=CLAUDE_CHOICES, help="modelo de Claude que revisa (por defecto sonnet)")
    ap.add_argument("--referencia", default="haiku", choices=CLAUDE_CHOICES,
                    help="modelo de Claude para la referencia 'Claude solo' (por defecto haiku). Se calcula una vez y se reutiliza "
                         "en todas las corridas, hasta que la tarea cambie")
    ap.add_argument("--modos", nargs="*", default=["pareja", "claude"], choices=["pareja", "claude"],
                    help="pareja = local + revision; claude = calcular la referencia 'Claude solo' que falte o haya caducado "
                         "(la ya guardada siempre se reutiliza)")
    ap.add_argument("--rondas", type=int, default=2, help="rondas máximas de revisión y corrección (por defecto 2)")
    ap.add_argument("--tareas", nargs="*", help=f"tareas a probar (por defecto: {' '.join(CODE_TASKS)})")
    ap.add_argument("--categorias", nargs="*", choices=[c for c, _, _ in CATEGORIES if c != "mcp"],
                    help="categorías a probar (por defecto todas las de código)")
    ap.add_argument("--repetir", action="store_true", help="ignorar resultados guardados del modelo local y rehacer todo")
    ap.add_argument("--repetir-referencia", action="store_true", help="volver a calcular la referencia de Claude solo aunque este guardada")
    ap.add_argument("--rapido", action="store_true", help="una sola tarea representativa por categoría")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    here = Path(__file__).resolve().parent
    print("=" * 74 + "\n BENCHMARK PAREJA — el modelo local escribe y Claude revisa\n" + "=" * 74)
    auth, err = claude_auth()
    if auth is None:
        sys.exit("✗ " + err)
    method = auth.get("authMethod") or ("claude.ai" if auth.get("loggedIn") else "none")
    if method == "none" or auth.get("loggedIn") is False:
        sys.exit("✗ Claude Code no tiene sesión iniciada. Ejecuta `claude` una vez e inicia sesión con tu cuenta.")
    print(f"Claude Code: {claude_exe()}  ·  sesión: {method}" + ("  ⚠ usa API key: se cobrará por token" if method == "api_key" else ""))
    try:
        http_json(base + "/v1/models", timeout=15)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No pude conectar con LM Studio en {base}: {e}")
    node = node_ready()
    tools = toolchains()
    cat_of = {t: c for c, _, ts in CATEGORIES for t in ts}
    cats_sel = args.categorias or [c for c, _, _ in CATEGORIES if c != "mcp"]
    if "pareja" not in args.modos:
        # Solo la referencia 'Claude solo': no hace falta modelo local.
        tasks = args.tareas or [t for t in CODE_TASKS if cat_of[t] in cats_sel and tools.get(cat_of[t], (True,))[0]]
        print(f"Referencia Claude {args.referencia} solo - tareas: {', '.join(tasks)}" + chr(10))
        for task in tasks:
            print(f"· {task}")
            log = lambda s: print("    " + s)
            guardada = None if args.repetir_referencia else referencia_guardada(task, args.referencia)
            if guardada:
                log(f"(guardada) Claude solo {guardada['score']}")
            else:
                referencia_calcular(task, args.referencia, node, log)
        print(chr(10) + f"Referencias en: {REFERENCIA_DIR / args.referencia}")
        return
    model = choose_model(base, args.modelo)
    mid = model["id"]
    out = here / "resultados_pareja" / f"{safe_name(mid)}__{args.revisor}" / PAIR_VERSION
    out.mkdir(parents=True, exist_ok=True)
    sys.stdout = Tee(sys.stdout, out / "log.txt")
    if args.tareas:
        tasks = args.tareas
    elif args.rapido:
        tasks = [QUICK_TASKS[c] for c in cats_sel if tools.get(c, (True,))[0]]
    else:
        tasks = [t for t in CODE_TASKS if cat_of[t] in cats_sel and tools.get(cat_of[t], (True,))[0]]
    skipped = [t for t in CODE_TASKS if not args.tareas and cat_of[t] in cats_sel and not args.rapido and t not in tasks]
    if skipped:
        print("Se omiten por falta de compilador: " + ", ".join(skipped))
    print(f"Tareas: {', '.join(tasks)}  ·  modos: {', '.join(args.modos)}  ·  rondas de revisión: {args.rondas}\n")
    results = []
    for task in tasks:
        f = out / f"{task}.json"
        r = json.loads(f.read_text(encoding="utf-8")) if f.exists() and not args.repetir else {"task": task}
        print(f"· {task}")
        log = lambda s: print("    " + s)
        if "pareja" in args.modos and "pair" not in r:
            p = run_pair(base, mid, task, args.revisor, args.rondas, node, log)
            r["pair_run"] = {k: v for k, v in p.items() if k not in ("pair", "files")}
            r["pair"] = p.get("pair")
            r["pair_files"] = p.get("files")
            log(f"→ pareja {r['pair']['score'] if r['pair'] else '—'}/10")
            f.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        elif r.get("pair"):
            log(f"(guardado) Qwen solo {r['pair_run']['solo']['score']} → pareja {r['pair']['score']}")
        ref = None if args.repetir_referencia else referencia_guardada(task, args.referencia)
        if ref is None and "claude" in args.modos:
            if not args.repetir_referencia and (REFERENCIA_DIR / args.referencia / f"{task}.json").exists():
                log("la tarea cambio desde que se calculo la referencia: se vuelve a correr Claude solo")
            ref = referencia_calcular(task, args.referencia, node, log)
        elif ref is not None:
            log(f"(referencia guardada) Claude {args.referencia} solo {ref['score']}")
        if ref is not None:
            r["claude_solo"] = ref
            r["claude_solo_modelo"] = args.referencia
        else:
            r.pop("claude_solo", None)
            log("sin referencia de Claude solo para esta tarea (usa --modos pareja claude para calcularla)")
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        results.append(r)
    report = here / f"calificacion_pareja_{safe_name(mid)}_{args.revisor}_{datetime.datetime.now():%Y%m%d-%H%M}.txt"
    text = write_pair_report(report, model, args.revisor, results, args.modos, args.referencia)
    print("\n" + text)
    print(f"Reporte guardado en: {report}")


if __name__ == "__main__":
    main()
