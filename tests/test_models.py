
from gcontact_destroyer.models import Contact, Status


class TestStatus:
    def test_status_values(self):
        assert Status.UNMARKED == "unmarked"
        assert Status.TRASHED == "trashed"
        assert Status.PROTECTED == "protected"


class TestContact:
    def test_from_api_response_full(self):
        api_data = {
            "resourceName": "people/c123",
            "etag": "abc123",
            "names": [
                {"displayName": "John Doe", "givenName": "John", "familyName": "Doe"}
            ],
            "emailAddresses": [{"value": "john@example.com"}, {"value": "jd@work.com"}],
            "phoneNumbers": [{"value": "555-0101"}],
            "organizations": [{"name": "Acme Corp", "title": "Engineer"}],
            "memberships": [
                {
                    "contactGroupMembership": {
                        "contactGroupResourceName": "contactGroups/abc"
                    }
                },
            ],
        }
        contact = Contact.from_api_response(api_data)

        assert contact.resource_name == "people/c123"
        assert contact.display_name == "John Doe"
        assert contact.first_name == "John"
        assert contact.last_name == "Doe"
        assert contact.emails == ["john@example.com", "jd@work.com"]
        assert contact.phones == ["555-0101"]
        assert contact.organizations == [{"name": "Acme Corp", "title": "Engineer"}]
        assert contact.etag == "abc123"
        assert contact.status == Status.UNMARKED
        assert contact.group_resource_names == ["contactGroups/abc"]

    def test_from_api_response_minimal(self):
        api_data = {"resourceName": "people/c456", "etag": "xyz"}
        contact = Contact.from_api_response(api_data)

        assert contact.resource_name == "people/c456"
        assert contact.display_name == ""
        assert contact.first_name == ""
        assert contact.last_name == ""
        assert contact.emails == []
        assert contact.phones == []
        assert contact.organizations == []

    def test_primary_email(self):
        c = Contact(
            resource_name="people/c1",
            emails=["a@b.com", "c@d.com"],
        )
        assert c.primary_email == "a@b.com"

    def test_primary_email_empty(self):
        c = Contact(resource_name="people/c1")
        assert c.primary_email == ""

    def test_primary_phone(self):
        c = Contact(resource_name="people/c1", phones=["555-1234"])
        assert c.primary_phone == "555-1234"

    def test_primary_phone_empty(self):
        c = Contact(resource_name="people/c1")
        assert c.primary_phone == ""

    def test_primary_org(self):
        c = Contact(
            resource_name="people/c1",
            organizations=[{"name": "Acme", "title": "Dev"}],
        )
        assert c.primary_org == "Acme"

    def test_primary_org_empty(self):
        c = Contact(resource_name="people/c1")
        assert c.primary_org == ""

    def test_email_domain(self):
        c = Contact(resource_name="people/c1", emails=["user@bigcorp.com"])
        assert c.email_domain == "bigcorp.com"

    def test_email_domain_no_email(self):
        c = Contact(resource_name="people/c1")
        assert c.email_domain == ""

    def test_is_sparse_no_email_no_phone(self):
        c = Contact(resource_name="people/c1", display_name="Someone")
        assert c.is_sparse is True

    def test_is_sparse_has_email(self):
        c = Contact(resource_name="people/c1", emails=["a@b.com"])
        assert c.is_sparse is False

    def test_completeness_label_name_only(self):
        c = Contact(resource_name="people/c1", display_name="Someone")
        assert c.completeness_label == "Name only (no email/phone)"

    def test_completeness_label_email_only(self):
        c = Contact(resource_name="people/c1", emails=["a@b.com"])
        assert c.completeness_label == "Email only (no name)"

    def test_completeness_label_phone_only(self):
        c = Contact(resource_name="people/c1", phones=["555"])
        assert c.completeness_label == "Phone only (no name)"

    def test_completeness_label_nothing(self):
        c = Contact(resource_name="people/c1")
        assert c.completeness_label == "No name, no email, no phone"

    def test_completeness_label_complete(self):
        c = Contact(resource_name="people/c1", display_name="X", emails=["a@b.com"])
        assert c.completeness_label == "Complete"

    def test_notes_from_raw_json(self):
        c = Contact(
            resource_name="people/c1",
            raw_json={"biographies": [{"value": "Met at PyCon 2019"}]},
        )
        assert c.notes == "Met at PyCon 2019"

    def test_notes_empty(self):
        c = Contact(resource_name="people/c1", raw_json={})
        assert c.notes == ""

    def test_nickname(self):
        c = Contact(
            resource_name="people/c1",
            raw_json={"nicknames": [{"value": "Johnny", "type": "DEFAULT"}]},
        )
        assert c.nickname == "Johnny"

    def test_nickname_empty(self):
        c = Contact(resource_name="people/c1", raw_json={})
        assert c.nickname == ""

    def test_birthday_with_year(self):
        c = Contact(
            resource_name="people/c1",
            raw_json={"birthdays": [{"date": {"year": 1985, "month": 6, "day": 15}}]},
        )
        assert c.birthday == "Jun 15, 1985"

    def test_birthday_without_year(self):
        c = Contact(
            resource_name="people/c1",
            raw_json={"birthdays": [{"date": {"month": 3, "day": 7}}]},
        )
        assert c.birthday == "Mar 7"

    def test_birthday_text_fallback(self):
        c = Contact(
            resource_name="people/c1",
            raw_json={"birthdays": [{"text": "March 7th"}]},
        )
        assert c.birthday == "March 7th"

    def test_birthday_empty(self):
        c = Contact(resource_name="people/c1", raw_json={})
        assert c.birthday == ""

    def test_urls(self):
        c = Contact(
            resource_name="people/c1",
            raw_json={"urls": [
                {"value": "https://example.com", "type": "homePage"},
                {"value": "https://linkedin.com/in/jdoe", "type": "profile"},
            ]},
        )
        assert c.urls == ["https://example.com", "https://linkedin.com/in/jdoe"]

    def test_urls_empty(self):
        c = Contact(resource_name="people/c1", raw_json={})
        assert c.urls == []

    def test_to_db_row_and_back(self):
        original = Contact(
            resource_name="people/c1",
            display_name="Test",
            first_name="T",
            last_name="Est",
            emails=["t@e.com"],
            phones=["555"],
            organizations=[{"name": "Org"}],
            status=Status.TRASHED,
            etag="e1",
            raw_json={"resourceName": "people/c1"},
        )
        row = original.to_db_row()
        restored = Contact.from_db_row(row)

        assert restored.resource_name == original.resource_name
        assert restored.display_name == original.display_name
        assert restored.emails == original.emails
        assert restored.phones == original.phones
        assert restored.organizations == original.organizations
        assert restored.status == original.status
