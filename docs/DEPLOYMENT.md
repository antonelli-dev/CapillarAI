# Despliegue y datos

## Imágenes

La aplicación **no escribe** las fotos de entrada en base de datos ni en rutas de archivo por defecto: se decodifican en memoria, se procesan y la respuesta de `/v1/generate` es un flujo PNG.

**Revisa en tu entorno:**

- Que el **reverse proxy** (nginx, Caddy, etc.) no guarde cuerpos de petición en logs de acceso con nivel debug.
- Política de **retención de logs** del proveedor cloud.
- Que no montéis volúmenes que persistan cachés de imágenes sin querer.

## Variables relevantes

| Variable | Descripción |
|----------|-------------|
| `API_KEYS` | Claves en texto, separadas por comas (útil en dev). |
| `API_KEYS_DB` | Ruta a SQLite con claves hasheadas (`scripts/add_api_key.py`). |
| `CORS_ORIGINS` | Orígenes permitidos para el navegador. |
| `ENVIRONMENT` | `development` o `production` (aviso si CORS vacío en prod). |
| `RATE_LIMIT_UPLOAD` / `RATE_LIMIT_GENERATE` | Formato slowapi, p. ej. `60/minute`. |
| `ADMIN_SECRET` | Activa `/v1/admin/keys` para gestionar claves SQLite sin redeploy. |

## Alertas

El código expone **métricas Prometheus** en `/metrics`. Puedes enlazar Grafana/Prometheus o un chequeo HTTP externo (p. ej. `/health`) para avisar si el servicio cae o responde `busy` de forma prolongada.
