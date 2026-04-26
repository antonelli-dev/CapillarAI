# Integración API CapillarAI

Base URL: `https://tu-servidor` (sin barra final).

## Autenticación

Todas las rutas bajo `/v1` requieren:

- Cabecera `X-API-Key: <clave>` **o**
- `Authorization: Bearer <clave>`

Sin claves configuradas (`API_KEYS` y `API_KEYS_DB` vacíos), el servidor acepta peticiones sin autenticación (**solo desarrollo**).

## Validar foto (`POST /v1/upload`)

Comprueba encuadre, luz y pose antes de gastar inferencia en `/v1/generate`.

```bash
curl -sS -X POST "https://tu-servidor/v1/upload" \
  -H "X-API-Key: TU_CLAVE" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@foto.jpg"
```

Respuesta OK: `{"message":"Imagen válida","valid":true}`.

Errores frecuentes:

| Código | Significado        |
|--------|--------------------|
| 400    | Validación facial  |
| 401    | API key inválida   |
| 413    | Imagen > 10 MB     |
| 429    | Demasiadas peticiones (rate limit) |

## Generar simulación (`POST /v1/generate`)

Devuelve un **PNG**.

```bash
curl -sS -X POST "https://tu-servidor/v1/generate?seed=42" \
  -H "X-API-Key: TU_CLAVE" \
  -F "file=@foto.jpg" \
  -o resultado.png
```

- `seed` (opcional): entero para acercar resultados entre ejecuciones (mismo modelo y versión).
- **503**: cola GPU llena — reintentar más tarde.
- **504**: tiempo de inferencia agotado — reintentar.

## Límites

- **Tamaño**: 10 MB por imagen.
- **Rate limit**: por defecto `RATE_LIMIT_UPLOAD` y `RATE_LIMIT_GENERATE` (p. ej. `60/minute` y `12/minute`). Respuesta **429** si se excede.

## CORS (navegador)

Define `CORS_ORIGINS` con los orígenes permitidos separados por comas. En producción no dejes el valor vacío si el front es otro dominio.

## Salud y métricas

- `GET /health` — estado y profundidad de cola (sin autenticación).
- `GET /metrics` — Prometheus (sin autenticación).

## OpenAPI

- `GET /docs` — Swagger UI.
- `GET /redoc` — ReDoc.

## Admin — gestión de claves (opcional)

Si defines **`ADMIN_SECRET`** en el servidor, quedan disponibles (sin API key de cliente, solo secreto admin):

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/v1/admin/keys` | Listar claves (`key_hash_preview`, `id`). Query `active_only=false` para ver revocadas. |
| POST | `/v1/admin/keys` | **Crear clave para cliente:** `{"generate": true, "label": "Clínica X"}` → respuesta incluye **`api_key`** una sola vez. O `{"plain_key":"tu_clave","label":"..."}` si tú generas la clave fuera. |
| DELETE | `/v1/admin/keys/{id}` | Revocar por `id` (rowid de la lista) |

Cabecera: **`X-Admin-Secret: <tu_ADMIN_SECRET>`** (o `Authorization: Bearer ...`).

En producción usa **HTTPS**; el secreto admin es tan sensible como la raíz del sistema.

## Cabeceras de seguridad HTTP

La app añade (entre otras) `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` y `Cache-Control: no-store` en rutas `/v1/*`, `/docs`, etc. Detrás de HTTPS puedes activar **HSTS** con la variable de entorno:

- **`SECURE_HSTS_MAX_AGE`**: segundos para `Strict-Transport-Security` (p. ej. `31536000` = un año). Solo se envía si la petición se considera HTTPS (URL `https:` o cabecera `X-Forwarded-Proto: https` típica tras un proxy). En desarrollo local HTTP déjala vacía. Por defecto el header es solo `max-age=…` (host actual).
- **`SECURE_HSTS_INCLUDE_SUBDOMAINS`**: `1` / `true` para añadir `includeSubDomains` (solo si todo el dominio va en HTTPS).
- **`SECURE_HSTS_PRELOAD`**: `1` / `true` para añadir `preload` (solo si vas a registrar el dominio en la lista de preload; para una API casi nunca hace falta).

## Depuración

Todas las respuestas llevan **`X-Request-ID`**. Los errores JSON incluyen **`request_id`** para cruzar con logs (`capillarai.access`).
