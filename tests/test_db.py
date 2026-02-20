import sqlite3
from datetime import datetime, timezone

import pytest

from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.models import Contact, Status


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    return ContactsDB(db_path)


@pytest.fixture
def sample_contacts():
    return [
        Contact(
            resource_name="people/c1",
            display_name="Alice Smith",
            first_name="Alice",
            last_name="Smith",
            emails=["alice@example.com"],
            phones=["555-0001"],
            organizations=[{"name": "Acme"}],
            etag="e1",
        ),
        Contact(
            resource_name="people/c2",
            display_name="Bob Jones",
            first_name="Bob",
            last_name="Jones",
            emails=["bob@bigcorp.com"],
            phones=[],
            organizations=[],
            etag="e2",
        ),
        Contact(
            resource_name="people/c3",
            display_name="",
            emails=["mystery@unknown.com"],
            etag="e3",
        ),
    ]


class TestContactsDB:
    def test_creates_table(self, db):
        conn = sqlite3.connect(db.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_upsert_and_get_all(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        results = db.get_contacts()
        assert len(results) == 3

    def test_upsert_updates_existing(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        updated = Contact(
            resource_name="people/c1",
            display_name="Alice Johnson",
            emails=["alice@new.com"],
            etag="e1-updated",
        )
        db.upsert_contacts([updated])
        results = db.get_contacts()
        assert len(results) == 3
        alice = next(c for c in results if c.resource_name == "people/c1")
        assert alice.display_name == "Alice Johnson"

    def test_upsert_updates_status_protected_to_unmarked(self, db, sample_contacts):
        """When Keep label is removed in Google, sync should un-protect the contact."""
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c1", Status.PROTECTED)
        assert db.get_contact("people/c1").status == Status.PROTECTED

        # Re-sync the same contact without PROTECTED status (Keep label removed)
        re_synced = Contact(
            resource_name="people/c1",
            display_name="Alice Smith",
            emails=["alice@example.com"],
            status=Status.UNMARKED,
            etag="e1-v2",
        )
        db.upsert_contacts([re_synced])
        assert db.get_contact("people/c1").status == Status.UNMARKED

    def test_upsert_preserves_trashed_status(self, db, sample_contacts):
        """Trashed is a local user decision; sync should not overwrite it."""
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c1", Status.TRASHED)

        re_synced = Contact(
            resource_name="people/c1",
            display_name="Alice Smith",
            emails=["alice@example.com"],
            status=Status.UNMARKED,
            etag="e1-v2",
        )
        db.upsert_contacts([re_synced])
        assert db.get_contact("people/c1").status == Status.TRASHED

    def test_upsert_sets_protected_status(self, db, sample_contacts):
        """Sync should mark contacts with Keep label as protected."""
        db.upsert_contacts(sample_contacts)

        re_synced = Contact(
            resource_name="people/c1",
            display_name="Alice Smith",
            emails=["alice@example.com"],
            status=Status.PROTECTED,
            etag="e1-v2",
        )
        db.upsert_contacts([re_synced])
        assert db.get_contact("people/c1").status == Status.PROTECTED

    def test_get_contacts_excludes_protected(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c1", Status.PROTECTED)
        results = db.get_contacts(exclude_protected=True)
        assert len(results) == 2
        assert all(c.resource_name != "people/c1" for c in results)

    def test_get_contacts_by_status(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c1", Status.TRASHED)
        results = db.get_contacts(status=Status.TRASHED)
        assert len(results) == 1
        assert results[0].resource_name == "people/c1"

    def test_set_status(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c2", Status.TRASHED)
        contact = db.get_contact("people/c2")
        assert contact.status == Status.TRASHED

    def test_get_contact(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        contact = db.get_contact("people/c1")
        assert contact.display_name == "Alice Smith"

    def test_get_contact_not_found(self, db):
        assert db.get_contact("people/nope") is None

    def test_search(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        results = db.search("alice")
        assert len(results) == 1
        assert results[0].display_name == "Alice Smith"

    def test_search_by_email(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        results = db.search("bigcorp")
        assert len(results) == 1
        assert results[0].display_name == "Bob Jones"

    def test_search_excludes_protected(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c1", Status.PROTECTED)
        results = db.search("alice")
        assert len(results) == 0

    def test_delete_contacts(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        db.delete_contacts(["people/c1", "people/c2"])
        results = db.get_contacts()
        assert len(results) == 1

    def test_get_domain_counts(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        counts = db.get_domain_counts()
        assert counts["example.com"] == 1
        assert counts["bigcorp.com"] == 1

    def test_get_domain_counts_excludes_protected(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c1", Status.PROTECTED)
        counts = db.get_domain_counts()
        assert "example.com" not in counts

    def test_get_contacts_by_domain(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        results = db.get_contacts_by_domain("bigcorp.com")
        assert len(results) == 1
        assert results[0].display_name == "Bob Jones"

    def test_get_sparse_counts(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        counts = db.get_sparse_counts()
        assert isinstance(counts, dict)

    def test_stats(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        db.set_status("people/c1", Status.PROTECTED)
        db.set_status("people/c2", Status.TRASHED)
        stats = db.get_stats()
        assert stats["total"] == 3
        assert stats["protected"] == 1
        assert stats["trashed"] == 1
        assert stats["remaining"] == 1

    def test_save_and_get_sync_token(self, db):
        db.save_sync_token("token123")
        assert db.get_sync_token() == "token123"

    def test_get_sync_token_none(self, db):
        assert db.get_sync_token() is None

    def test_get_last_sync_time_none_when_empty(self, db):
        assert db.get_last_sync_time() is None

    def test_get_last_sync_time_returns_utc_datetime(self, db, sample_contacts):
        db.upsert_contacts(sample_contacts)
        result = db.get_last_sync_time()
        assert result is not None
        assert result.tzinfo == timezone.utc
        # Should be recent (within the last minute)
        age = datetime.now(timezone.utc) - result
        assert age.total_seconds() < 60
