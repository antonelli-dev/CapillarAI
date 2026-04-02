# CapillarAI

REST API for AI-powered hair transplant simulation. Accepts a frontal portrait photo and returns a realistic post-FUE result image, powered by Stable Diffusion inpainting with adaptive scalp detection.

## Features

- Automatic hair loss severity detection (mild / moderate / severe)
- Adaptive mask generation using MediaPipe face landmarks
- Profile-based inference presets (`launch`, `maximum_fill`, `identity_lock`)
- Portrait validation (blur, lighting, framing, frontal pose)

## Stack

- **FastAPI** — REST endpoints (`/upload`, `/generate`)
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

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Validate portrait photo |
| POST | `/generate` | Generate hair transplant simulation |

## Profiles

Edit `ACTIVE_PROFILE` in `app/product_profiles.py`:

| Profile | Use case |
|---------|----------|
| `launch` | Default — best balance |
| `maximum_fill` | Severe baldness, maximum coverage |
| `identity_lock` | Prioritise face identity (IP-Adapter) |

## License

Proprietary — all rights reserved.
