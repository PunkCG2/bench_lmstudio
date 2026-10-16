# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es esto

Suite de benchmarks (en español, Python 3 sin dependencias externas) para evaluar modelos locales servidos por **LM Studio** (`http://localhost:1235`, API OpenAI-compatible + `/api/v1/models/load|unload`). No es un proyecto con build/lint/test propios: los "tests" son las tareas que cada benchmark califica. Windows es la plataforma objetivo (`.bat` lanzadores).

## Ejecutar

Punto de entrada: `correr_bench.bat` / `python bench.py`. Pregunta modelo → tipo (agente, asistente, chat, pareja) → revisor (haiku/sonnet, solo en pareja) y llama al `main()` del script elegido. LM Studio: `http://localhost:1235` (`--base` solo como opción avanzada).

```bash
python bench.py                                                        # interactivo
python bench.py --modelo qwen3.8 --tipo pareja --revisor sonnet        # sin preguntas
python bench.py --tipo agente --rapido                                 # un subconjunto representativo, 1 intento
python bench.py --all --tipo agente --rapido --excluir embed           # todos los modelos, uno por uno (nunca por defecto)
python bench.py --tipo agente --categorias unity web --tareas T-104    # filtros
python pareja_benchmark.py --modos claude --referencia haiku         # solo la referencia Claude solo (sin modelo local)
python revalorar.py --detalle --tareas W-202                           # recalifica resultados_pareja/ guardados con los tests actuales
```

Argumentos (los no reconocidos por `bench.py` pasan al benchmark): `--modelo`, `--tipo`, `--revisor`, `--all`, `--excluir`, `--base`; por benchmark `--categorias`, `--tareas` (agente/pareja), `--intentos` (agente/asistente/chat, por defecto 1), `--repetir`, `--rapido`, y solo pareja `--revisor` (sonnet por defecto, también haiku/opus/fable), `--referencia` (haiku por defecto), `--rondas` y `--modos` (`pareja`/`claude`; `claude` calcula la referencia que falte). `--categorias` en asistente = datos texto tts voz chatbot; en chat = conocimiento razonamiento formato vision web (las omitidas salen N/A y no pesan en la nota). `--rapido` agente/pareja = `QUICK_TASKS` (una tarea por categoría). Pareja exige Claude Code con sesión (`claude auth status`) y llama a `claude -p`.

`_deps_web/` tiene `node_modules` (jsdom, typescript) usados por los graders web y FB-601.

## Arquitectura

- **`agente_benchmark.py` es el núcleo** (tareas, Sandbox, build, calificadores, cliente LM Studio). Es un archivo monolítico con definiciones duplicadas (`run_build`, `grade_run`, `CATEGORIES`, `TASKS`…): **vale la última** en el archivo. Busca todas las ocurrencias antes de editar.
- **`pareja_benchmark.py` importa el núcleo** (`import agente_benchmark` + `globals().update`) y solo añade la capa de pareja: `claude_call`, `run_pair`, `run_claude_solo`, `pair_diagnostics`, `write_pair_report`, `main`. Tareas y graders se editan una sola vez, en el núcleo.
- `asistente_benchmark.py` y `chat_benchmark.py` son independientes (duplican helpers de LM Studio y comparten formato de resultados `resultados_<tipo>/<modelo>_<version>.json`).
- **Tareas de código:** `CATEGORIES` = `(id, nombre, [tareas])`: Unity T-102..104, Web W-201..203, CPP-301, UE-302, RS-401, NET-501, FB-601, MCP-70x. T-101 y W-204 se retiraron en v4 (quedan sus tests/ALLOWED por si se reactivan). IDs no se renumeran para no romper resultados guardados.
- **Tests y descripciones viven en archivos:** `tests/unity_tests.cs`, `tests/web_tests.js`, `tests/rs401_extra.rs`, `tests/fb601_extra.js`, `tareas/<ID>.md` (descripción que ve el modelo). El núcleo los carga al importarse y sobrescribe `PROJECTS[...]["docs/tasks/<ID>.md"]`. Los tests de CPP/UE/NET y la base de RS/FB siguen embebidos en `EXTRA_TESTS`.
- **Build:** C# de Unity con `dotnet build` contra `UNITY_STUBS` (API de Unity falsa embebida); TypeScript con `tsc` de `_deps_web`. Sin compilador, la categoría se omite (`toolchains()`).
- **Nota por tarea:** `task_score` = 0.65 funcional + 0.25 convenciones + 0.10 compila.
- **Pareja:** local implementa → Claude revisa (hasta `--rondas`) → local corrige; referencia "Claude solo". El reporte incluye `pair_diagnostics` (utilidad de la revisión, falsas alarmas, costo por punto, disciplina del modelo local).
- **`qwen_mcp.py`:** servidor MCP stdio mínimo que expone `qwen_escribir/corregir/estado`. `CLAUDE_qwen.md` es texto de delegación para pegar en *otros* proyectos.

