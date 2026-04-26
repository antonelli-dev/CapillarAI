# CapillarAI

REST API for AI-powered hair transplant simulation. Accepts a frontal portrait photo and returns a realistic post-FUE result image, powered by Stable Diffusion inpainting with adaptive scalp detection.

## Features

- Automatic hair loss severity detection (mild / moderate / severe)
- Adaptive mask generation using MediaPipe face landmarks
- Profile-based inference presets (`launch`, `maximum_fill`, `identity_lock`)
- Portrait validation (lighting, framing, frontal pose)

## Stack

- **FastAPI** — REST API versionada (`/v1/upload`, `/v1/generate`), OpenAPI en `/docs`
- **Stable Diffusion 1.5 Inpainting** (`runwayml/stable-diffusion-inpainting`)
- **MediaPipe** — face mesh landmarks + portrait validation
- **PyTorch** — CUDA/CPU inference

## Quick start

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Integración, autenticación (`X-API-Key`), límites y CORS: **`docs/INTEGRATION.md`**. Despliegue y datos: **`docs/DEPLOYMENT.md`**.

Tests: `pip install -r requirements-dev.txt` y `pytest tests/`.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/upload` | Validate portrait photo |
| POST | `/v1/generate` | Generate hair transplant simulation (query opcional `seed`) |
| GET | `/health` | Health + queue depth |
| GET | `/metrics` | Métricas Prometheus |

Autenticación: cabecera `X-API-Key` o `Bearer` (variables `API_KEYS` y/o `API_KEYS_DB`). Ver `scripts/add_api_key.py` para claves hasheadas sin redeploy.

**Gestión de claves por API:** con `ADMIN_SECRET` + `API_KEYS_DB` → `POST /v1/admin/keys` con `{"generate":true}` genera una clave segura para el cliente (solo se muestra en esa respuesta); listar/revocar en `docs/INTEGRATION.md`. Cabeceras de seguridad básicas (`X-Content-Type-Options`, etc.) y `X-Request-ID` en respuestas.

## Profiles

Edit `ACTIVE_PROFILE` in `app/product_profiles.py`:

| Profile | Use case |
|---------|----------|
| `launch` | Default — best balance |
| `maximum_fill` | Severe baldness, maximum coverage |
| `identity_lock` | Prioritise face identity (IP-Adapter) |

## License

Proprietary — all rights reserved.
