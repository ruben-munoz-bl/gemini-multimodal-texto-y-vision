"""Práctica: análisis de textos con la API de Gemini.

Para cada texto de la carpeta ``texts/`` se ejecutan cuatro tareas mediante
prompts estructurados que obligan al modelo a devolver JSON:

1. detección de idioma
2. extracción de entidades nombradas
3. análisis de sentimiento
4. resumen automático

Cada respuesta se compara con la verdad de referencia de ``texts/esperado.json``
y se genera un informe de precisión en ``results/informe.md`` (y ``results/informe.json``).
"""

import json
import os
import re
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

TEXTS_DIR = BASE_DIR / "texts"
RESULTS_DIR = BASE_DIR / "results"

client = genai.Client(api_key=API_KEY)


# ---------------------------------------------------------------------------
# Prompts estructurados: instrucciones + esquema JSON de respuesta
# ---------------------------------------------------------------------------

PROMPTS = {
    "idioma": {
        "titulo": "Detección de idioma",
        "system_instruction": (
            "Eres un lingüista experto. Respondes siempre en español y entregas "
            "exclusivamente el objeto JSON solicitado, sin comentarios ni marcado."
        ),
        "instrucciones": (
            "Tarea 1: detecta el idioma principal del texto.\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"idioma": "<código ISO 639-1, p. ej. es, en>", '
            '"nombre": "<nombre del idioma en español>", '
            '"confianza": <número entre 0 y 1>}\n'
            "Reglas: no analices el contenido ni lo traduzcas, únicamente identifica el idioma."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "idioma": {"type": "string", "description": "Código ISO 639-1: es, en..."},
                "nombre": {"type": "string", "description": "Nombre del idioma en español"},
                "confianza": {"type": "number", "description": "Confianza entre 0 y 1"},
            },
            "required": ["idioma", "nombre", "confianza"],
        },
    },
    "entidades": {
        "titulo": "Extracción de entidades nombradas",
        "system_instruction": (
            "Eres un experto en Procesamiento de Lenguaje Natural (PLN). Respondes "
            "siempre en español y entregas exclusivamente el objeto JSON solicitado."
        ),
        "instrucciones": (
            "Tarea 2: extrae las entidades nombradas del texto (personas, "
            "organizaciones, lugares, productos, eventos y fechas).\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"entidades": [{"texto": "<mención literal>", '
            '"categoria": "<PERSONA|ORGANIZACION|LUGAR|PRODUCTO|EVENTO|FECHA|OTRO>"}]}\n'
            "Reglas: usa las palabras exactas del texto, no las traduzcas ni las parafraseas; "
            "si no hay entidades devuelve una lista vacía."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "entidades": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "texto": {"type": "string"},
                            "categoria": {
                                "type": "string",
                                "enum": [
                                    "PERSONA",
                                    "ORGANIZACION",
                                    "LUGAR",
                                    "PRODUCTO",
                                    "EVENTO",
                                    "FECHA",
                                    "OTRO",
                                ],
                            },
                        },
                        "required": ["texto", "categoria"],
                    },
                }
            },
            "required": ["entidades"],
        },
    },
    "sentimiento": {
        "titulo": "Análisis de sentimiento",
        "system_instruction": (
            "Eres un analista de sentimiento textual. Respondes siempre en español y "
            "entregas exclusivamente el objeto JSON solicitado."
        ),
        "instrucciones": (
            "Tarea 3: clasifica el sentimiento global del texto.\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"sentimiento": "<positivo|negativo|neutral>", '
            '"confianza": <número entre 0 y 1>}\n'
            "Reglas: valora el tono general del texto completo. Los informativos objetivos "
            "sin carga emocional son neutrales; las noticias celebratorias o de éxito, "
            "y por supuesto las reseñas y mensajes con valoración clara, se clasifican por su tono."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "sentimiento": {"type": "string", "enum": ["positivo", "negativo", "neutral"]},
                "confianza": {"type": "number", "description": "Confianza entre 0 y 1"},
            },
            "required": ["sentimiento", "confianza"],
        },
    },
    "resumen": {
        "titulo": "Resumen automático",
        "system_instruction": (
            "Eres un redactor experto en síntesis de textos. Respondes siempre en español "
            "y entregas exclusivamente el objeto JSON solicitado."
        ),
        "instrucciones": (
            "Tarea 4: resume el texto en una única frase de como máximo 40 palabras.\n"
            "Responde SOLO con un objeto JSON con esta forma exacta:\n"
            '{"resumen": "<frase resumen>", "frases_clave": ["<idea1>", "<idea2>"]}\n'
            "Reglas: conserva los datos relevantes (nombres, cifras y fechas) y no añadas "
            "información que no aparezca en el texto."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "resumen": {"type": "string"},
                "frases_clave": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["resumen", "frases_clave"],
        },
    },
}


