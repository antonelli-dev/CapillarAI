"""SQLite implementation of JobRepositoryPort."""
import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.domain.job import JobStatus, JobType, ShareLink, SimulationJob
from app.ports.job_repository import JobRepositoryPort

logger = logging.getLogger(__name__)


class SQLiteJobRepository(JobRepositoryPort):
    """
    SQLite-based job repository with GDPR-compliant data handling.
    Stores job metadata; images stored in StoragePort (S3/MinIO).
    """
    
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    clinic_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    input_image_path TEXT,
                    donor_image_path TEXT,
                    parameters TEXT,  -- JSON
                    result_urls TEXT,  -- JSON
                    error_message TEXT,
                    webhook_url TEXT,
                    webhook_sent BOOLEAN DEFAULT 0,
                    webhook_response_status INTEGER,
                    retention_days INTEGER DEFAULT 30,
                    patient_consent_given BOOLEAN DEFAULT 0,
                    consent_timestamp TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS jobs_clinic_id_idx ON jobs (clinic_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status)")
            conn.execute("CREATE INDEX IF NOT EXISTS jobs_created_at_idx ON jobs (created_at)")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS share_links (
                    token TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    clinic_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    max_views INTEGER DEFAULT 10,
                    view_count INTEGER DEFAULT 0,
                    watermark_text TEXT,
                    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS share_links_expires_idx ON share_links (expires_at)")
    
    def create(self, job: SimulationJob) -> SimulationJob:
        """Persist new job."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, job_type, clinic_id, status, created_at,
                    input_image_path, donor_image_path, parameters,
                    webhook_url, retention_days, patient_consent_given, consent_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.job_type.value,
                    job.clinic_id,
                    job.status.value,
                    job.created_at or datetime.utcnow(),
                    job.input_image_path,
                    job.donor_image_path,
                    json.dumps(job.parameters),
                    job.webhook_url,
                    job.retention_days,
                    job.patient_consent_given,
                    job.consent_timestamp,
                )
            )
        return job
    
    def get_by_id(self, job_id: str) -> Optional[SimulationJob]:
        """Retrieve job by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,)
            ).fetchone()
            
            if row:
                return self._row_to_job(row)
            return None
    
    def get_by_clinic(
        self,
        clinic_id: str,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SimulationJob]:
        """List jobs for a clinic."""
        query = "SELECT * FROM jobs WHERE clinic_id = ?"
        params = [clinic_id]
        
        if status:
            query += " AND status = ?"
            params.append(status.value)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_job(row) for row in rows]
    
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> SimulationJob:
        """Update job status."""
        now = datetime.utcnow()
        
        with sqlite3.connect(self.db_path) as conn:
            if status == JobStatus.PROCESSING:
                conn.execute(
                    "UPDATE jobs SET status = ?, started_at = ? WHERE job_id = ?",
                    (status.value, now, job_id)
                )
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
                conn.execute(
                    "UPDATE jobs SET status = ?, completed_at = ?, error_message = ? WHERE job_id = ?",
                    (status.value, now, error_message, job_id)
                )
            else:
                conn.execute(
                    "UPDATE jobs SET status = ? WHERE job_id = ?",
                    (status.value, job_id)
                )
        
        return self.get_by_id(job_id)
    
    def update_results(
        self,
        job_id: str,
        result_urls: Dict[str, str],
    ) -> SimulationJob:
        """Update job with result URLs."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET result_urls = ? WHERE job_id = ?",
                (json.dumps(result_urls), job_id)
            )
        return self.get_by_id(job_id)
    
    def mark_webhook_sent(
        self,
        job_id: str,
        response_status: int,
    ) -> None:
        """Record webhook delivery."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET webhook_sent = 1, webhook_response_status = ? WHERE job_id = ?",
                (response_status, job_id)
            )
    
    def get_pending_jobs(self, limit: int = 10) -> List[SimulationJob]:
        """Get jobs waiting to be processed."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs 
                WHERE status = ? 
                ORDER BY created_at ASC 
                LIMIT ?
                """,
                (JobStatus.PENDING.value, limit)
            ).fetchall()
            return [self._row_to_job(row) for row in rows]
    
    def get_expired_jobs(self, limit: int = 100) -> List[SimulationJob]:
        """Get jobs past retention period (GDPR)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs 
                WHERE completed_at IS NOT NULL
                AND datetime(completed_at, '+' || retention_days || ' days') < datetime('now')
                AND status != ?
                LIMIT ?
                """,
                (JobStatus.CANCELLED.value, limit)
            ).fetchall()
            return [self._row_to_job(row) for row in rows]
    
    def delete(self, job_id: str) -> None:
        """Hard delete (GDPR erasure)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
    
    # Share links
    def create_share_link(self, link: ShareLink) -> ShareLink:
        """Create time-limited share token."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO share_links (
                    token, job_id, clinic_id, expires_at, max_views, watermark_text
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    link.token,
                    link.job_id,
                    link.clinic_id,
                    link.expires_at,
                    link.max_views,
                    link.watermark_text,
                )
            )
        return link
    
    def get_share_link(self, token: str) -> Optional[ShareLink]:
        """Validate and retrieve share link."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM share_links WHERE token = ?",
                (token,)
            ).fetchone()
            
            if row:
                return self._row_to_share_link(row)
            return None
    
    def increment_share_link_views(self, token: str) -> None:
        """Record view count for share link."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE share_links SET view_count = view_count + 1 WHERE token = ?",
                (token,)
            )
    
    def _row_to_job(self, row: sqlite3.Row) -> SimulationJob:
        """Convert DB row to domain object."""
        return SimulationJob(
            job_id=row["job_id"],
            job_type=JobType(row["job_type"]),
            clinic_id=row["clinic_id"],
            status=JobStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            input_image_path=row["input_image_path"],
            donor_image_path=row["donor_image_path"],
            parameters=json.loads(row["parameters"]) if row["parameters"] else {},
            result_urls=json.loads(row["result_urls"]) if row["result_urls"] else {},
            error_message=row["error_message"],
            webhook_url=row["webhook_url"],
            webhook_sent=bool(row["webhook_sent"]),
            webhook_response_status=row["webhook_response_status"],
            retention_days=row["retention_days"],
            patient_consent_given=bool(row["patient_consent_given"]),
            consent_timestamp=datetime.fromisoformat(row["consent_timestamp"]) if row["consent_timestamp"] else None,
        )
    
    def _row_to_share_link(self, row: sqlite3.Row) -> ShareLink:
        """Convert DB row to domain object."""
        return ShareLink(
            token=row["token"],
            job_id=row["job_id"],
            clinic_id=row["clinic_id"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
            max_views=row["max_views"],
            view_count=row["view_count"],
            watermark_text=row["watermark_text"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
        )
