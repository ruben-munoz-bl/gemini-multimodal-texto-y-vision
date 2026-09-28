# Google AI Studio y API de Gemini

Práctica en Python que usa la **API de Gemini** (a través de Google AI Studio) para analizar un
conjunto de textos con cuatro tareas de NLP y comparar la precisión de los resultados.

## Características de la práctica

| Característica | Cómo se cumple |
|---|---|
| Script Python con la API de Gemini para **detección de idioma, entidades nombradas, sentimiento y resumen** | `gemini-text.py` ejecuta las 4 tareas sobre cada texto (40 llamadas por ejecución) |
| **Prompts estructurados** que piden resultados en **JSON** | Cada tarea tiene sus instrucciones, su `system_instruction` y su esquema JSON; la API recibe `response_format={"type": "text", "mime_type": "application/json", "schema": ...}`, que obliga al modelo a devolver JSON válido |
| Procesar **10 textos de ejemplo** (noticias, reseñas, emails) | `texts/text1.txt` … `texts/text10.txt`: 4 noticias, 3 reseñas y 3 emails, en español e inglés |
| **Informe de resultados comparando la precisión** | `results/informe.md` e `results/informe.json`, calculados contra la verdad de referencia `texts/esperado.json` |

Otros scripts del repositorio:

- **`gemini-images.py`**: descripción de imágenes en JSON estructurado.

---

## Requisitos previos

- Python 3.10 o superior
- Una cuenta de Google
- Dependencias:
  ```bash
  pip install -r requirements.txt
  ```

---

## Obtención de la API Key

1. Inicia sesión en [Google AI Studio](https://aistudio.google.com/).
2. Pulsa **Get API Key**.
3. Selecciona **Create API Key**.
4. Rellena los dos campos del panel:
   - **Nombre**: un nombre identificativo y fácil de recordar.
   - **Project**: si aún no tienes un proyecto, selecciónalo para crear uno nuevo (también pedirá un nombre).
5. Confirma y tu API Key quedará creada. Cópiala para el paso siguiente.

---

## Configuración

1. Copia el archivo de ejemplo de variables de entorno:

   ```bash
   cp .env.example .env
   ```

2. Pega tu API Key en `.env`:

   ```env
   GEMINI_API_KEY="tu_api_key_aqui"
   # Opcional: modelo a utilizar (por defecto gemini-3.5-flash-lite)
   GEMINI_MODEL="gemini-3.5-flash-lite"
   ```

3. En tus scripts, la clave se carga así:

   ```python
   load_dotenv(BASE_DIR / ".env")

   if not os.getenv("GEMINI_API_KEY"):
       raise RuntimeError("No se encontro GEMINI_API_KEY en el archivo .env")

   client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
   ```

> **Nota:** en el nivel gratuito `gemini-3.5-flash` solo admite 20 peticiones/día, por eso el
> script usa `gemini-3.5-flash-lite` por defecto (se puede cambiar con `GEMINI_MODEL`).

---

## Estructura del proyecto

```text
.
├── .env                # Variables de entorno (no se sube al repositorio)
├── .env.example        # Plantilla de ejemplo sin datos reales
├── gemini-text.py      # Práctica: idioma + entidades + sentimiento + resumen + informe
├── gemini-images.py    # Descripción de imágenes (JSON estructurado)
├── images/             # Imágenes de entrada (*.jpg)
├── texts/              # 10 textos de entrada (*.txt)
│   └── esperado.json   # Verdad de referencia para calcular la precisión
└── results/            # Resultados e informes generados (*.json, *.md)
```

---

## Uso

### Analizar los 10 textos y generar el informe

```bash
python gemini-text.py
```

El script:

1. Lee los 10 textos de `texts/`.
2. Para cada uno lanza **4 peticiones** con prompts estructurados (idioma, entidades,
   sentimiento, resumen), cada una con su esquema JSON.
3. Valida cada respuesta contra `texts/esperado.json`.
4. Calcula las métricas y escribe los resultados.

### Describir imágenes

```bash
python gemini-images.py
```

### Salida

Cada ejecución imprime el resumen por consola y crea ficheros en `results/`:

- `results/analisis-N.json` — respuestas crudas + evaluación de cada texto.
- `results/informe.md` — **informe de resultados comparando la precisión**.
- `results/informe.json` — las mismas métricas en formato JSON.
- `results/parcial.json` — avance de la ejecución en curso.
- `results/image_descriptions-N.json` — descripciones de imágenes.

Además, `results.json` en la raíz siempre contiene el resultado de la última ejecución.

---

## Métricas del informe

| Tarea | Métrica | Descripción |
|---|---|---|
| Detección de idioma | Exactitud | % de aciertos del código ISO 639-1 (`es`, `en`) frente a la referencia |
| Análisis de sentimiento | Exactitud | % de aciertos en `positivo` / `negativo` / `neutral` |
| Extracción de entidades | Precisión, Recall y F1 | Emparejamiento por contención tras normalizar mayúsculas, acentos y puntuación |
| Resumen automático | ROUGE-1 (P/R/F1) | Solapamiento de términos entre el resumen del modelo y el de referencia |

El informe incluye además un **ranking de tareas por precisión**, la comparación **por tipo de
texto** (noticia / reseña / email), el detalle texto a texto y las conclusiones.

La verdad de referencia (`texts/esperado.json`) es la que se usa como "gold" para la comparación:

```json
{
  "text1.txt": {
    "tipo": "noticia",
    "idioma": "es",
    "sentimiento": "neutral",
    "entidades": ["Ayuntamiento de Valencia", "Valencia", "Metrovalencia"],
    "resumen": "Valencia inaugura la línea 10 de Metrovalencia..."
  }
}
```

---

## Ejemplo de llamada estructurada

```python
interaction = client.interactions.create(
    model="gemini-3.5-flash-lite",
    input=prompt,                       # instrucciones estructuradas + texto
    system_instruction=rol,             # rol del modelo
    response_format={                   # obliga a responder en JSON
        "type": "text",
        "mime_type": "application/json",
        "schema": schema,
    },
    store=False,
)
resultado = json.loads(interaction.output_text)
```

---

## Seguridad de la API Key

Una API Key es una "llave" que da acceso a los servicios de tu cuenta, potencialmente de pago. Por eso:

- Guarda la clave **solo** en `.env` (variables de entorno).
- **Nunca** la subas a repositorios (GitHub, etc.).
- El único archivo permitido en el repositorio es `.env.example`, sin datos reales.
