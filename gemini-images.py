"""Práctica: análisis de imágenes y documentos (PDF) con Gemini multimodal.

Para cada archivo de la carpeta ``images/`` (imágenes JPG y documentos PDF) se
ejecutan cuatro tareas con prompts específicos que obligan al modelo a devolver JSON:

1. OCR (extracción de texto; en PDF solo se transcribe la primera página)
2. descripción de contenido visual
3. clasificación de escena
4. detección de elementos/objetos

Cada respuesta se compara con la verdad de referencia de ``images/esperado.json``
y se genera una tabla comparativa de precisión en ``results/informe_imagenes.md``
(y ``results/informe_imagenes.json``).
"""

import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("No se encontro GEMINI_API_KEY en el archivo .env")

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_INTENTOS = 5
ESPERA_MAXIMA = 60

IMAGES_DIR = BASE_DIR / "images"
RESULTS_DIR = BASE_DIR / "results"

client = genai.Client(api_key=API_KEY)


# ---------------------------------------------------------------------------
# Prompts específicos por tarea visual + esquema JSON de respuesta
# ---------------------------------------------------------------------------

PROMPTS = {
    "ocr": {
        "titulo": "OCR (extracción de texto)",
        "system_instruction": (
            "Eres un motor de OCR experto. Transcribes exactamente lo que hay en la imagen "
            "o en el documento, sin inventar texto, y respondes solo con el objeto JSON "
            "solicitado."
        ),
        "instrucciones": (
            "Tarea 1: extrae TODO el texto visible (rótulos, cifras, etiquetas, matrículas, "
            "documentos...). Si el archivo es un PDF, transcribe solo la PRIMERA página, "
            "respetando el orden en que aparece el texto.\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"texto": "<texto transcrito tal cual aparece>"}\n'
            'Reglas: devuelve {"texto": ""} solo si el archivo no contiene ninguna letra o '
            "cifra; si el texto es pequeño, está en perspectiva o algo desenfocado, transcribe "
            "igualmente las partes que logres descifrar, sin inventar palabras; conserva los "
            "números y signos."
        ),
        "schema": {
            "type": "object",
            "properties": {"texto": {"type": "string"}},
            "required": ["texto"],
        },
    },
    "descripcion": {
        "titulo": "Descripción de contenido visual",
        "system_instruction": (
            "Eres un describir de imágenes preciso y objetivo. Respondes siempre en español y "
            "entregas solo el objeto JSON solicitado."
        ),
        "instrucciones": (
            "Tarea 2: describe el contenido visual del archivo en una o dos frases, citando "
            "los elementos principales (sujetos, objetos, colores, fondo). Si es un PDF, "
            "describe de qué trata el documento y cómo está organizado.\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"descripcion": "<descripción objetiva>", "elementos": ["<elemento>", ...]}\n'
            "Reglas: no inventes elementos que no se vean; en 'elementos' incluye solo lo apreciable."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "descripcion": {"type": "string"},
                "elementos": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["descripcion", "elementos"],
        },
    },
    "escena": {
        "titulo": "Clasificación de escenas",
        "system_instruction": (
            "Eres un clasificador de escenas. Respondes siempre en español y entregas solo "
            "el objeto JSON solicitado."
        ),
        "instrucciones": (
            "Tarea 3: clasifica la escena principal del archivo en una de estas categorías:\n"
            "- documento: un PDF, papeles, formularios o alguien los está fotografiando\n"
            "- urbana: calles, edificios, tráfico o ciudades\n"
            "- producto: objeto fotografiado sobre fondo limpio de estudio\n"
            "- naturaleza: paisajes, agua, montañas o animales en exteriores\n"
            "- interior: escena doméstica o de interior, incluidas mascotas\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"escena": "<documento|urbana|producto|naturaleza|interior>", '
            '"confianza": <número entre 0 y 1>}\n'
            "Reglas: si el archivo es un PDF, la categoría es 'documento'; si no lo es, "
            "clasifica por el lugar donde se tomó la foto; si es un interior con mascotas, "
            "la categoría es 'interior', no 'naturaleza'."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "escena": {
                    "type": "string",
                    "enum": ["documento", "urbana", "producto", "naturaleza", "interior"],
                },
                "confianza": {"type": "number"},
            },
            "required": ["escena", "confianza"],
        },
    },
    "objetos": {
        "titulo": "Detección de objetos",
        "system_instruction": (
            "Eres un experto en detección de objetos en imágenes. Respondes siempre en español "
            "y entregas solo el objeto JSON solicitado."
        ),
        "instrucciones": (
            "Tarea 4: detecta los objetos principales visibles en la imagen. Si el archivo es "
            "un PDF, detecta los elementos propios del documento (portada, índice, tabla, "
            "diagrama, gráfico, formulario...).\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"objetos": [{"objeto": "<nombre del objeto>", '
            '"categoria": "<PERSONA|ANIMAL|VEHICULO|EDIFICIO|MOBILIARIO|OBJETO|TEXTO|OTRO>"}]}\n'
            "Reglas: usa nombres genéricos y concretos (por ejemplo 'coche', no 'coche rojo'); "
            "no repitas objetos y limitate a lo que se ve realmente."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "objetos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "objeto": {"type": "string"},
                            "categoria": {
                                "type": "string",
                                "enum": [
                                    "PERSONA",
                                    "ANIMAL",
                                    "VEHICULO",
                                    "EDIFICIO",
                                    "MOBILIARIO",
                                    "OBJETO",
                                    "TEXTO",
                                    "OTRO",
                                ],
                            },
                        },
                        "required": ["objeto", "categoria"],
                    },
                }
            },
            "required": ["objetos"],
        },
    },
}


