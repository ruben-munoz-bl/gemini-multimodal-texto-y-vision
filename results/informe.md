# Informe de resultados: análisis de textos con Gemini

- **Modelo**: `gemini-3.5-flash-lite`
- **Textos procesados**: 10 (email, noticia, resena)
- **Tareas por texto**: 4 (Detección de idioma, Extracción de entidades nombradas, Análisis de sentimiento, Resumen automático)
- **Formato de respuesta**: JSON estructurado (`response_format` + esquema) para las 4 tareas

## 1. Comparativa de precisión por tarea

| Tarea | Métrica | Resultado |
|---|---|---|
| Detección de idioma | Aciertos | 10/10 (100.0%) |
| Análisis de sentimiento | Aciertos | 10/10 (100.0%) |
| Extracción de entidades | Precisión / Recall / F1 | 82.4% / 83.0% / 80.1% |
| Resumen automático | ROUGE-1 F1 | 55.5% |

### Ranking de tareas (de más a menos precisa)

| # | Tarea | Métrica de referencia | Valor |
|---|---|---|---|
| 1 | Detección de idioma | Exactitud | 100.0% |
| 2 | Análisis de sentimiento | Exactitud | 100.0% |
| 3 | Extracción de entidades | F1 | 80.1% |
| 4 | Resumen automático | ROUGE-1 F1 | 55.5% |

## 2. Resultados por tipo de texto

| Tipo | Textos | Idioma | Sentimiento | Entidades (F1) | Resumen (ROUGE-1) |
|---|---|---|---|---|---|
| email | 3 | 100.0% | 100.0% | 82.2% | 61.9% |
| noticia | 4 | 100.0% | 100.0% | 72.0% | 61.4% |
| resena | 3 | 100.0% | 100.0% | 88.9% | 41.3% |

## 3. Detalle por texto

| Texto | Tipo | Idioma (pred./esp.) | Sentimiento (pred./esp.) | Entidades P/R/F1 | Resumen ROUGE-1 |
|---|---|---|---|---|---|
| text1.txt | noticia | es/es (OK) | neutral/neutral (OK) | 57.1%/80.0%/66.7% | 51.8% |
| text2.txt | resena | es/es (OK) | negativo/negativo (OK) | 100.0%/100.0%/100.0% | 33.3% |
| text3.txt | email | es/es (OK) | neutral/neutral (OK) | 100.0%/100.0%/100.0% | 76.2% |
| text4.txt | noticia | en/en (OK) | neutral/neutral (OK) | 75.0%/100.0%/85.7% | 53.3% |
| text5.txt | resena | es/es (OK) | positivo/positivo (OK) | 100.0%/100.0%/100.0% | 64.0% |
| text6.txt | email | en/en (OK) | negativo/negativo (OK) | 100.0%/50.0%/66.7% | 42.9% |
| text7.txt | noticia | es/es (OK) | positivo/positivo (OK) | 75.0%/100.0%/85.7% | 82.3% |
| text8.txt | resena | en/en (OK) | negativo/negativo (OK) | 100.0%/50.0%/66.7% | 26.7% |
| text9.txt | email | es/es (OK) | positivo/positivo (OK) | 66.7%/100.0%/80.0% | 66.7% |
| text10.txt | noticia | en/en (OK) | neutral/neutral (OK) | 50.0%/50.0%/50.0% | 58.1% |

## 4. Conclusiones de la comparativa

- La tarea más precisa es **Detección de idioma** (100.0%) y la menos precisa es **Resumen automático** (55.5%).
- Media global de exactitud en clasificación (idioma + sentimiento): 100.0%.
- En entidades nombradas se recuperó una media del 83.0% de las entidades de referencia con una precisión del 82.4%.
- La similaridad léxica media entre resúmenes del modelo y de referencia es 55.5% (ROUGE-1 F1).
- Textos con algún fallo o solapamiento incompleto: 7 de 10.

## 5. Ejemplo de respuesta estructurada

Texto de ejemplo: `text1.txt`

```json
{
  "idioma": {
    "idioma": "es",
    "nombre": "Español",
    "confianza": 1.0
  },
  "entidades": {
    "entidades": [
      {
        "texto": "Ayuntamiento de Valencia",
        "categoria": "ORGANIZACION"
      },
      {
        "texto": "este martes",
        "categoria": "FECHA"
      },
      {
        "texto": "línea 10",
        "categoria": "PRODUCTO"
      },
      {
        "texto": "Metrovalencia",
        "categoria": "ORGANIZACION"
      },
      {
        "texto": "Benimaclet",
        "categoria": "LUGAR"
      },
      {
        "texto": "aeropuerto",
        "categoria": "LUGAR"
      },
      {
        "texto": "María Campos",
        "categoria": "PERSONA"
      }
    ]
  },
  "sentimiento": {
    "sentimiento": "neutral",
    "confianza": 0.95
  },
  "resumen": {
    "resumen": "El Ayuntamiento de Valencia inauguró este martes la nueva línea 10 de Metrovalencia, valorada en 320 millones de euros, para conectar Benimaclet con el aeropuerto y reducir el tiempo de viaje en un 25%.",
    "frases_clave": [
      "Línea 10 de Metrovalencia",
      "320 millones de euros",
      "María Campos"
    ]
  }
}
```
