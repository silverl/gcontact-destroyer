from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from gcontact_destroyer.models import Contact, Status


class ContactsDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    resource_name TEXT PRIMARY KEY,
                    display_name TEXT DEFAULT '',
                    first_name TEXT DEFAULT '',
                    last_name TEXT DEFAULT '',
                    emails TEXT DEFAULT '[]',
                    phones TEXT DEFAULT '[]',
                    organizations TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'unmarked',
                    etag TEXT DEFAULT '',
                    raw_json TEXT DEFAULT '{}',
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def upsert_contacts(self, contacts: list[Contact]) -> None:
        with self._connect() as conn:
            for contact in contacts:
                row = contact.to_db_row()
                conn.execute(
                    """INSERT INTO contacts
                       (resource_name, display_name, first_name, last_name,
                        emails, phones, organizations, status, etag, raw_json)
                       VALUES (:resource_name, :display_name, :first_name, :last_name,
                               :emails, :phones, :organizations, :status, :etag, :raw_json)
                       ON CONFLICT(resource_name) DO UPDATE SET
                           display_name=excluded.display_name,
                           first_name=excluded.first_name,
                           last_name=excluded.last_name,
                           emails=excluded.emails,
                           phones=excluded.phones,
                           organizations=excluded.organizations,
                           status = CASE
                               WHEN contacts.status IN ('trashed', 'protected')
                                   THEN contacts.status
                               ELSE excluded.status
                           END,
                           etag=excluded.etag,
                           raw_json=excluded.raw_json,
                           synced_at=CURRENT_TIMESTAMP
                    """,
                    row,
                )

    def get_contacts(
        self,
        exclude_protected: bool = False,
        status: Status | None = None,
    ) -> list[Contact]:
        query = "SELECT * FROM contacts"
        params: list[str] = []
        conditions: list[str] = []

        if exclude_protected:
            conditions.append("status != ?")
            params.append(Status.PROTECTED.value)
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY display_name"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Contact.from_db_row(dict(r)) for r in rows]

    def get_contact(self, resource_name: str) -> Contact | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contacts WHERE resource_name = ?",
                (resource_name,),
            ).fetchone()
            if row is None:
                return None
            return Contact.from_db_row(dict(row))

    def set_status(self, resource_name: str, status: Status) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE contacts SET status = ? WHERE resource_name = ?",
                (status.value, resource_name),
            )

    def search(self, query: str, exclude_protected: bool = True) -> list[Contact]:
        pattern = f"%{query}%"
        sql = """
            SELECT * FROM contacts
            WHERE (display_name LIKE ? OR emails LIKE ? OR phones LIKE ? OR organizations LIKE ?)
        """
        params: list[str] = [pattern, pattern, pattern, pattern]

        if exclude_protected:
            sql += " AND status != ?"
            params.append(Status.PROTECTED.value)

        sql += " ORDER BY display_name"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [Contact.from_db_row(dict(r)) for r in rows]

    def delete_contacts(self, resource_names: list[str]) -> None:
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in resource_names)
            conn.execute(
                f"DELETE FROM contacts WHERE resource_name IN ({placeholders})",
                resource_names,
            )

    def get_domain_counts(self) -> dict[str, int]:
        contacts = self.get_contacts(status=Status.UNMARKED)
        counter: Counter[str] = Counter()
        for c in contacts:
            domain = c.email_domain
            key = domain if domain else "(no email)"
            counter[key] += 1
        return dict(counter.most_common())

    def get_contacts_by_domain(self, domain: str) -> list[Contact]:
        pattern = f"%@{domain}%"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE emails LIKE ? AND status = ? ORDER BY display_name",
                (pattern, Status.UNMARKED.value),
            ).fetchall()
            return [Contact.from_db_row(dict(r)) for r in rows]

    def get_sparse_counts(self) -> dict[str, int]:
        contacts = self.get_contacts(status=Status.UNMARKED)
        counter: Counter[str] = Counter()
        for c in contacts:
            label = c.completeness_label
            if label != "Complete":
                counter[label] += 1
        return dict(counter.most_common())

    def get_contacts_by_completeness(self, label: str) -> list[Contact]:
        contacts = self.get_contacts(status=Status.UNMARKED)
        return [c for c in contacts if c.completeness_label == label]

    def get_label_counts(self) -> dict[str, int]:
        contacts = self.get_contacts(status=Status.UNMARKED)
        counter: Counter[str] = Counter()
        for c in contacts:
            raw = c.raw_json
            if isinstance(raw, str):
                raw = json.loads(raw)
            for m in raw.get("memberships", []):
                cgm = m.get("contactGroupMembership", {})
                group_name = cgm.get("contactGroupResourceName", "")
                if group_name and group_name not in (
                    "contactGroups/myContacts",
                    "contactGroups/starred",
                ):
                    counter[group_name] += 1
        return dict(counter.most_common())

    def get_contacts_by_label(self, group_resource_name: str) -> list[Contact]:
        contacts = self.get_contacts(status=Status.UNMARKED)
        result = []
        for c in contacts:
            raw = c.raw_json
            if isinstance(raw, str):
                raw = json.loads(raw)
            for m in raw.get("memberships", []):
                cgm = m.get("contactGroupMembership", {})
                if cgm.get("contactGroupResourceName") == group_resource_name:
                    result.append(c)
                    break
        return result

    def get_stats(self) -> dict[str, int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
            protected = conn.execute(
                "SELECT COUNT(*) FROM contacts WHERE status = ?",
                (Status.PROTECTED.value,),
            ).fetchone()[0]
            trashed = conn.execute(
                "SELECT COUNT(*) FROM contacts WHERE status = ?",
                (Status.TRASHED.value,),
            ).fetchone()[0]
            return {
                "total": total,
                "protected": protected,
                "trashed": trashed,
                "remaining": total - protected - trashed,
            }

    def save_group_names(self, groups: dict[str, str]) -> None:
        """Save a mapping of group resource names to display names."""
        with self._connect() as conn:
            for resource_name, display_name in groups.items():
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                    (f"group:{resource_name}", display_name),
                )

    def get_group_names(self) -> dict[str, str]:
        """Return mapping of group resource names to display names."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM metadata WHERE key LIKE 'group:%'"
            ).fetchall()
            return {row[0].removeprefix("group:"): row[1] for row in rows}

    def save_sync_token(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('sync_token', ?)",
                (token,),
            )

    def get_last_sync_time(self) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(synced_at) FROM contacts"
            ).fetchone()
            if row and row[0]:
                return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)
            return None

    def get_sync_token(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'sync_token'"
            ).fetchone()
            return row[0] if row else None