# ---------------------------------------------------------------------------
# Llamadas a la API
# ---------------------------------------------------------------------------

def construir_prompt(tarea: str, nombre_archivo: str) -> str:
    return (
        f"{PROMPTS[tarea]['instrucciones']}\n\n"
        f"Archivo a analizar: {nombre_archivo}. Devuelve exclusivamente el objeto JSON, "
        "sin explicaciones y sin usar bloques de código."
    )


def esperar_reintento(exc: Exception, intento: int) -> None:
    segundos = min(ESPERA_MAXIMA, 2**intento)
    aviso = re.search(r"retry in (\d+)s", str(exc))
    if aviso:
        segundos = min(ESPERA_MAXIMA, int(aviso.group(1)) + 1)
    time.sleep(segundos)


MIMES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def parte_archivo(ruta: Path):
    """Parte multimodal de la petición: 'document' para PDF e 'image' para el resto."""
    mime = MIMES.get(ruta.suffix.lower(), "application/jpeg")
    if mime == "application/pdf":
        return {"type": "document", "data": ruta, "mime_type": mime}
    return {"type": "image", "data": ruta, "mime_type": mime}


def llamar_modelo(tarea: str, ruta_imagen: Path) -> dict:
    """Una petición multimodal con prompt específico + esquema JSON. Reintenta ante errores."""
    cfg = PROMPTS[tarea]
    ultimo_error = None

    for intento in range(MAX_INTENTOS):
        try:
            interaccion = client.interactions.create(
                model=MODEL,
                input=[
                    {"type": "text", "text": construir_prompt(tarea, ruta_imagen.name)},
                    parte_archivo(ruta_imagen),
                ],
                system_instruction=cfg["system_instruction"],
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": cfg["schema"],
                },
                store=False,
            )
            return json.loads(interaccion.output_text or "")
        except (json.JSONDecodeError, genai_errors.APIError, ValueError) as error:
            ultimo_error = error
            print(f"    ! {tarea}: intento {intento + 1}/{MAX_INTENTOS} fallido ({error})")
            if intento < MAX_INTENTOS - 1:
                esperar_reintento(error, intento)

    raise RuntimeError(f"No se pudo completar la tarea '{tarea}': {ultimo_error}")