## Resultados y estado

- Los resultados se guardan por modelo/versión y se reutilizan si existen (usa `--repetir` para forzar): `resultados_pareja/<modelo>__<revisor>/<PAIR_VERSION>/<TAREA>.json` + `log.txt` (agente: `resultados_agente/<modelo>/<BENCH_VERSION>/<TAREA>_intentoN.json`). Versiones actuales: agente `v4`, pareja `v2`; no se conservan resultados de versiones anteriores. Reportes de texto en la raíz: `calificacion_pareja_*.txt`, `comparativa_haiku_v3.txt`. Son datos generados; no los edites a mano.
- Al cambiar un grader o una tarea, los JSON guardados quedan obsoletos: sube la versión (`BENCH_VERSION` / `PAIR_VERSION`) o usa `revalorar.py` o ejecuta con `--repetir`.
- Los scripts reconfiguran stdout a UTF-8; mantén ese manejo (salida con tildes/emoji en consola Windows).

## Referencia "Claude solo" (pareja)
Se calcula una vez por tarea y modelo y se guarda en `referencia_claude/<modelo>/<TAREA>.json` con una huella (proyecto + tests + `BENCH_VERSION` + `CLAUDE_SOLO_PROMPT_VERSION`). Toda corrida de pareja la reutiliza; si la huella cambia (la tarea o sus tests cambiaron) se vuelve a calcular sola con `--modos pareja claude`, o a la fuerza con `--repetir-referencia`. Si cambias solo un calificador (código de `grade_run`) la huella no cambia: sube `BENCH_VERSION` o usa `--repetir-referencia`. El reporte la rotula `Claude <referencia> solo`, que puede ser otro modelo que el revisor.

## Contrato con el sitio (`E:/IA/bench-site`, `npm run data`)
`scripts/parse-report.js` del sitio lee `calificacion_pareja_*.txt` por texto exacto. No cambies sin revisar el parser: cabecera `Modelo local:  <id> (<cuantización>)`, `Revisor:       Claude <alias>`, `Fecha: … Benchmark: <v>`; sección `RESUMEN` con cabecera que contiene `tiempo/tarea` seguida de EXACTAMENTE 3 filas (local, pareja, Claude solo; por posición, terminan en `nota  N s  tokens  costo$|—`); `La revisión mejoró N tarea(s), empeoró M y K quedaron aprobadas…`; sección `DETALLE POR TAREA` con filas de 7 columnas numéricas, líneas `· revisión N: [archivo] texto` y `✗ …`. Secciones extra (p. ej. `pair_diagnostics`) deben ir antes de `DETALLE POR TAREA` y no repetir `Modelo local:`, `Revisor:` ni `Fecha:`. Sin fila de Claude solo (sin referencia) el parser lanza error. El sitio también falla si dos reportes tienen el mismo `<id>@<cuantización>`.
