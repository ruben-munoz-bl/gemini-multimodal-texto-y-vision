import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

if not os.getenv("GEMINI_API_KEY"):
    raise RuntimeError("No se encontro GEMINI_API_KEY en el archivo .env")

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PROMPT = (
    "Describe la imagen de manera detallada. Responde SOLO con un objeto JSON de esta "
    'forma exacta: {"descripcion": "<texto detallado>", "objetos": ["<objeto>", ...], '
    '"escena": "<interior|exterior|otro>"}'
)

SCHEMA = {
    "type": "object",
    "properties": {
        "descripcion": {"type": "string"},
        "objetos": {"type": "array", "items": {"type": "string"}},
        "escena": {"type": "string", "enum": ["interior", "exterior", "otro"]},
    },
    "required": ["descripcion", "objetos", "escena"],
}

images = sorted((BASE_DIR / "images").glob("*.jpg"))
results_dir = BASE_DIR / "results"
results_dir.mkdir(exist_ok=True)

responses = []
for i, img_path in enumerate(images, start=1):
    interaction = client.interactions.create(
        model=MODEL,
        input=[
            {"type": "text", "text": PROMPT},
            {"type": "image", "data": img_path, "mime_type": "image/jpeg"},
        ],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": SCHEMA,
        },
        store=False,
    )
    salida = interaction.output_text
    print(f"Imagen {i} ({img_path.name}): analizada con éxito: {salida}")
    responses.append(json.loads(salida))

final_response = json.dumps({"results": responses}, ensure_ascii=False, indent=2)
print(f"Respuesta final:\n{final_response}")

result_number = 1
result_file = results_dir / f"image_descriptions-{result_number}.json"
while result_file.exists():
    result_number += 1
    result_file = results_dir / f"image_descriptions-{result_number}.json"
result_file.write_text(final_response, encoding="utf-8")

(BASE_DIR / "results.json").write_text(final_response, encoding="utf-8")