# ---------------------------------------------------------------------------
# Lectura de archivos y verdad de referencia
# ---------------------------------------------------------------------------

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def cargar_imagenes() -> list[tuple[str, Path]]:
    ficheros = [
        p
        for p in IMAGES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSIONES and p.stem != "esperado"
    ]
    ficheros.sort(
        key=lambda p: (0 if p.suffix.lower() != ".pdf" else 1, int(re.search(r"\d+", p.stem).group()))
    )
    if not ficheros:
        raise FileNotFoundError(f"No hay imágenes ni PDFs en {IMAGES_DIR}")
    return [(f.name, f) for f in ficheros]


def cargar_esperado() -> dict:
    ruta = IMAGES_DIR / "esperado.json"
    if not ruta.exists():
        raise FileNotFoundError(f"Falta la verdad de referencia: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Métricas de comparación
# ---------------------------------------------------------------------------

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "was", "were", "have", "has",
    "not", "you", "your", "are", "but", "from", "they", "will", "del", "las",
    "los", "una", "unos", "unas", "por", "para", "con", "que", "mas", "más",
    "sin", "sobre", "este", "esta", "como", "pero", "sus", "les", "dos",
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9ñ\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def tokens(texto: str) -> list[str]:
    """Tokens sin acentos y con soporte unicode (incluye texto en cirílico para OCR)."""
    texto = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", str(texto)).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return [t for t in re.findall(r"[^\W_]+", texto, flags=re.UNICODE) if len(t) >= 2 or t.isdigit()]


def palabras(texto: str) -> list[str]:
    return [t for t in tokens(texto) if t not in STOPWORDS and len(t) >= 3]


# Equivalentes admitidos al comparar objetos detectados con los de referencia
SINONIMOS = {
    "frasco": "bote",
    "tarro": "bote",
    "envase": "bote",
    "pastilla": "capsula",
    "pildora": "capsula",
    "comprimido": "capsula",
    "gatito": "gato",
    "movil": "telefono",
    "celular": "telefono",
    "vehiculo": "coche",
    "automovil": "coche",
    "motocicleta": "moto",
    "cicla": "moto",
    "valla": "barrera",
    "vallas": "barrera",
    "verja": "barrera",
    "cercado": "barrera",
    "pajaro": "ave",
    "pajaros": "aves",
    "esquema": "diagrama",
    "esquemas": "diagrama",
    "grafico": "diagrama",
    "cuadro": "tabla",
    "cuadros": "tabla",
    "portadilla": "portada",
}


def canonico(texto: str) -> str:
    """Normaliza una mención y sustituye sinónimos por su forma canónica."""
    texto = normalizar(texto)
    palabras_ = [SINONIMOS.get(palabra, palabra) for palabra in texto.split()]
    return " ".join(palabras_)


def elemento_texto(elemento) -> str:
    if isinstance(elemento, dict):
        return str(
            elemento.get("objeto")
            or elemento.get("texto")
            or elemento.get("nombre")
            or elemento.get("elemento")
            or ""
        )
    return str(elemento)


def prf(predichos: list[str], esperados: list[str]) -> dict:
    """Precisión, recall y F1 con emparejamiento por contención normalizada."""
    pred_norm = [canonico(p) for p in predichos if canonico(p)]
    esp_norm = [canonico(e) for e in esperados if canonico(e)]

    aciertos = 0
    usados_esp = set()
    for p in pred_norm:
        for j, e in enumerate(esp_norm):
            if j in usados_esp:
                continue
            if p == e or p in e or e in p:
                aciertos += 1
                usados_esp.add(j)
                break

    precision = aciertos / len(pred_norm) if pred_norm else 0.0
    recall = aciertos / len(esp_norm) if esp_norm else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "predichos": len(pred_norm),
        "esperados": len(esp_norm),
        "aciertos": aciertos,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def rouge1(predicho: str, esperado: str) -> dict:
    pred_tokens = palabras(predicho)
    esp_tokens = palabras(esperado)
    comunes = sum((Counter(pred_tokens) & Counter(esp_tokens)).values())
    precision = comunes / len(pred_tokens) if pred_tokens else 0.0
    recall = comunes / len(esp_tokens) if esp_tokens else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "rouge1_precision": round(precision, 4),
        "rouge1_recall": round(recall, 4),
        "rouge1_f1": round(f1, 4),
    }


