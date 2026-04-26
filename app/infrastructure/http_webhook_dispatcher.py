"""HTTP-based implementation of WebhookDispatcherPort."""
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

import requests

from app.domain.job import SimulationJob
from app.ports.webhook_dispatcher import WebhookDispatcherPort

logger = logging.getLogger(__name__)


class HTTPWebhookDispatcher(WebhookDispatcherPort):
    """
    HTTP webhook dispatcher with HMAC signature verification.
    Sends JSON POST requests to clinic callback URLs.
    """
    
    def __init__(
        self,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        secret_prefix: str = "whsec_",
    ):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.secret_prefix = secret_prefix
    
    def send_job_completed(
        self,
        webhook_url: str,
        job: SimulationJob,
        retry_count: int = 3,
    ) -> int:
        """
        Notify clinic that job is complete.
        
        Returns:
            HTTP status code from webhook response
        """
        payload = {
            "event": "job.completed",
            "job": job.to_public_dict(),
        }
        
        return self._send_with_retry(webhook_url, payload, retry_count)
    
    def send_batch_completed(
        self,
        webhook_url: str,
        job_ids: list[str],
        summary: Dict[str, Any],
    ) -> int:
        """Notify clinic that batch processing is complete."""
        payload = {
            "event": "batch.completed",
            "job_ids": job_ids,
            "summary": summary,
        }
        
        return self._send_with_retry(webhook_url, payload, self.max_retries)
    
    def _send_with_retry(
        self,
        webhook_url: str,
        payload: Dict[str, Any],
        retries: int,
    ) -> int:
        """Send webhook with exponential backoff retry."""
        import time
        
        payload_json = json.dumps(payload, default=str, separators=(',', ':'))
        
        for attempt in range(retries):
            try:
                # Sign payload if we have a secret for this URL
                # In real implementation, you'd look up the secret from config/DB
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "CapillarAI-Webhook/1.0",
                    "X-Webhook-Event": payload["event"],
                }
                
                response = requests.post(
                    webhook_url,
                    data=payload_json,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                
                status = response.status_code
                
                if 200 <= status < 300:
                    logger.info(f"Webhook delivered to {webhook_url}: {status}")
                    return status
                elif status in (429, 500, 502, 503, 504):
                    # Retry on rate limit or server errors
                    logger.warning(f"Webhook retry {attempt+1}/{retries}: {status}")
                    if attempt < retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    # Client error, don't retry
                    logger.error(f"Webhook failed: {status} - {response.text[:200]}")
                    return status
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Webhook timeout to {webhook_url}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error(f"Webhook error to {webhook_url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        
        # All retries exhausted
        logger.error(f"Webhook failed after {retries} attempts: {webhook_url}")
        return 0  # Indicate failure
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """
        Verify webhook signature using HMAC-SHA256.
        
        Expected signature format: "t=<timestamp>,v1=<hex_signature>"
        """
        try:
            # Parse signature header
            parts = {}
            for part in signature.split(','):
                if '=' in part:
                    key, value = part.split('=', 1)
                    parts[key.strip()] = value.strip()
            
            timestamp = parts.get('t')
            sig_value = parts.get('v1')
            
            if not timestamp or not sig_value:
                return False
            
            # Reconstruct signed payload
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            
            # Compute expected signature
            expected_sig = hmac.new(
                secret.encode('utf-8'),
                signed_payload.encode('utf-8'),
                hashlib.sha256,
            ).hexdigest()
            
            # Constant-time comparison
            return hmac.compare_digest(sig_value, expected_sig)
            
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    def generate_signature(self, payload: bytes, secret: str) -> str:
        """Generate webhook signature for testing."""
        import time
        
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
        
        signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        
        return f"t={timestamp},v1={signature}"