# ---------------------------------------------------------------------------
# Llamadas a la API
# ---------------------------------------------------------------------------

def construir_prompt(tarea: str, texto: str) -> str:
    """Une las instrucciones estructuradas con el texto a analizar."""
    return (
        f"{PROMPTS[tarea]['instrucciones']}\n\n"
        "Devuelve exclusivamente el objeto JSON, sin explicaciones y sin usar "
        "bloques de código.\n\n"
        f"TEXTO:\n\"\"\"\n{texto}\n\"\"\""
    )


def esperar_reintento(exc: Exception, intento: int) -> None:
    """Pausa exponencial; si la API indica los segundos a esperar, se respetan."""
    segundos = min(ESPERA_MAXIMA, 2**intento)
    mensaje = str(exc)
    aviso = re.search(r"retry in (\d+)s", mensaje)
    if aviso:
        segundos = min(ESPERA_MAXIMA, int(aviso.group(1)) + 1)
    time.sleep(segundos)


def llamar_modelo(tarea: str, texto: str) -> dict:
    """Una petición con prompt estructurado + esquema JSON. Reintenta ante errores."""
    cfg = PROMPTS[tarea]
    ultimo_error = None

    for intento in range(MAX_INTENTOS):
        try:
            interaccion = client.interactions.create(
                model=MODEL,
                input=construir_prompt(tarea, texto),
                system_instruction=cfg["system_instruction"],
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": cfg["schema"],
                },
                store=False,
            )
            salida = interaccion.output_text or ""
            return json.loads(salida)
        except (json.JSONDecodeError, genai_errors.APIError, ValueError) as error:
            ultimo_error = error
            print(f"    ! {tarea}: intento {intento + 1}/{MAX_INTENTOS} fallido ({error})")
            if intento < MAX_INTENTOS - 1:
                esperar_reintento(error, intento)

    raise RuntimeError(f"No se pudo completar la tarea '{tarea}': {ultimo_error}")


# ---------------------------------------------------------------------------
# Lectura de textos y verdad de referencia
# ---------------------------------------------------------------------------

def cargar_textos() -> list[tuple[str, str]]:
    """Devuelve [(nombre_fichero, texto), ...] ordenado por número de texto."""
    ficheros = sorted(
        TEXTS_DIR.glob("text*.txt"),
        key=lambda p: int(re.search(r"\d+", p.stem).group()),
    )
    if not ficheros:
        raise FileNotFoundError(f"No hay textos en {TEXTS_DIR}")
    return [(f.name, f.read_text(encoding="utf-8").strip()) for f in ficheros]