def evaluar_ocr(predicho: str, esperado: str) -> dict:
    """Si la imagen no tiene texto, acertar es devolver vacío (penaliza alucinaciones)."""
    pred_tokens = tokens(predicho)
    esp_tokens = tokens(esperado)
    if not esp_tokens:
        acierto = not pred_tokens
        return {
            "texto_esperado": esperado,
            "texto_predicho": predicho,
            "con_texto": False,
            "precision": 1.0 if acierto else 0.0,
            "recall": 1.0 if acierto else 0.0,
            "f1": 1.0 if acierto else 0.0,
        }
    resultado = rouge1(predicho, esperado)
    resultado.update(
        {
            "precision": resultado.pop("rouge1_precision"),
            "recall": resultado.pop("rouge1_recall"),
            "f1": resultado.pop("rouge1_f1"),
            "texto_esperado": esperado,
            "texto_predicho": predicho,
            "con_texto": True,
        }
    )
    return resultado


def evaluar_imagen(nombre: str, resultado: dict, esperado: dict) -> dict:
    escena_pred = normalizar((resultado.get("escena") or {}).get("escena", ""))
    escena_esp = normalizar(esperado["escena"])
    objetos = (resultado.get("objetos") or {}).get("objetos", [])
    descripcion = resultado.get("descripcion") or {}

    return {
        "fichero": nombre,
        "tipo": esperado["tipo"],
        "ocr": evaluar_ocr(str((resultado.get("ocr") or {}).get("texto", "")), esperado["texto_ocr"]),
        "escena": {
            "predicha": escena_pred,
            "esperada": escena_esp,
            "correcta": escena_pred == escena_esp,
            "confianza": (resultado.get("escena") or {}).get("confianza"),
        },
        "objetos": prf([elemento_texto(o) for o in objetos], esperado["objetos"]),
        "descripcion": {
            **rouge1(str(descripcion.get("descripcion", "")), esperado["descripcion"]),
            "predicha": str(descripcion.get("descripcion", "")),
            "esperada": esperado["descripcion"],
        },
    }


def agregar_metricas(evaluciones: list[dict]) -> dict:
    validos = [e for e in evaluciones if not e.get("error")]

    def media(valores: list[float]) -> float:
        return round(sum(valores) / len(valores), 4) if valores else 0.0

    metricas = {
        "imagenes_totales": len(evaluciones),
        "imagenes_evaluadas": len(validos),
        "ocr": {
            "f1": media([e["ocr"]["f1"] for e in validos]),
            "precision": media([e["ocr"]["precision"] for e in validos]),
            "recall": media([e["ocr"]["recall"] for e in validos]),
            "aciertos": sum(1 for e in validos if e["ocr"]["f1"] == 1.0),
            "evaluados": len(validos),
        },
        "descripcion": {
            "rouge1_precision": media([e["descripcion"]["rouge1_precision"] for e in validos]),
            "rouge1_recall": media([e["descripcion"]["rouge1_recall"] for e in validos]),
            "rouge1_f1": media([e["descripcion"]["rouge1_f1"] for e in validos]),
            "evaluados": len(validos),
        },
        "escena": {
            "aciertos": sum(1 for e in validos if e["escena"]["correcta"]),
            "evaluados": len(validos),
        },
        "objetos": {
            "precision": media([e["objetos"]["precision"] for e in validos]),
            "recall": media([e["objetos"]["recall"] for e in validos]),
            "f1": media([e["objetos"]["f1"] for e in validos]),
            "evaluados": len(validos),
        },
    }
    metricas["escena"]["precision"] = (
        round(metricas["escena"]["aciertos"] / metricas["escena"]["evaluados"], 4)
        if metricas["escena"]["evaluados"]
        else 0.0
    )

    por_tipo: dict[str, dict] = {}
    for e in validos:
        datos = por_tipo.setdefault(
            e["tipo"],
            {"imagenes": 0, "ocr_f1": [], "descripcion_r1": [], "escena_ok": 0, "objetos_f1": []},
        )
        datos["imagenes"] += 1
        datos["ocr_f1"].append(e["ocr"]["f1"])
        datos["descripcion_r1"].append(e["descripcion"]["rouge1_f1"])
        datos["escena_ok"] += int(e["escena"]["correcta"])
        datos["objetos_f1"].append(e["objetos"]["f1"])
    for tipo, datos in por_tipo.items():
        metricas.setdefault("por_tipo", {})[tipo] = {
            "imagenes": datos["imagenes"],
            "ocr_f1": media(datos["ocr_f1"]),
            "descripcion_rouge1": media(datos["descripcion_r1"]),
            "escena_precision": round(datos["escena_ok"] / datos["imagenes"], 4),
            "objetos_f1": media(datos["objetos_f1"]),
        }

    return metricas


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def pct(valor: float) -> str:
    return f"{valor * 100:.1f}%"


