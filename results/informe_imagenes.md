# Informe de resultados: análisis de imágenes y documentos con Gemini (multimodal)

- **Modelo**: `gemini-3.5-flash-lite`
- **Archivos procesados**: 5 (interior, naturaleza, pdf, producto, urbana)
- **Tareas visuales por archivo**: 4 (OCR (extracción de texto), Descripción de contenido visual, Clasificación de escenas, Detección de objetos)
- **Formato de respuesta**: JSON estructurado (`response_format` + esquema) para las 4 tareas, con un prompt específico por tarea

## 1. Tabla comparativa de precisión por tarea visual

| Tarea visual | Métrica | Resultado |
|---|---|---|
| OCR (extracción de texto) | F1 medio (tokens) | 100.0% (5/5 ficheros exactos) |
| Descripción de contenido visual | ROUGE-1 F1 | 43.2% |
| Clasificación de escenas | Exactitud | 5/5 (100.0%) |
| Detección de objetos | Precisión / Recall / F1 | 75.0% / 66.7% / 69.0% |

### Ranking de tareas (de más a menos precisa)

| # | Tarea visual | Métrica de referencia | Valor |
|---|---|---|---|
| 1 | OCR (extracción de texto) | F1 de tokens | 100.0% |
| 2 | Clasificación de escenas | Exactitud | 100.0% |
| 3 | Detección de objetos | F1 | 69.0% |
| 4 | Descripción de contenido visual | ROUGE-1 F1 | 43.2% |

## 2. Resultados por tipo de archivo

| Tipo | Archivos | OCR (F1) | Descripción (ROUGE-1) | Escena | Objetos (F1) |
|---|---|---|---|---|---|
| interior | 1 | 100.0% | 68.8% | 100.0% | 33.3% |
| naturaleza | 1 | 100.0% | 43.5% | 100.0% | 100.0% |
| pdf | 1 | 100.0% | 39.3% | 100.0% | 85.7% |
| producto | 1 | 100.0% | 32.3% | 100.0% | 40.0% |
| urbana | 1 | 100.0% | 32.3% | 100.0% | 85.7% |

## 3. Detalle por archivo

| Archivo | Tipo | OCR (F1) | Escena (pred./esp.) | Objetos P/R/F1 | Descripción (ROUGE-1) |
|---|---|---|---|---|---|
| image-1.jpg | interior | 100.0% | interior/interior (OK) | 50.0%/25.0%/33.3% | 68.8% |
| image-2.jpg | urbana | 100.0% | urbana/urbana (OK) | 75.0%/100.0%/85.7% | 32.3% |
| image-3.jpg | producto | 100.0% | producto/producto (OK) | 50.0%/33.3%/40.0% | 32.3% |
| image-4.jpg | naturaleza | 100.0% | naturaleza/naturaleza (OK) | 100.0%/100.0%/100.0% | 43.5% |
| pdf-1.pdf | pdf | 100.0% | documento/documento (OK) | 100.0%/75.0%/85.7% | 39.3% |

## 4. Conclusiones de la comparativa

- La tarea visual más precisa es **OCR (extracción de texto)** (100.0%) y la menos precisa es **Descripción de contenido visual** (43.2%).
- La clasificación de escenas acertó en 5/5 archivos.
- En OCR: F1 medio 100.0%; con texto legible (2 archivos) F1 100.0% y en archivos sin texto (3) acertó el vacío en 3/3.
- En detección de objetos se recuperó una media del 66.7% de los objetos de referencia con una precisión del 75.0%.
- La similaridad léxica media entre descripciones del modelo y de referencia es 43.2% (ROUGE-1 F1).

## 5. Ejemplo de respuesta estructurada

Archivo de ejemplo: `pdf-1.pdf`

```json
{
  "ocr": {
    "texto": "Dossier de supòsits - Disseny de Base de\nDades\nRubén Muñoz Blanco\nCicle: CFGS 1DAM\nProfesors: Ana Bono Marin i Maria Roser Agramunt Marques\nCASOS BÀSICS\nSupòsit 0 (Exemple)\nDisseny Conceptual\nDisseny Lògic Relacional\nTaules amb dades representavies\nSupòsit 1| Biblioteca Digital\nDisseny Conceptual\nDisseny Lògic Relacional\nTaules amb dades representavies\nSupòsit 2 | Cinema\nDisseny Conceptual\nDisseny Lògic Relacional\nTaules amb dades representavies\nSupòsit 3 | Cursos en línea\nDisseny Conceptual\nDisseny Lògic Relacional\nTaules amb dades representavies\nSupòsit 4 | Projectes\nDisseny Conceptual\nDisseny Lògic Relacional\nTaules amb dades representatives\nSupòsit 5 | Productes-consumidor\nDisseny Conceptual\nDossier de supòsits - Disseny de Base de Dades 1"
  },
  "descripcion": {
    "descripcion": "El documento es un dossier académico titulado 'Dossier de supòsits - Disseny de Base de Dades', organizado en diferentes supuestos prácticos y casos avanzados que incluyen descripciones de entidades, diagramas de diseño conceptual, esquemas de diseño lógico relacional y tablas de datos representativos.",
    "elementos": [
      "título del documento",
      "texto explicativo",
      "diagramas de diseño conceptual",
      "esquemas lógicos relacionales",
      "tablas con datos representativos",
      "reglas de integridad"
    ]
  },
  "escena": {
    "escena": "documento",
    "confianza": 1.0
  },
  "objetos": {
    "objetos": [
      {
        "objeto": "portada",
        "categoria": "TEXTO"
      },
      {
        "objeto": "diagrama",
        "categoria": "OTRO"
      },
      {
        "objeto": "tabla",
        "categoria": "TEXTO"
      }
    ]
  }
}
```