def cargar_esperado() -> dict:
    ruta = TEXTS_DIR / "esperado.json"
    if not ruta.exists():
        raise FileNotFoundError(f"Falta la verdad de referencia: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Métricas de comparación
# ---------------------------------------------------------------------------

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "was", "were", "have", "has",
    "not", "you", "your", "are", "but", "from", "they", "will", "del", "las",
    "los", "una", "unos", "unas", "por", "para", "con", "que", "por", "mas",
    "más", "sin", "sobre", "este", "esta", "como", "pero", "sus", "les", "dos",
}


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos ni puntuación: para comparar entidades."""
    texto = unicodedata.normalize("NFKD", str(texto).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9ñ\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def tokens(texto: str) -> list[str]:
    return [t for t in normalizar(texto).split() if len(t) >= 3 and t not in STOPWORDS]


def texto_entidad(entidad) -> str:
    if isinstance(entidad, dict):
        return str(entidad.get("texto") or entidad.get("nombre") or entidad.get("entidad") or "")
    return str(entidad)


def evaluar_entidades(predichas: list, esperadas: list) -> dict:
    """Precisión, recall y F1 con emparejamiento por contención normalizada."""
    pred_norm = [normalizar(texto_entidad(e)) for e in predichas]
    pred_norm = [p for p in pred_norm if p]
    esp_norm = [normalizar(e) for e in esperadas if normalizar(e)]

    aciertos = 0
    usados_pred = set()
    usados_esp = set()
    for i, p in enumerate(pred_norm):
        for j, e in enumerate(esp_norm):
            if j in usados_esp:
                continue
            if p == e or p in e or e in p:
                aciertos += 1
                usados_pred.add(i)
                usados_esp.add(j)
                break

    precision = aciertos / len(pred_norm) if pred_norm else 0.0
    recall = aciertos / len(esp_norm) if esp_norm else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "entidades_predichas": len(pred_norm),
        "entidades_esperadas": len(esp_norm),
        "aciertos": aciertos,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def evaluar_resumen(predicho: str, esperado: str) -> dict:
    """ROUGE-1 (precisión, recall y F1) entre resumen modelo y resumen de referencia."""
    pred_tokens = tokens(predicho)
    esp_tokens = tokens(esperado)
    comunes = sum((Counter(pred_tokens) & Counter(esp_tokens)).values())

    precision = comunes / len(pred_tokens) if pred_tokens else 0.0
    recall = comunes / len(esp_tokens) if esp_tokens else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "rouge1_precision": round(precision, 4),
        "rouge1_recall": round(recall, 4),
        "rouge1_f1": round(f1, 4),
    }


def evaluar_texto(nombre: str, resultado: dict, esperado: dict) -> dict:
    """Compara las cuatro respuestas del modelo con la verdad de referencia."""
    idioma = resultado.get("idioma") or {}
    sentimiento = resultado.get("sentimiento") or {}
    resumen = resultado.get("resumen") or {}

    idioma_pred = normalizar(idioma.get("idioma", ""))
    idioma_esp = normalizar(esperado["idioma"])
    sent_pred = normalizar(sentimiento.get("sentimiento", ""))
    sent_esp = normalizar(esperado["sentimiento"])

    return {
        "fichero": nombre,
        "tipo": esperado["tipo"],
        "idioma": {
            "predicho": idioma_pred,
            "esperado": idioma_esp,
            "correcto": idioma_pred == idioma_esp,
        },
        "sentimiento": {
            "predicho": sent_pred,
            "esperado": sent_esp,
            "correcto": sent_pred == sent_esp,
        },
        "entidades": evaluar_entidades(
            (resultado.get("entidades") or {}).get("entidades", []),
            esperado["entidades"],
        ),
        "resumen": {
            **evaluar_resumen(str(resumen.get("resumen", "")), esperado["resumen"]),
            "predicho": str(resumen.get("resumen", "")),
            "esperado": esperado["resumen"],
        },
    }


def agregar_metricas(evaluciones: list[dict]) -> dict:
    """Agrega las métricas por texto en una comparativa global por tarea."""
    validos = [e for e in evaluciones if not e.get("error")]

    idiomas = [e for e in validos if e["idioma"]["predicho"]]
    sentimientos = [e for e in validos if e["sentimiento"]["predicho"]]
    entidades = [e for e in validos if e["entidades"]["entidades_esperadas"]]
    resumenes = [e for e in validos if e["resumen"]["predicho"]]

    def media(valores: list[float]) -> float:
        return round(sum(valores) / len(valores), 4) if valores else 0.0

    metricas = {
        "textos_totales": len(evaluciones),
        "textos_evaluados": len(validos),
        "idioma": {
            "aciertos": sum(1 for e in idiomas if e["idioma"]["correcto"]),
            "evaluados": len(idiomas),
        },
        "sentimiento": {
            "aciertos": sum(1 for e in sentimientos if e["sentimiento"]["correcto"]),
            "evaluados": len(sentimientos),
        },
        "entidades": {
            "precision": media([e["entidades"]["precision"] for e in entidades]),
            "recall": media([e["entidades"]["recall"] for e in entidades]),
            "f1": media([e["entidades"]["f1"] for e in entidades]),
            "evaluados": len(entidades),
        },
        "resumen": {
            "rouge1_precision": media([e["resumen"]["rouge1_precision"] for e in resumenes]),
            "rouge1_recall": media([e["resumen"]["rouge1_recall"] for e in resumenes]),
            "rouge1_f1": media([e["resumen"]["rouge1_f1"] for e in resumenes]),
            "evaluados": len(resumenes),
        },
    }

    metricas["idioma"]["precision"] = (
        round(metricas["idioma"]["aciertos"] / metricas["idioma"]["evaluados"], 4)
        if metricas["idioma"]["evaluados"]
        else 0.0
    )
    metricas["sentimiento"]["precision"] = (
        round(metricas["sentimiento"]["aciertos"] / metricas["sentimiento"]["evaluados"], 4)
        if metricas["sentimiento"]["evaluados"]
        else 0.0
    )

    # Precisión media por tipo de documento (noticia, resena, email)
    por_tipo: dict[str, dict] = {}
    for e in validos:
        datos = por_tipo.setdefault(
            e["tipo"], {"textos": 0, "idioma_ok": 0, "sentimiento_ok": 0, "entidades_f1": [], "rouge1": []}
        )
        datos["textos"] += 1
        datos["idioma_ok"] += int(e["idioma"]["correcto"])
        datos["sentimiento_ok"] += int(e["sentimiento"]["correcto"])
        datos["entidades_f1"].append(e["entidades"]["f1"])
        datos["rouge1"].append(e["resumen"]["rouge1_f1"])
    for tipo, datos in por_tipo.items():
        metricas.setdefault("por_tipo", {})[tipo] = {
            "textos": datos["textos"],
            "precision_idioma": round(datos["idioma_ok"] / datos["textos"], 4),
            "precision_sentimiento": round(datos["sentimiento_ok"] / datos["textos"], 4),
            "entidades_f1": media(datos["entidades_f1"]),
            "rouge1_f1": media(datos["rouge1"]),
        }

    return metricas


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def pct(valor: float) -> str:
    return f"{valor * 100:.1f}%"


def generar_informe(evaluciones: list[dict], metricas: dict, ruta_md: Path, ruta_json: Path) -> str:
    lineas = [
        "# Informe de resultados: análisis de textos con Gemini",
        "",
        f"- **Modelo**: `{MODEL}`",
        f"- **Textos procesados**: {metricas['textos_totales']} "
        f"({', '.join(sorted({e['tipo'] for e in evaluciones}))})",
        f"- **Tareas por texto**: {len(PROMPTS)} "
        f"({', '.join(cfg['titulo'] for cfg in PROMPTS.values())})",
        f"- **Formato de respuesta**: JSON estructurado (`response_format` + esquema) "
        f"para las {len(PROMPTS)} tareas",
        "",
        "## 1. Comparativa de precisión por tarea",
        "",
        "| Tarea | Métrica | Resultado |",
        "|---|---|---|",
        f"| Detección de idioma | Aciertos | {metricas['idioma']['aciertos']}/"
        f"{metricas['idioma']['evaluados']} ({pct(metricas['idioma']['precision'])}) |",
        f"| Análisis de sentimiento | Aciertos | {metricas['sentimiento']['aciertos']}/"
        f"{metricas['sentimiento']['evaluados']} ({pct(metricas['sentimiento']['precision'])}) |",
        f"| Extracción de entidades | Precisión / Recall / F1 | "
        f"{pct(metricas['entidades']['precision'])} / {pct(metricas['entidades']['recall'])} / "
        f"{pct(metricas['entidades']['f1'])} |",
        f"| Resumen automático | ROUGE-1 F1 | {pct(metricas['resumen']['rouge1_f1'])} |",
        "",
    ]

    ranking = sorted(
        [
            ("Detección de idioma", metricas["idioma"]["precision"]),
            ("Análisis de sentimiento", metricas["sentimiento"]["precision"]),
            ("Extracción de entidades", metricas["entidades"]["f1"]),
            ("Resumen automático", metricas["resumen"]["rouge1_f1"]),
        ],
        key=lambda par: par[1],
        reverse=True,
    )
    lineas += [
        "### Ranking de tareas (de más a menos precisa)",
        "",
        "| # | Tarea | Métrica de referencia | Valor |",
        "|---|---|---|---|",
    ]
    for indice, (nombre, valor) in enumerate(ranking, start=1):
        metrica = "F1" if "entidades" in nombre else ("ROUGE-1 F1" if "Resumen" in nombre else "Exactitud")
        lineas.append(f"| {indice} | {nombre} | {metrica} | {pct(valor)} |")

    lineas += [
        "",
        "## 2. Resultados por tipo de texto",
        "",
        "| Tipo | Textos | Idioma | Sentimiento | Entidades (F1) | Resumen (ROUGE-1) |",
        "|---|---|---|---|---|---|",
    ]
    for tipo, datos in sorted(metricas.get("por_tipo", {}).items()):
        lineas.append(
            f"| {tipo} | {datos['textos']} | {pct(datos['precision_idioma'])} | "
            f"{pct(datos['precision_sentimiento'])} | {pct(datos['entidades_f1'])} | "
            f"{pct(datos['rouge1_f1'])} |"
        )

    lineas += [
        "",
        "## 3. Detalle por texto",
        "",
        "| Texto | Tipo | Idioma (pred./esp.) | Sentimiento (pred./esp.) | Entidades P/R/F1 | Resumen ROUGE-1 |",
        "|---|---|---|---|---|---|",
    ]
    for e in evaluciones:
        if e.get("error"):
            lineas.append(f"| {e['fichero']} | {e.get('tipo', '-')} | error | error | - | - |")
            continue
        ent = e["entidades"]
        marcadors = lambda ok: "OK" if ok else "FALLO"
        lineas.append(
            f"| {e['fichero']} | {e['tipo']} | "
            f"{e['idioma']['predicho']}/{e['idioma']['esperado']} ({marcadors(e['idioma']['correcto'])}) | "
            f"{e['sentimiento']['predicho']}/{e['sentimiento']['esperado']} "
            f"({marcadors(e['sentimiento']['correcto'])}) | "
            f"{pct(ent['precision'])}/{pct(ent['recall'])}/{pct(ent['f1'])} | "
            f"{pct(e['resumen']['rouge1_f1'])} |"
        )

    fallos = [
        e
        for e in evaluciones
        if not e.get("error")
        and (not e["idioma"]["correcto"] or not e["sentimiento"]["correcto"] or e["entidades"]["f1"] < 1)
    ]
    lineas += ["", "## 4. Conclusiones de la comparativa", ""]
    lineas.append(
        f"- La tarea más precisa es **{ranking[0][0]}** ({pct(ranking[0][1])}) y la menos "
        f"precisa es **{ranking[-1][0]}** ({pct(ranking[-1][1])})."
    )
    lineas.append(
        f"- Media global de exactitud en clasificación (idioma + sentimiento): "
        f"{pct((metricas['idioma']['precision'] + metricas['sentimiento']['precision']) / 2)}."
    )
    lineas.append(
        f"- En entidades nombradas se recuperó una media del {pct(metricas['entidades']['recall'])} "
        f"de las entidades de referencia con una precisión del {pct(metricas['entidades']['precision'])}."
    )
    lineas.append(
        f"- La similaridad léxica media entre resúmenes del modelo y de referencia es "
        f"{pct(metricas['resumen']['rouge1_f1'])} (ROUGE-1 F1)."
    )
    lineas.append(f"- Textos con algún fallo o solapamiento incompleto: {len(fallos)} de {metricas['textos_totales']}.")
    ejemplo = next((r for r in resultados_crudos if r.get("idioma")), None)
    lineas += ["", "## 5. Ejemplo de respuesta estructurada", ""]
    if ejemplo:
        lineas += [
            f"Texto de ejemplo: `{ejemplo['fichero']}`",
            "",
            "```json",
            json.dumps(
                {clave: ejemplo[clave] for clave in PROMPTS},
                ensure_ascii=False,
                indent=2,
            ),
            "```",
        ]
    lineas.append("")

    informe = "\n".join(lineas)
    ruta_md.write_text(informe, encoding="utf-8")
    ruta_json.write_text(
        json.dumps({"modelo": MODEL, "metricas": metricas, "detalles": evaluciones}, ensure_ascii=False, indent=2),
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


resultados_crudos: list[dict] = []


def main() -> None:
    global resultados_crudos

    textos = cargar_textos()
    esperado = cargar_esperado()
    RESULTS_DIR.mkdir(exist_ok=True)

    print(f"Modelo: {MODEL} | Textos: {len(textos)} | Tareas: {', '.join(PROMPTS)}")

    resultados_crudos = []
    evaluciones = []

    for indice, (nombre, texto) in enumerate(textos, start=1):
        print(f"\n[{indice}/{len(textos)}] {nombre}")
        resultado: dict = {}
        for tarea in PROMPTS:
            print(f"  - {PROMPTS[tarea]['titulo']}...", end=" ", flush=True)
            try:
                resultado[tarea] = llamar_modelo(tarea, texto)
                print("OK")
            except RuntimeError as error:
                resultado[tarea] = None
                print(f"ERROR ({error})")

        resultados_crudos.append({"fichero": nombre, **resultado})

        if any(valor is None for valor in resultado.values()):
            evaluciones.append(
                {
                    "fichero": nombre,
                    "tipo": esperado.get(nombre, {}).get("tipo", "-"),
                    "error": "alguna tarea fallo tras reintentos",
                }
            )
        else:
            evaluciones.append(evaluar_texto(nombre, resultado, esperado[nombre]))

        parcial = RESULTS_DIR / "parcial.json"
        parcial.write_text(
            json.dumps(
                {"modelo": MODEL, "resultados": resultados_crudos, "evaluaciones": evaluciones},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    metricas = agregar_metricas(evaluciones)

    agregado = {
        "modelo": MODEL,
        "metricas": metricas,
        "resultados": resultados_crudos,
    }
    ruta_agregado = siguiente_nombre("analisis")
    ruta_agregado.write_text(json.dumps(agregado, ensure_ascii=False, indent=2), encoding="utf-8")

    informe = generar_informe(
        evaluciones,
        metricas,
        RESULTS_DIR / "informe.md",
        RESULTS_DIR / "informe.json",
    )

    (BASE_DIR / "results.json").write_text(json.dumps(agregado, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"Idioma       : {metricas['idioma']['aciertos']}/{metricas['idioma']['evaluados']} "
          f"({pct(metricas['idioma']['precision'])})")
    print(f"Sentimiento  : {metricas['sentimiento']['aciertos']}/{metricas['sentimiento']['evaluados']} "
          f"({pct(metricas['sentimiento']['precision'])})")
    print(f"Entidades F1 : {pct(metricas['entidades']['f1'])}")
    print(f"Resumen R1   : {pct(metricas['resumen']['rouge1_f1'])}")
    print("=" * 70)
    print(f"Datos      -> {ruta_agregado}")
    print(f"Informe    -> {RESULTS_DIR / 'informe.md'}")
    print(f"Métricas   -> {RESULTS_DIR / 'informe.json'}")


if __name__ == "__main__":
    main()
