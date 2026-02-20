from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from gcontact_destroyer.config import (
    CREDENTIALS_PATH,
    SCOPES,
    SYNC_PAGE_SIZE,
    BATCH_DELETE_SIZE,
    TOKEN_PATH,
    ensure_dirs,
)
from gcontact_destroyer.models import Contact

OAUTH_TIMEOUT = 120  # seconds to wait for OAuth before giving up


class OAuthError(Exception):
    """Raised when OAuth authentication fails or times out."""


class GooglePeopleAPI:
    PERSON_FIELDS = (
        "names,emailAddresses,phoneNumbers,organizations,memberships,metadata,"
        "biographies,nicknames,birthdays,urls"
    )

    def __init__(
        self,
        service: Any = None,
        token_path: Path = TOKEN_PATH,
    ) -> None:
        self._service = service
        self._token_path = token_path

    @classmethod
    def authenticate(
        cls,
        credentials_path: Path = CREDENTIALS_PATH,
        token_path: Path = TOKEN_PATH,
    ) -> GooglePeopleAPI:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        ensure_dirs()
        creds = None

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not credentials_path.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {credentials_path}. "
                        "Download it from Google Cloud Console and place it at "
                        f"{credentials_path}. See docs/google-setup.md for instructions."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            token_path.write_text(creds.to_json())

        service = build("people", "v1", credentials=creds)
        return cls(service=service, token_path=token_path)

    @classmethod
    async def authenticate_async(
        cls,
        credentials_path: Path = CREDENTIALS_PATH,
        token_path: Path = TOKEN_PATH,
    ) -> GooglePeopleAPI:
        """Async-safe authenticate that won't block the event loop.

        Runs the blocking OAuth flow in a separate thread with a timeout
        so the TUI stays responsive (Ctrl+C, etc. still work).
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(cls.authenticate, credentials_path, token_path),
                timeout=OAUTH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise OAuthError(
                f"OAuth timed out after {OAUTH_TIMEOUT}s. "
                "Please retry — make sure your browser completed the sign-in."
            )

    def fetch_all_contacts(
        self,
        sync_token: str | None = None,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Contact]:
        contacts: list[Contact] = []

        kwargs: dict[str, Any] = {
            "resourceName": "people/me",
            "pageSize": SYNC_PAGE_SIZE,
            "personFields": self.PERSON_FIELDS,
        }
        if sync_token:
            kwargs["syncToken"] = sync_token

        request = self._service.people().connections().list(**kwargs)

        while request is not None:
            response = request.execute()
            for entry in response.get("connections", []):
                metadata = entry.get("metadata", {})
                if metadata.get("deleted"):
                    continue
                contacts.append(Contact.from_api_response(entry))

            if progress_callback:
                progress_callback(len(contacts))

            request = self._service.people().connections().list_next(request, response)

        return contacts

    def batch_delete(
        self,
        resource_names: list[str],
        batch_size: int = BATCH_DELETE_SIZE,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        failed: list[str] = []
        total = len(resource_names)

        for i in range(0, total, batch_size):
            chunk = resource_names[i : i + batch_size]
            try:
                self._service.people().batchDeleteContacts(
                    body={"resourceNames": chunk}
                ).execute()
            except Exception:
                failed.extend(chunk)

            if progress_callback:
                progress_callback(min(i + batch_size, total), total)

        return failed

    def fetch_contact_groups(self) -> list[dict[str, Any]]:
        response = (
            self._service.contactGroups()
            .list(
                pageSize=1000,
                groupFields="name,memberCount,groupType",
            )
            .execute()
        )

        return [
            {
                "resourceName": g["resourceName"],
                "name": g.get("name", ""),
                "memberCount": g.get("memberCount", 0),
            }
            for g in response.get("contactGroups", [])
            if g.get("groupType") == "USER_CONTACT_GROUP"
        ]

    def find_group_resource_name(self, group_name: str) -> str | None:
        groups = self.fetch_contact_groups()
        for g in groups:
            if g["name"] == group_name:
                return g["resourceName"]
        return None

    def create_contact_group(self, name: str) -> str:
        response = (
            self._service.contactGroups()
            .create(body={"contactGroup": {"name": name}})
            .execute()
        )
        return response["resourceName"]

    def add_to_group(
        self,
        group_resource_name: str,
        resource_names: list[str],
    ) -> None:
        self._service.contactGroups().members().modify(
            resourceName=group_resource_name,
            body={"resourceNamesToAdd": resource_names},
        ).execute()
