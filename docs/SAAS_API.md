# CapillarAI SaaS API Documentation

## Overview

New SaaS features for hair transplant clinics:
- **Async Job Queue** - Background processing with webhooks
- **Donor Area Analysis** - CPU-only viability assessment
- **Hairline Presets** - Clinic-specific configurations
- **Shareable Links** - Patient result sharing
- **GDPR Compliance** - Data export, deletion, consent

## Base URL

```
http://localhost:8002/v1
```

## Authentication

All endpoints require API key (except public share links):
```
X-API-Key: your-api-key
```

---

## 1. Async Jobs

### Create Async Job
**POST** `/jobs`

Submit photo for background processing. Returns job ID immediately.

**Request:**
```bash
curl -X POST http://localhost:8002/v1/jobs \
  -H "X-API-Key: your-key" \
  -F "front_image=@photo.jpg" \
  -F "donor_image=@donor.jpg" \
  -F "webhook_url=https://your-clinic.com/webhook" \
  -F "patient_reference=PAT-001" \
  -F "consent_given=true"
```

**Response (202):**
```json
{
  "job_id": "uuid",
  "status": "pending",
  "created_at": "2026-04-26T13:39:33Z"
}
```

### Get Job Status
**GET** `/jobs/{job_id}`

```bash
curl http://localhost:8002/v1/jobs/{job_id} \
  -H "X-API-Key: your-key"
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "result_urls": {
    "simulation": "/storage/...",
    "pdf_report": "/storage/..."
  }
}
```

### Batch Upload
**POST** `/jobs/batch`

Upload up to 10 images at once.

```bash
curl -X POST http://localhost:8002/v1/jobs/batch \
  -H "X-API-Key: your-key" \
  -F "images=@photo1.jpg" \
  -F "images=@photo2.jpg"
```

---

## 2. Donor Area Analysis

### Analyze Donor Area
**POST** `/donor-analysis`

CPU-only analysis. No GPU required.

**Request:**
```bash
curl -X POST http://localhost:8002/v1/donor-analysis \
  -H "X-API-Key: your-key" \
  -F "donor_image=@donor_area.jpg" \
  -F "recipient_area_cm2=80"
```

**Response (200):**
```json
{
  "density_score": 7.5,
  "estimated_grafts": 2500,
  "coverage_area_cm2": 100.0,
  "hair_caliber_mm": 0.08,
  "recommendation": "Recommended",
  "confidence": 0.85,
  "reasoning": "Donor area adequate...",
  "match_score": 0.95
}
```

---

## 3. Hairline Presets

### List Presets
**GET** `/presets`

```bash
curl http://localhost:8002/v1/presets \
  -H "X-API-Key: your-key"
```

### Create Preset
**POST** `/presets`

```bash
curl -X POST http://localhost:8002/v1/presets \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Conservative Natural",
    "hairline_type": "conservative",
    "parameters": {
      "height_mm": 8,
      "density": 0.75,
      "curve_style": "natural"
    }
  }'
```

### Get Preset
**GET** `/presets/{preset_id}`

### Update Preset
**PUT** `/presets/{preset_id}`

### Delete Preset
**DELETE** `/presets/{preset_id}`

---

## 4. Share Links

### Create Share Link
**POST** `/share/{job_id}`

```bash
curl -X POST http://localhost:8002/v1/share/{job_id} \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "expires_in_days": 30,
    "max_views": 5,
    "watermark_text": "Clinic Name"
  }'
```

**Response:**
```json
{
  "share_url": "http://localhost:8002/p/abc123",
  "expires_at": "2026-05-26T13:39:33Z"
}
```

### Access Shared Result
**GET** `/p/{token}` (Public - No Auth)

```bash
curl http://localhost:8002/p/abc123
```

---

## 5. GDPR Compliance

### Record Consent
**POST** `/gdpr/consent`

```bash
curl -X POST http://localhost:8002/v1/gdpr/consent \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_reference": "PAT-001",
    "purpose": ["simulation", "storage"],
    "consent_given": true
  }'
```

### Export Patient Data
**POST** `/gdpr/export`

Returns ZIP with all patient data.

```bash
curl -X POST http://localhost:8002/v1/gdpr/export \
  -H "X-API-Key: your-key" \
  -d '{"patient_reference": "PAT-001"}' \
  --output patient-data.zip
```

### Request Data Deletion
**POST** `/gdpr/delete`

```bash
curl -X POST http://localhost:8002/v1/gdpr/delete \
  -H "X-API-Key: your-key" \
  -d '{
    "patient_reference": "PAT-001",
    "reason": "patient_request"
  }'
```

---

## Webhook Format

When async job completes, webhook is sent:

```json
{
  "event": "job.completed",
  "job_id": "uuid",
  "status": "completed",
  "result_urls": {
    "simulation": "https://...",
    "pdf_report": "https://..."
  },
  "timestamp": "2026-04-26T13:39:33Z",
  "signature": "sha256=..."
}
```

**Verify signature:**
```python
import hmac
import hashlib

expected = hmac.new(
    webhook_secret.encode(),
    request_body,
    hashlib.sha256
).hexdigest()

if f"sha256={expected}" == signature_header:
    # Valid webhook
```

---

## Error Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 202 | Accepted (async) |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Server Error |

---

## Rate Limits

- Upload: 10/minute
- Generate: 2/minute
- Donor Analysis: 60/minute
- Presets: 120/minute

---

## Testing

Run test suite:
```bash
python test_saas_api.py
```

Expected output:
```
Health               [PASS]
Donor Analysis       [PASS]
Presets              [PASS]
GDPR                 [PASS]
Async Jobs           [PASS]
------------------------
Total: 5/5 passed
```