def generar_informe(
    evaluciones: list[dict],
    metricas: dict,
    resultados_crudos: list[dict],
    ruta_md: Path,
    ruta_json: Path,
) -> str:
    lineas = [
        "# Informe de resultados: análisis de imágenes y documentos con Gemini (multimodal)",
        "",
        f"- **Modelo**: `{MODEL}`",
        f"- **Archivos procesados**: {metricas['imagenes_totales']} "
        f"({', '.join(sorted({e['tipo'] for e in evaluciones if not e.get('error')}))})",
        f"- **Tareas visuales por archivo**: {len(PROMPTS)} "
        f"({', '.join(cfg['titulo'] for cfg in PROMPTS.values())})",
        "- **Formato de respuesta**: JSON estructurado (`response_format` + esquema) "
        f"para las {len(PROMPTS)} tareas, con un prompt específico por tarea",
        "",
        "## 1. Tabla comparativa de precisión por tarea visual",
        "",
        "| Tarea visual | Métrica | Resultado |",
        "|---|---|---|",
        f"| OCR (extracción de texto) | F1 medio (tokens) | {pct(metricas['ocr']['f1'])} "
        f"({metricas['ocr']['aciertos']}/{metricas['ocr']['evaluados']} ficheros exactos) |",
        f"| Descripción de contenido visual | ROUGE-1 F1 | {pct(metricas['descripcion']['rouge1_f1'])} |",
        f"| Clasificación de escenas | Exactitud | {metricas['escena']['aciertos']}/"
        f"{metricas['escena']['evaluados']} ({pct(metricas['escena']['precision'])}) |",
        f"| Detección de objetos | Precisión / Recall / F1 | {pct(metricas['objetos']['precision'])} / "
        f"{pct(metricas['objetos']['recall'])} / {pct(metricas['objetos']['f1'])} |",
        "",
        "### Ranking de tareas (de más a menos precisa)",
        "",
        "| # | Tarea visual | Métrica de referencia | Valor |",
        "|---|---|---|---|",
    ]

    ranking = sorted(
        [
            ("OCR (extracción de texto)", "F1 de tokens", metricas["ocr"]["f1"]),
            ("Descripción de contenido visual", "ROUGE-1 F1", metricas["descripcion"]["rouge1_f1"]),
            ("Clasificación de escenas", "Exactitud", metricas["escena"]["precision"]),
            ("Detección de objetos", "F1", metricas["objetos"]["f1"]),
        ],
        key=lambda fila: fila[2],
        reverse=True,
    )
    for indice, (nombre_tarea, metrica, valor) in enumerate(ranking, start=1):
        lineas.append(f"| {indice} | {nombre_tarea} | {metrica} | {pct(valor)} |")

    lineas += [
        "",
        "## 2. Resultados por tipo de archivo",
        "",
        "| Tipo | Archivos | OCR (F1) | Descripción (ROUGE-1) | Escena | Objetos (F1) |",
        "|---|---|---|---|---|---|",
    ]
    for tipo, datos in sorted(metricas.get("por_tipo", {}).items()):
        lineas.append(
            f"| {tipo} | {datos['imagenes']} | {pct(datos['ocr_f1'])} | "
            f"{pct(datos['descripcion_rouge1'])} | {pct(datos['escena_precision'])} | "
            f"{pct(datos['objetos_f1'])} |"
        )

    lineas += [
        "",
        "## 3. Detalle por archivo",
        "",
        "| Archivo | Tipo | OCR (F1) | Escena (pred./esp.) | Objetos P/R/F1 | Descripción (ROUGE-1) |",
        "|---|---|---|---|---|---|",
    ]
    for e in evaluciones:
        if e.get("error"):
            lineas.append(f"| {e['fichero']} | {e.get('tipo', '-')} | error | error | - | - |")
            continue
        ok = "OK" if e["escena"]["correcta"] else "FALLO"
        lineas.append(
            f"| {e['fichero']} | {e['tipo']} | {pct(e['ocr']['f1'])} | "
            f"{e['escena']['predicha']}/{e['escena']['esperada']} ({ok}) | "
            f"{pct(e['objetos']['precision'])}/{pct(e['objetos']['recall'])}/{pct(e['objetos']['f1'])} | "
            f"{pct(e['descripcion']['rouge1_f1'])} |"
        )

    fallos_escena = [e for e in evaluciones if not e.get("error") and not e["escena"]["correcta"]]
    textos_con = [e for e in evaluciones if not e.get("error") and e["ocr"]["con_texto"]]
    textos_sin = [e for e in evaluciones if not e.get("error") and not e["ocr"]["con_texto"]]

    lineas += ["", "## 4. Conclusiones de la comparativa", ""]
    lineas.append(
        f"- La tarea visual más precisa es **{ranking[0][0]}** ({pct(ranking[0][2])}) y la menos "
        f"precisa es **{ranking[-1][0]}** ({pct(ranking[-1][2])})."
    )
    lineas.append(
        f"- La clasificación de escenas acertó en {metricas['escena']['aciertos']}/"
        f"{metricas['escena']['evaluados']} archivos."
    )
    lineas.append(
        f"- En OCR: F1 medio {pct(metricas['ocr']['f1'])}; con texto legible "
        f"({len(textos_con)} archivos) F1 {pct(sum(e['ocr']['f1'] for e in textos_con) / len(textos_con)) if textos_con else '0.0%'} "
        f"y en archivos sin texto ({len(textos_sin)}) acertó el vacío en "
        f"{sum(1 for e in textos_sin if e['ocr']['f1'] == 1.0)}/{len(textos_sin)}."
    )
    lineas.append(
        f"- En detección de objetos se recuperó una media del {pct(metricas['objetos']['recall'])} "
        f"de los objetos de referencia con una precisión del {pct(metricas['objetos']['precision'])}."
    )
    lineas.append(
        f"- La similaridad léxica media entre descripciones del modelo y de referencia es "
        f"{pct(metricas['descripcion']['rouge1_f1'])} (ROUGE-1 F1)."
    )
    if fallos_escena:
        lineas.append(
            "- Escenas mal clasificadas: " + ", ".join(e["fichero"] for e in fallos_escena) + "."
        )

    con_ocr = [
        r for r in resultados_crudos if r.get("escena") and r.get("ocr", {}).get("texto")
    ]
    ejemplo = max(con_ocr, key=lambda r: len(r["ocr"]["texto"]), default=None) or next(
        (r for r in resultados_crudos if r.get("escena")), None
    )
    lineas += ["", "## 5. Ejemplo de respuesta estructurada", ""]
    if ejemplo:
        lineas += [
            f"Archivo de ejemplo: `{ejemplo['fichero']}`",
            "",
            "```json",
            json.dumps({clave: ejemplo[clave] for clave in PROMPTS}, ensure_ascii=False, indent=2),
            "```",
        ]
    lineas.append("")

    informe = "\n".join(lineas)
    ruta_md.write_text(informe, encoding="utf-8")
    ruta_json.write_text(
        json.dumps(
            {"modelo": MODEL, "metricas": metricas, "detalles": evaluciones},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return informe


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def siguiente_nombre(prefijo: str) -> Path:
    numero = 1
    ruta = RESULTS_DIR / f"{prefijo}-{numero}.json"
    while ruta.exists():
        numero += 1
        ruta = RESULTS_DIR / f"{prefijo}-{numero}.json"
    return ruta


def evaluar_todo(resultados_crudos: list[dict], esperado: dict) -> list[dict]:
    """Evalúa todas las respuestas crudas contra la verdad de referencia."""
    evaluciones: list[dict] = []
    for bruto in resultados_crudos:
        nombre = bruto["fichero"]
        resultado = {clave: valor for clave, valor in bruto.items() if clave != "fichero"}
        if nombre not in esperado:
            evaluciones.append(
                {"fichero": nombre, "tipo": "-", "error": "sin referencia en esperado.json"}
            )
        elif any(valor is None for valor in resultado.values()):
            evaluciones.append(
                {"fichero": nombre, "tipo": esperado[nombre].get("tipo", "-"), "error": "fallo"}
            )
        else:
            evaluciones.append(evaluar_imagen(nombre, resultado, esperado[nombre]))
    return evaluciones


def guardar_parcial(resultados_crudos: list[dict], esperado: dict) -> None:
    (RESULTS_DIR / "parcial_imagenes.json").write_text(
        json.dumps(
            {
                "modelo": MODEL,
                "resultados": resultados_crudos,
                "evaluaciones": evaluar_todo(resultados_crudos, esperado),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main(argv: list[str]) -> None:
    solo_evaluar = "--solo-evaluar" in argv
    esperado = cargar_esperado()
    RESULTS_DIR.mkdir(exist_ok=True)
    parcial_ruta = RESULTS_DIR / "parcial_imagenes.json"
    resultados_crudos: list[dict] = []

    if solo_evaluar:
        if not parcial_ruta.exists():
            raise FileNotFoundError(
                f"No existe {parcial_ruta}: primero ejecuta el script sin --solo-evaluar"
            )
        datos = json.loads(parcial_ruta.read_text(encoding="utf-8"))
        resultados_crudos = datos["resultados"]
        print(
            f"[--solo-evaluar] {len(resultados_crudos)} archivos desde {parcial_ruta.name} "
            "(sin llamadas a la API)"
        )
    else:
        imagenes = cargar_imagenes()
        print(
            f"Modelo: {MODEL} | Archivos: {len(imagenes)} | Tareas: {', '.join(PROMPTS)}"
        )

        for indice, (nombre, ruta) in enumerate(imagenes, start=1):
            print(f"\n[{indice}/{len(imagenes)}] {nombre}")
            resultado: dict = {}
            for tarea in PROMPTS:
                print(f"  - {PROMPTS[tarea]['titulo']}...", end=" ", flush=True)
                try:
                    resultado[tarea] = llamar_modelo(tarea, ruta)
                    print("OK")
                except RuntimeError as error:
                    resultado[tarea] = None
                    print(f"ERROR ({error})")

            resultados_crudos.append({"fichero": nombre, **resultado})
            guardar_parcial(resultados_crudos, esperado)

    evaluciones = evaluar_todo(resultados_crudos, esperado)
    metricas = agregar_metricas(evaluciones)

    agregado = {"modelo": MODEL, "metricas": metricas, "resultados": resultados_crudos}
    ruta_agregado = siguiente_nombre("imagenes-analisis")
    ruta_agregado.write_text(json.dumps(agregado, ensure_ascii=False, indent=2), encoding="utf-8")

    generar_informe(
        evaluciones,
        metricas,
        resultados_crudos,
        RESULTS_DIR / "informe_imagenes.md",
        RESULTS_DIR / "informe_imagenes.json",
    )

    (BASE_DIR / "results.json").write_text(
        json.dumps(agregado, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 70)
    print(f"OCR F1       : {pct(metricas['ocr']['f1'])}")
    print(f"Descripcion  : {pct(metricas['descripcion']['rouge1_f1'])} (ROUGE-1 F1)")
    print(f"Escena       : {metricas['escena']['aciertos']}/{metricas['escena']['evaluados']} "
          f"({pct(metricas['escena']['precision'])})")
    print(f"Objetos F1   : {pct(metricas['objetos']['f1'])}")
    print("=" * 70)
    print(f"Datos    -> {ruta_agregado}")
    print(f"Informe  -> {RESULTS_DIR / 'informe_imagenes.md'}")
    print(f"Metricas -> {RESULTS_DIR / 'informe_imagenes.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
