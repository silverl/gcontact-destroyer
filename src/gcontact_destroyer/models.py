from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    UNMARKED = "unmarked"
    TRASHED = "trashed"
    PROTECTED = "protected"


@dataclass
class Contact:
    resource_name: str
    display_name: str = ""
    first_name: str = ""
    last_name: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    organizations: list[dict[str, str]] = field(default_factory=list)
    status: Status = Status.UNMARKED
    etag: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)
    group_resource_names: list[str] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Contact:
        names = data.get("names", [])
        name_entry = names[0] if names else {}

        emails = [e["value"] for e in data.get("emailAddresses", [])]
        phones = [p["value"] for p in data.get("phoneNumbers", [])]
        orgs = [
            {k: v for k, v in org.items() if k in ("name", "title", "department")}
            for org in data.get("organizations", [])
        ]
        groups = [
            m["contactGroupMembership"]["contactGroupResourceName"]
            for m in data.get("memberships", [])
            if "contactGroupMembership" in m
        ]

        return cls(
            resource_name=data["resourceName"],
            display_name=name_entry.get("displayName", ""),
            first_name=name_entry.get("givenName", ""),
            last_name=name_entry.get("familyName", ""),
            emails=emails,
            phones=phones,
            organizations=orgs,
            etag=data.get("etag", ""),
            raw_json=data,
            group_resource_names=groups,
        )

    @property
    def primary_email(self) -> str:
        return self.emails[0] if self.emails else ""

    @property
    def primary_phone(self) -> str:
        return self.phones[0] if self.phones else ""

    @property
    def primary_org(self) -> str:
        if self.organizations:
            return self.organizations[0].get("name", "")
        return ""

    @property
    def email_domain(self) -> str:
        email = self.primary_email
        if "@" in email:
            return email.split("@", 1)[1]
        return ""

    @property
    def notes(self) -> str:
        raw = self.raw_json
        if isinstance(raw, str):
            raw = json.loads(raw)
        bios = raw.get("biographies", [])
        if bios:
            return bios[0].get("value", "")
        return ""

    @property
    def nickname(self) -> str:
        raw = self.raw_json
        if isinstance(raw, str):
            raw = json.loads(raw)
        nicks = raw.get("nicknames", [])
        return nicks[0].get("value", "") if nicks else ""

    @property
    def birthday(self) -> str:
        raw = self.raw_json
        if isinstance(raw, str):
            raw = json.loads(raw)
        bdays = raw.get("birthdays", [])
        if not bdays:
            return ""
        bday = bdays[0]
        if "text" in bday:
            return bday["text"]
        date = bday.get("date", {})
        month = date.get("month")
        day = date.get("day")
        if not month or not day:
            return ""
        month_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        year = date.get("year")
        if year:
            return f"{month_abbr[month - 1]} {day}, {year}"
        return f"{month_abbr[month - 1]} {day}"

    @property
    def urls(self) -> list[str]:
        raw = self.raw_json
        if isinstance(raw, str):
            raw = json.loads(raw)
        return [u["value"] for u in raw.get("urls", []) if u.get("value")]

    @property
    def is_sparse(self) -> bool:
        return not self.emails and not self.phones

    @property
    def completeness_label(self) -> str:
        has_name = bool(self.display_name)
        has_email = bool(self.emails)
        has_phone = bool(self.phones)

        if not has_name and not has_email and not has_phone:
            return "No name, no email, no phone"
        if has_name and not has_email and not has_phone:
            return "Name only (no email/phone)"
        if has_email and not has_name:
            return "Email only (no name)"
        if has_phone and not has_name and not has_email:
            return "Phone only (no name)"
        return "Complete"

    def to_db_row(self) -> dict[str, Any]:
        return {
            "resource_name": self.resource_name,
            "display_name": self.display_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "emails": json.dumps(self.emails),
            "phones": json.dumps(self.phones),
            "organizations": json.dumps(self.organizations),
            "status": self.status.value,
            "etag": self.etag,
            "raw_json": json.dumps(self.raw_json),
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> Contact:
        return cls(
            resource_name=row["resource_name"],
            display_name=row["display_name"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            emails=json.loads(row["emails"]),
            phones=json.loads(row["phones"]),
            organizations=json.loads(row["organizations"]),
            status=Status(row["status"]),
            etag=row["etag"],
            raw_json=json.loads(row["raw_json"]) if row["raw_json"] else {},
        )
