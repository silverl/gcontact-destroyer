import asyncio
from unittest.mock import MagicMock, patch

import pytest

from gcontact_destroyer.google_api import GooglePeopleAPI, OAuthError


@pytest.fixture
def mock_service():
    return MagicMock()


@pytest.fixture
def api(mock_service, tmp_path):
    token_path = tmp_path / "token.json"
    return GooglePeopleAPI(service=mock_service, token_path=token_path)


class TestFetchAllContacts:
    def test_single_page(self, api, mock_service):
        mock_service.people().connections().list().execute.return_value = {
            "connections": [
                {
                    "resourceName": "people/c1",
                    "etag": "e1",
                    "names": [{"displayName": "Alice"}],
                },
            ],
            "totalItems": 1,
        }
        mock_service.people().connections().list_next.return_value = None

        contacts = api.fetch_all_contacts()
        assert len(contacts) == 1
        assert contacts[0].resource_name == "people/c1"

    def test_multiple_pages(self, api, mock_service):
        first_response = {
            "connections": [{"resourceName": "people/c1", "etag": "e1"}],
            "nextPageToken": "page2",
        }
        second_response = {
            "connections": [{"resourceName": "people/c2", "etag": "e2"}],
        }

        request_mock = MagicMock()
        mock_service.people().connections().list.return_value = request_mock
        request_mock.execute.side_effect = [first_response, second_response]
        mock_service.people().connections().list_next.side_effect = [
            request_mock,
            None,
        ]

        contacts = api.fetch_all_contacts()
        assert len(contacts) == 2

    def test_empty_response(self, api, mock_service):
        mock_service.people().connections().list().execute.return_value = {}
        mock_service.people().connections().list_next.return_value = None

        contacts = api.fetch_all_contacts()
        assert contacts == []


    def test_skips_deleted_contacts(self, api, mock_service):
        mock_service.people().connections().list().execute.return_value = {
            "connections": [
                {
                    "resourceName": "people/c1",
                    "etag": "e1",
                    "names": [{"displayName": "Alice"}],
                },
                {
                    "resourceName": "people/c2",
                    "etag": "e2",
                    "metadata": {"deleted": True},
                },
                {
                    "resourceName": "people/c3",
                    "etag": "e3",
                    "names": [{"displayName": "Bob"}],
                    "metadata": {"deleted": False},
                },
            ],
        }
        mock_service.people().connections().list_next.return_value = None

        contacts = api.fetch_all_contacts()
        assert len(contacts) == 2
        assert contacts[0].resource_name == "people/c1"
        assert contacts[1].resource_name == "people/c3"


class TestBatchDelete:
    def test_batch_delete_single_batch(self, api, mock_service):
        names = [f"people/c{i}" for i in range(10)]
        mock_service.people().batchDeleteContacts().execute.return_value = {}

        api.batch_delete(names)

        mock_service.people().batchDeleteContacts.assert_called()

    def test_batch_delete_multiple_batches(self, api, mock_service):
        names = [f"people/c{i}" for i in range(600)]
        mock_service.people().batchDeleteContacts().execute.return_value = {}

        api.batch_delete(names, batch_size=500)

        assert mock_service.people().batchDeleteContacts.call_count >= 2


class TestFetchContactGroups:
    def test_fetch_groups(self, api, mock_service):
        mock_service.contactGroups().list().execute.return_value = {
            "contactGroups": [
                {
                    "resourceName": "contactGroups/abc",
                    "name": "Keep",
                    "memberCount": 5,
                    "groupType": "USER_CONTACT_GROUP",
                },
                {
                    "resourceName": "contactGroups/myContacts",
                    "name": "myContacts",
                    "groupType": "SYSTEM_CONTACT_GROUP",
                },
            ]
        }

        groups = api.fetch_contact_groups()
        assert len(groups) == 1
        assert groups[0]["name"] == "Keep"

    def test_find_keep_group(self, api, mock_service):
        mock_service.contactGroups().list().execute.return_value = {
            "contactGroups": [
                {
                    "resourceName": "contactGroups/abc",
                    "name": "Keep",
                    "memberCount": 5,
                    "groupType": "USER_CONTACT_GROUP",
                },
            ]
        }
        resource_name = api.find_group_resource_name("Keep")
        assert resource_name == "contactGroups/abc"


class TestCreateContactGroup:
    def test_create_contact_group_returns_resource_name(self, api, mock_service):
        mock_service.contactGroups().create().execute.return_value = {
            "resourceName": "contactGroups/newgroup123",
            "name": "Keep",
        }

        result = api.create_contact_group("Keep")

        assert result == "contactGroups/newgroup123"
        mock_service.contactGroups().create.assert_called_with(
            body={"contactGroup": {"name": "Keep"}}
        )

    def test_create_contact_group_calls_api(self, api, mock_service):
        mock_service.contactGroups().create().execute.return_value = {
            "resourceName": "contactGroups/xyz",
            "name": "MyGroup",
        }

        api.create_contact_group("MyGroup")

        mock_service.contactGroups().create().execute.assert_called_once()


class TestAddToGroup:
    def test_add_to_group(self, api, mock_service):
        mock_service.contactGroups().members().modify().execute.return_value = {}

        api.add_to_group("contactGroups/abc", ["people/c1", "people/c2"])

        mock_service.contactGroups().members().modify.assert_called()


class TestRemoveFromGroup:
    def test_remove_from_group(self, api, mock_service):
        mock_service.contactGroups().members().modify().execute.return_value = {}

        api.remove_from_group("contactGroups/abc", ["people/c1", "people/c2"])

        mock_service.contactGroups().members().modify.assert_called()


class TestAuthenticateAsync:
    async def test_delegates_to_sync_authenticate(self, tmp_path):
        fake_api = GooglePeopleAPI(service=MagicMock(), token_path=tmp_path / "t.json")
        with patch.object(
            GooglePeopleAPI, "authenticate", return_value=fake_api
        ) as mock_auth:
            result = await GooglePeopleAPI.authenticate_async(
                credentials_path=tmp_path / "creds.json",
                token_path=tmp_path / "t.json",
            )
        mock_auth.assert_called_once_with(
            tmp_path / "creds.json", tmp_path / "t.json"
        )
        assert result is fake_api

    async def test_timeout_raises_oauth_error(self, tmp_path):
        def hang_forever(*args, **kwargs):
            import time
            time.sleep(10)

        with patch.object(GooglePeopleAPI, "authenticate", side_effect=hang_forever):
            with patch("gcontact_destroyer.google_api.OAUTH_TIMEOUT", 0.1):
                with pytest.raises(OAuthError, match="timed out"):
                    await GooglePeopleAPI.authenticate_async(
                        credentials_path=tmp_path / "creds.json",
                        token_path=tmp_path / "t.json",
                    )

    async def test_propagates_auth_exceptions(self, tmp_path):
        with patch.object(
            GooglePeopleAPI,
            "authenticate",
            side_effect=FileNotFoundError("no creds"),
        ):
            with pytest.raises(FileNotFoundError, match="no creds"):
                await GooglePeopleAPI.authenticate_async(
                    credentials_path=tmp_path / "creds.json",
                    token_path=tmp_path / "t.json",
                )
