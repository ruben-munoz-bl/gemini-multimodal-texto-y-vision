# Google AI Studio y API de Gemini

Práctica en Python que usa la **API de Gemini** (a través de Google AI Studio) para analizar
textos e imágenes con prompts estructurados en JSON y comparar la precisión de los resultados
contra una verdad de referencia.


## Características de la práctica 1: texto

| Característica | Cómo se cumple |
|---|---|
| Script Python con la API de Gemini para **detección de idioma, entidades nombradas, sentimiento y resumen** | `gemini-text.py` ejecuta las 4 tareas sobre cada texto (40 llamadas por ejecución) |
| **Prompts estructurados** que piden resultados en **JSON** | Cada tarea tiene sus instrucciones, su `system_instruction` y su esquema JSON; la API recibe `response_format={"type": "text", "mime_type": "application/json", "schema": ...}`, que obliga al modelo a devolver JSON válido |
| Procesar **10 textos de ejemplo** (noticias, reseñas, emails) | `texts/text1.txt` … `texts/text10.txt`: 4 noticias, 3 reseñas y 3 emails, en español e inglés |
| **Informe de resultados comparando la precisión** | `results/informe.md` e `results/informe.json`, calculados contra la verdad de referencia `texts/esperado.json` |

## Características de la práctica 2: imágenes y documentos (multimodal)

| Característica | Cómo se cumple |
|---|---|
| Capacidades multimodales de Gemini para **OCR, descripción visual, clasificación de escenas y detección de objetos** | `gemini-images.py` ejecuta las 4 tareas sobre cada archivo (20 llamadas por ejecución), enviando texto + imagen o PDF a la API |
| **Prompts específicos por tarea visual** con respuesta en **JSON** | Cuatro prompts distintos (uno por tarea) con su esquema JSON y `response_format` estructurado; en PDF el OCR transcribe solo la primera página |
| **5 archivos de test**: 4 imágenes JPG + 1 PDF | `images/image-1.jpg` … `images/image-4.jpg` (interior con mascotas, foto urbana, producto y paisaje) más `images/pdf-1.pdf` (dossier de 46 páginas) |
| **Tabla comparativa de precisión por tipo de tarea visual** | `results/informe_imagenes.md` e `results/informe_imagenes.json`, contra la verdad de referencia `images/esperado.json` |

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
├── gemini-text.py      # Práctica 1: idioma + entidades + sentimiento + resumen + informe
├── gemini-images.py    # Práctica 2: OCR + descripción + escenas + objetos + informe
├── analisis_resultados.ipynb  # Notebook Jupyter con el análisis de resultados
├── images/             # Archivos de test: 4 imágenes (*.jpg) + 1 PDF
│   └── esperado.json   # Verdad de referencia de los archivos
├── texts/              # 10 textos de entrada (*.txt)
│   └── esperado.json   # Verdad de referencia de los textos
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

### Analizar las 4 imágenes y el PDF y generar la tabla comparativa

```bash
python gemini-images.py
```

El script:

1. Lee los archivos de `images/` (4 JPG: interior, urbana, producto y naturaleza, más el
   PDF `pdf-1.pdf` de 46 páginas).
2. Para cada uno lanza **4 peticiones multimodales** con prompts específicos (OCR, descripción
   de contenido visual, clasificación de escena y detección de objetos), cada una con su
   esquema JSON; los PDF se envían como `{"type": "document", "mime_type": "application/pdf"}`
   y el OCR transcribe solo su primera página.
3. Valida cada respuesta contra `images/esperado.json`.
4. Calcula las métricas y escribe la **tabla comparativa de precisión por tarea visual**.

Para regenerar el informe **sin volver a llamar a la API** (útil si solo has cambiado
`images/esperado.json` o los prompts):

```bash
python gemini-images.py --solo-evaluar
```

reutiliza las respuestas guardadas en `results/parcial_imagenes.json`.

> Si añades, borras o renombras archivos en `images/`, actualiza también las entradas
> correspondientes de `images/esperado.json`: sin referencia no se puede calcular su precisión.

### Ver el análisis de resultados en Jupyter

```bash
jupyter notebook analisis_resultados.ipynb
```

El notebook **no llama a la API**: carga `results/informe.json` e
`results/informe_imagenes.json` y presenta en tablas (pandas) y con gráfico opcional
(matplotlib) el resumen por tarea, los rankings, el detalle por archivo, un ejemplo de
respuesta JSON estructurada y las conclusiones.

### Salida

Cada ejecución imprime el resumen por consola y crea ficheros en `results/`:

- `results/analisis-N.json` — respuestas crudas + evaluación de cada texto.
- `results/informe.md` / `results/informe.json` — informe de la práctica de texto.
- `results/imagenes-analisis-N.json` — respuestas crudas + evaluación de cada archivo.
- `results/informe_imagenes.md` / `results/informe_imagenes.json` — **tabla comparativa de
  precisión de las tareas visuales**.
- `results/parcial.json` / `results/parcial_imagenes.json` — avance de cada ejecución.

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

### Métricas de la práctica de imágenes

| Tarea visual | Métrica | Descripción |
|---|---|---|
| OCR | F1 de tokens (unicode) | Comparación con el texto de referencia (en PDF, solo la primera página); si el archivo no tiene texto, acertar es devolver vacío (penaliza alucinaciones) |
| Descripción de contenido visual | ROUGE-1 (P/R/F1) | Solapamiento de términos entre la descripción del modelo y la de referencia |
| Clasificación de escenas | Exactitud | Acierto en `documento` / `urbana` / `producto` / `naturaleza` / `interior` |
| Detección de objetos | Precisión, Recall y F1 | Emparejamiento por contención con normalización de acentos y admitiendo sinónimos (`frasco` ≈ `bote`, `píldora` ≈ `cápsula`...) |

El informe de imágenes (`results/informe_imagenes.md`) incluye la **tabla comparativa por tarea
visual**, el ranking, los resultados **por tipo de imagen**, el detalle imagen a imagen y las
conclusiones. Su verdad de referencia es:

```json
{
  "image-3.jpg": {
    "tipo": "urbana",
    "escena": "urbana",
    "texto_ocr": "47 Pg. Marítim 9690 DLP",
    "descripcion": "Calle céntrica flanqueada por edificios altos...",
    "objetos": ["edificios", "semáforo", "coche", "autobús", "persona", "barrera"]
  }
}
```

---

## Ejemplo de llamada estructurada

```python
interaction = client.interactions.create(
    model="gemini-3.5-flash-lite",
    input=[
        {"type": "text", "text": prompt},                          # instrucciones + esquema
        {"type": "image", "data": ruta_imagen, "mime_type": "image/jpeg"},
    ],
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

(En la práctica de texto el `input` es directamente el prompt, sin la parte de imagen.)

---

## Seguridad de la API Key

Una API Key es una "llave" que da acceso a los servicios de tu cuenta, potencialmente de pago. Por eso:

- Guarda la clave **solo** en `.env` (variables de entorno).
- **Nunca** la subas a repositorios (GitHub, etc.).
- El único archivo permitido en el repositorio es `.env.example`, sin datos reales.
