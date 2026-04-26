"""OpenAPI description and tags for /docs and /redoc."""

API_TITLE = "CapillarAI"
API_VERSION = "1.0.0"

API_DESCRIPTION = """
Simulación visual de resultado capilar (inpainting). **No es asesoramiento médico.**

## Autenticación
Envía `X-API-Key: <tu_clave>` o `Authorization: Bearer <tu_clave>`.

Claves: variable `API_KEYS` (coma-separadas) y/o base SQLite `API_KEYS_DB` con claves hasheadas (`scripts/add_api_key.py`).

## Límites
- Tamaño máximo de imagen: **10 MB** (`413` si se excede).
- Rate limit por clave o IP: `RATE_LIMIT_UPLOAD`, `RATE_LIMIT_GENERATE` (p. ej. `60/minute`).
- Cola GPU: si la cola está llena → **503**; si la inferencia excede el timeout → **504**.

## CORS
Para navegadores, define `CORS_ORIGINS` con los orígenes permitidos (coma-separadas). En producción no uses `*`.

## Datos
Las imágenes se procesan en memoria para generar la respuesta; **no** se persiste el archivo de entrada en la aplicación (revisa logs y proxy en tu despliegue).

## Módulos de seguridad (aplicación)
Autenticación por API key (env + SQLite hasheado), rate limiting, admin con `ADMIN_SECRET`, generación opcional de claves con `POST ... generate=true`, cabeceras HTTP mínimas y `request_id` en errores — sin cambiar la lógica de inferencia.
"""

TAGS_METADATA = [
    {
        "name": "v1",
        "description": "Versión estable de la API. Prefijo `/v1`.",
    },
    {
        "name": "meta",
        "description": "Salud y métricas (sin autenticación).",
    },
    {
        "name": "admin",
        "description": "Gestión de claves en SQLite (solo si `ADMIN_SECRET` está definido). No usa API key de cliente.",
    },
]
