## Delegar en Qwen (modelo local)

Tienes el servidor MCP `qwen-local`: un modelo local (Qwen3.8 27B en LM Studio) que escribe código sin gastar tu
cuota de Claude, pero que a veces se equivoca. Tu papel es de arquitecto y revisor.

- **Archivos nuevos y autocontenidos** (scripts, clases, componentes de Unity, utilidades, herramientas de editor,
  scripts de Python o PowerShell): no los escribas tú. Llama a `qwen_escribir` con instrucciones precisas
  (propósito, firmas públicas, namespace, convenciones del proyecto, casos borde) y pasa en `archivos_contexto`
  los archivos que Qwen necesita ver (interfaces, clases que usa, CLAUDE.md o convenciones).
- **Revisión:** lee el archivo con Read y compáralo con los requisitos. Si hay problemas, llama a `qwen_corregir`
  con una lista numerada de correcciones concretas (qué está mal y cómo corregirlo). Revisa el diff que devuelve.
- **Máximo 2 rondas** de corrección. Si después sigue mal, o la corrección es pequeña (menos de ~15 líneas),
  corrígelo tú directamente.
- **Hazlo tú** cuando el cambio toque varios archivos existentes, requiera entender gran parte del proyecto,
  o sea una edición puntual en un archivo grande.
- Si el proyecto se puede compilar o probar, hazlo al final. Resume qué escribió Qwen y qué corregiste tú.
- Si `qwen_escribir` falla porque LM Studio no responde, avísame y continúa tú.
