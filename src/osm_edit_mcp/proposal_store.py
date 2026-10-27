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
    "SUPERSEDED",
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
            connection.execute("""
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
                """)
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
            if proposal.expires_at <= time.time() and proposal.status in {
                "PREVIEWED",
                "AWAITING_APPROVAL",
            }:
                connection.execute(
                    "UPDATE proposals SET status='EXPIRED', updated_at=? "
                    "WHERE proposal_id=? "
                    "AND status IN ('PREVIEWED','AWAITING_APPROVAL')",
                    (time.time(), proposal_id),
                )
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
                ).fetchone()
                assert row is not None
                proposal = self._from_row(row)
            if proposal.status == "EXPIRED" and not include_expired:
                return None
            return proposal

    def update_payload(self, proposal_id: str, payload: Dict[str, Any]) -> None:
        """Persist derived fields only while the exact preview is unapproved."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
                ).fetchone()
                if row is None:
                    raise ProposalStoreError("Unknown proposal")
                proposal = self._from_row(row)
                if proposal.status != "PREVIEWED":
                    raise ProposalStoreError("Only a previewed proposal can be updated")
                if (
                    canonical_digest(payload, proposal.api_target, proposal.osm_uid)
                    != proposal.digest
                ):
                    raise ProposalStoreError(
                        "Derived payload update cannot change the proposal digest"
                    )
                connection.execute(
                    "UPDATE proposals SET payload_json=?, updated_at=? "
                    "WHERE proposal_id=? AND status='PREVIEWED'",
                    (
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        time.time(),
                        proposal_id,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

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

    def supersede_preview(
        self,
        proposal_id: str,
        expected_digest: str,
        new_proposal_id: str,
        payload: Dict[str, Any],
        api_target: str,
        osm_uid: int,
        ttl_seconds: int,
    ) -> StoredProposal:
        """Atomically create a revision and retire its exact unclaimed parent.

        Competes with upload claims and other reviews in the same transaction.
        A confirmation already in flight cannot authorize the new revision.
        """
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
                ).fetchone()
                if row is None:
                    raise ProposalStoreError("Unknown proposal")
                parent = self._from_row(row)
                now = time.time()
                if parent.status not in {"PREVIEWED", "AWAITING_APPROVAL"}:
                    raise ProposalStoreError(f"Proposal is {parent.status.lower()}")
                if parent.expires_at <= now:
                    raise ProposalStoreError("Proposal expired")
                if (
                    parent.digest != expected_digest
                    or canonical_digest(
                        parent.payload, parent.api_target, parent.osm_uid
                    )
                    != expected_digest
                ):
                    raise ProposalStoreError("Proposal digest mismatch")
                if (
                    parent.api_target != api_target.rstrip("/")
                    or parent.osm_uid != osm_uid
                ):
                    raise ProposalStoreError(
                        "Proposal API target or OSM account changed"
                    )
                connection.execute(
                    """INSERT INTO proposals (
                        proposal_id, created_at, expires_at, status, api_target,
                        osm_uid, digest, payload_json, updated_at
                    ) VALUES (?, ?, ?, 'PREVIEWED', ?, ?, ?, ?, ?)""",
                    (
                        new_proposal_id,
                        now,
                        now + ttl_seconds,
                        parent.api_target,
                        osm_uid,
                        canonical_digest(payload, parent.api_target, osm_uid),
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        now,
                    ),
                )
                parent.payload["_superseded_by"] = new_proposal_id
                connection.execute(
                    "UPDATE proposals SET status='SUPERSEDED', payload_json=?, updated_at=? "
                    "WHERE proposal_id=?",
                    (json.dumps(parent.payload, ensure_ascii=False), now, proposal_id),
                )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        revision = self.get(new_proposal_id, include_expired=True)
        assert revision is not None
        return revision

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
            if (
                proposal.digest != digest
                or canonical_digest(
                    proposal.payload, proposal.api_target, proposal.osm_uid
                )
                != proposal.digest
            ):
                raise ProposalStoreError("Proposal digest mismatch")
            if proposal.api_target.rstrip("/") != api_target.rstrip("/"):
                raise ProposalStoreError("Proposal belongs to a different API target")
            if proposal.osm_uid is not None and proposal.osm_uid != osm_uid:
                raise ProposalStoreError("Proposal belongs to a different OSM account")
            if proposal.status == "APPLIED":
                connection.execute("COMMIT")
                return proposal
            if proposal.status not in {"PREVIEWED", "AWAITING_APPROVAL"}:
                raise ProposalStoreError(f"Proposal is {proposal.status.lower()}")
            if proposal.expires_at <= time.time():
                connection.execute(
                    "UPDATE proposals SET status='EXPIRED', updated_at=? "
                    "WHERE proposal_id=?",
                    (time.time(), proposal_id),
                )
                connection.execute("COMMIT")
                raise ProposalStoreError("Proposal expired")
            connection.execute(
                """
                UPDATE proposals
                SET status='APPLYING', updated_at=?
                WHERE proposal_id=? AND status IN ('PREVIEWED','AWAITING_APPROVAL')
                """,
                (time.time(), proposal_id),
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

    def record_reconciliation(
        self,
        proposal_id: str,
        digest: str,
        api_target: str,
        osm_uid: int,
        receipt: Dict[str, Any],
    ) -> StoredProposal:
        """Resolve an uncertain upload without claiming or repeating its write."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
                ).fetchone()
                if row is None:
                    raise ProposalStoreError("Unknown proposal")
                proposal = self._from_row(row)
                if (
                    proposal.digest != digest
                    or canonical_digest(
                        proposal.payload, proposal.api_target, proposal.osm_uid
                    )
                    != proposal.digest
                ):
                    raise ProposalStoreError("Proposal digest mismatch")
                if proposal.api_target.rstrip("/") != api_target.rstrip("/"):
                    raise ProposalStoreError(
                        "Proposal belongs to a different API target"
                    )
                if proposal.osm_uid is not None and proposal.osm_uid != osm_uid:
                    raise ProposalStoreError(
                        "Proposal belongs to a different OSM account"
                    )
                receipt_changeset = receipt.get("changeset_id")
                if (
                    type(receipt_changeset) is not int
                    or receipt_changeset <= 0
                    or receipt_changeset != proposal.changeset_id
                ):
                    raise ProposalStoreError(
                        "Reconciliation receipt belongs to a different changeset"
                    )
                if proposal.status == "APPLIED":
                    connection.execute("COMMIT")
                    return proposal
                if proposal.status != "RECONCILE_REQUIRED":
                    raise ProposalStoreError(
                        "Only a proposal requiring reconciliation can be resolved"
                    )
                cursor = connection.execute(
                    """
                    UPDATE proposals
                    SET status='APPLIED', receipt_json=?, error=NULL, updated_at=?
                    WHERE proposal_id=? AND status='RECONCILE_REQUIRED'
                    """,
                    (json.dumps(receipt, ensure_ascii=False), time.time(), proposal_id),
                )
                if cursor.rowcount != 1:
                    raise ProposalStoreError("Proposal reconciliation state changed")
                row = connection.execute(
                    "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
                ).fetchone()
                assert row is not None
                resolved = self._from_row(row)
                connection.execute("COMMIT")
                return resolved
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

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
