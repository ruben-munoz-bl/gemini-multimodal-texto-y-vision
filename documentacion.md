# Documentacion

## 2026-09-28

- Se adaptó la práctica a las características del enunciado en `gemini-text.py`:
  - **Cuatro tareas con la API de Gemini**: detección de idioma, extracción de entidades
    nombradas, análisis de sentimiento y resumen automático.
  - **Prompts estructurados**: cada tarea define instrucciones, `system_instruction` y un
    esquema JSON; la llamada usa `response_format={"type": "text", "mime_type":
    "application/json", "schema": ...}` para que la respuesta sea JSON válido siempre.
  - Reintentos con espera exponencial ante errores 429/503 y `store=False` para no conservar
    las interacciones.
- Nuevos textos de ejemplo en `texts/` (10 en total: 4 noticias, 3 reseñas y 3 emails, en
  español e inglés) y verdad de referencia en `texts/esperado.json`.
- Nuevo **informe de resultados comparando la precisión**: `results/informe.md` y
  `results/informe.json` con exactitud de idioma y sentimiento, P/R/F1 de entidades,
  ROUGE-1 de resúmenes, comparación por tipo de texto, ranking de tareas y conclusiones.
- `gemini-images.py` migrado también a respuesta JSON estructurada.
- Modelo por defecto `gemini-3.5-flash-lite` (configurable con `GEMINI_MODEL`), porque en
  nivel gratuito `gemini-3.5-flash` solo permite 20 peticiones/día.

## 2026-09-25

- Copilot corrigio `gemini.py` para generar un unico fichero por ejecucion, despues de analizar todos los textos.
- El fichero contiene los resultados agregados y usa el siguiente nombre libre `results/feelings_and_entities-n.json`.
