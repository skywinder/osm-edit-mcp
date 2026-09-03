"""Durable, idempotent proposal storage for OSM edits.

The store is deliberately small and synchronous. Proposal transitions are tiny
SQLite transactions, so they can safely coordinate multiple local MCP
processes without introducing another service.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

TERMINAL_STATUSES = {
    "APPLIED",
    "FAILED",
    "STALE",
    "EXPIRED",
    "RECONCILE_REQUIRED",
}


def canonical_digest(
    payload: Dict[str, Any], api_target: str, osm_uid: Optional[int]
) -> str:
    """Hash exactly what can be written, excluding derived presentation fields."""
    write_payload = {
        key: value for key, value in payload.items() if not key.startswith("_")
    }
    document = {
        "api_target": api_target.rstrip("/"),
        "osm_uid": osm_uid,
        "payload": write_payload,
    }
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class StoredProposal:
    proposal_id: str
    created_at: float
    expires_at: float
    status: str
    api_target: str
    osm_uid: Optional[int]
    digest: str
    payload: Dict[str, Any]
    receipt: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    changeset_id: Optional[int] = None


class ProposalStoreError(RuntimeError):
    """A proposal could not make the requested state transition."""


class ProposalStore:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()
        self._init_lock = threading.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.parent.stat().st_uid == os.getuid():
            os.chmod(self.path.parent, 0o700)
        if self.path.is_symlink():
            raise ProposalStoreError("Proposal database path must not be a symlink")
        connection = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        os.chmod(self.path, 0o600)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        self._initialize(connection)
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self, connection: sqlite3.Connection) -> None:
        if self._initialized:
            return
        with self._init_lock:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    api_target TEXT NOT NULL,
                    osm_uid INTEGER,
                    digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    receipt_json TEXT,
                    error TEXT,
                    changeset_id INTEGER,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS proposals_status_idx "
                "ON proposals(status, expires_at)"
            )
            self._initialized = True

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredProposal:
        return StoredProposal(
            proposal_id=row["proposal_id"],
            created_at=float(row["created_at"]),
            expires_at=float(row["expires_at"]),
            status=row["status"],
            api_target=row["api_target"],
            osm_uid=int(row["osm_uid"]) if row["osm_uid"] is not None else None,
            digest=row["digest"],
            payload=json.loads(row["payload_json"]),
            receipt=(
                json.loads(row["receipt_json"])
                if row["receipt_json"] is not None
                else None
            ),
            error=row["error"],
            changeset_id=(
                int(row["changeset_id"]) if row["changeset_id"] is not None else None
            ),
        )

    def create(
        self,
        proposal_id: str,
        payload: Dict[str, Any],
        api_target: str,
        osm_uid: Optional[int],
        ttl_seconds: int,
    ) -> StoredProposal:
        now = time.time()
        expires = now + ttl_seconds
        digest = canonical_digest(payload, api_target, osm_uid)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO proposals (
                    proposal_id, created_at, expires_at, status, api_target,
                    osm_uid, digest, payload_json, updated_at
                ) VALUES (?, ?, ?, 'PREVIEWED', ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    now,
                    expires,
                    api_target.rstrip("/"),
                    osm_uid,
                    digest,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
        proposal = self.get(proposal_id, include_expired=True)
        assert proposal is not None
        return proposal

    def get(
        self, proposal_id: str, *, include_expired: bool = False
    ) -> Optional[StoredProposal]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            if row is None:
                return None
            proposal = self._from_row(row)
            if (
                proposal.expires_at <= time.time()
                and proposal.status not in TERMINAL_STATUSES
            ):
                connection.execute(
                    "UPDATE proposals SET status='EXPIRED', updated_at=? "
                    "WHERE proposal_id=?",
                    (time.time(), proposal_id),
                )
                proposal = StoredProposal(**{**proposal.__dict__, "status": "EXPIRED"})
            if proposal.status == "EXPIRED" and not include_expired:
                return None
            return proposal

    def update_payload(self, proposal_id: str, payload: Dict[str, Any]) -> None:
        """Persist derived review fields without changing the write digest."""
        with self._connection() as connection:
            connection.execute(
                "UPDATE proposals SET payload_json=?, updated_at=? WHERE proposal_id=?",
                (
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    time.time(),
                    proposal_id,
                ),
            )

    def replace_preview_payload(
        self,
        proposal_id: str,
        payload: Dict[str, Any],
        api_target: str,
        osm_uid: Optional[int],
    ) -> str:
        """Replace a not-yet-approved preview and return its new digest."""
        digest = canonical_digest(payload, api_target, osm_uid)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE proposals
                SET payload_json=?, digest=?, updated_at=?
                WHERE proposal_id=? AND status='PREVIEWED'
                """,
                (
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    digest,
                    time.time(),
                    proposal_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ProposalStoreError("Only a previewed proposal can be replaced")
        return digest

    def expire(self, proposal_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE proposals SET status='EXPIRED', updated_at=? "
                "WHERE proposal_id=? AND status IN ('PREVIEWED','AWAITING_APPROVAL')",
                (time.time(), proposal_id),
            )

    def mark_awaiting_approval(self, proposal_id: str) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE proposals SET status='AWAITING_APPROVAL', updated_at=? "
                "WHERE proposal_id=? AND status='PREVIEWED'",
                (time.time(), proposal_id),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT status FROM proposals WHERE proposal_id=?",
                    (proposal_id,),
                ).fetchone()
                if row is None or row["status"] != "AWAITING_APPROVAL":
                    raise ProposalStoreError(
                        "Only a previewed proposal can await approval"
                    )

    def claim(
        self,
        proposal_id: str,
        digest: str,
        api_target: str,
        osm_uid: int,
    ) -> StoredProposal:
        """Atomically reserve a proposal for exactly one uploader."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
            if row is None:
                raise ProposalStoreError("Unknown proposal")
            proposal = self._from_row(row)
            if proposal.status == "APPLIED":
                connection.execute("COMMIT")
                return proposal
            if proposal.expires_at <= time.time():
                connection.execute(
                    "UPDATE proposals SET status='EXPIRED', updated_at=? "
                    "WHERE proposal_id=?",
                    (time.time(), proposal_id),
                )
                connection.execute("COMMIT")
                raise ProposalStoreError("Proposal expired")
            if proposal.status not in {"PREVIEWED", "AWAITING_APPROVAL"}:
                raise ProposalStoreError(f"Proposal is {proposal.status.lower()}")
            if proposal.digest != digest:
                raise ProposalStoreError("Proposal digest mismatch")
            if proposal.api_target.rstrip("/") != api_target.rstrip("/"):
                raise ProposalStoreError("Proposal belongs to a different API target")
            if proposal.osm_uid is not None and proposal.osm_uid != osm_uid:
                raise ProposalStoreError("Proposal belongs to a different OSM account")
            connection.execute(
                """
                UPDATE proposals
                SET status='APPLYING', osm_uid=COALESCE(osm_uid, ?), updated_at=?
                WHERE proposal_id=? AND status IN ('PREVIEWED','AWAITING_APPROVAL')
                """,
                (osm_uid, time.time(), proposal_id),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        claimed = self.get(proposal_id, include_expired=True)
        assert claimed is not None
        return claimed

    def set_changeset_id(self, proposal_id: str, changeset_id: int) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE proposals SET changeset_id=?, updated_at=? WHERE proposal_id=?",
                (changeset_id, time.time(), proposal_id),
            )

    def finish(
        self,
        proposal_id: str,
        status: str,
        *,
        receipt: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        if status not in {"APPLIED", "FAILED", "STALE", "RECONCILE_REQUIRED"}:
            raise ValueError(f"Unsupported proposal terminal status: {status}")
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE proposals
                SET status=?, receipt_json=?, error=?, updated_at=?
                WHERE proposal_id=? AND status='APPLYING'
                """,
                (
                    status,
                    json.dumps(receipt, ensure_ascii=False) if receipt else None,
                    error,
                    time.time(),
                    proposal_id,
                ),
            )

    def list(
        self, status: Optional[str] = None, limit: int = 50
    ) -> List[StoredProposal]:
        query = "SELECT * FROM proposals"
        parameters: List[Any] = []
        if status:
            query += " WHERE status=?"
            parameters.append(status.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(max(1, min(limit, 200)))
        with self._connection() as connection:
            return [
                self._from_row(row)
                for row in connection.execute(query, parameters).fetchall()
            ]


__all__ = [
    "ProposalStore",
    "ProposalStoreError",
    "StoredProposal",
    "canonical_digest",
]
