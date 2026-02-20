from __future__ import annotations

import urllib.parse
import webbrowser

from rich.markup import escape

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import Static
from textual.message import Message

from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.models import Contact, Status


class CardView(Container, can_focus=True):
    DEFAULT_CSS = """
    CardView {
        align: left top;
    }
    #card-container {
        margin: 5 0 0 5;
        width: 80;
        height: auto;
        max-height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #card-position {
        color: $text-muted;
        margin-bottom: 1;
    }
    #card-name {
        text-style: bold;
        margin-bottom: 1;
    }
    .card-field {
        margin-bottom: 0;
    }
    .card-label {
        color: $text-muted;
    }
    #card-notes {
        margin-top: 1;
        color: $warning;
    }
    #card-actions {
        margin-bottom: 1;
        color: yellow;
    }
    """

    BINDINGS = [
        Binding("x", "trash_card", "Trash", show=True),
        Binding("asterisk", "protect_card", "Protect", show=True),
        Binding("j", "next_card", "Next", show=False),
        Binding("l", "next_card", "Next", show=False),
        Binding("h", "prev_card", "Prev", show=False),
        Binding("k", "prev_card", "Prev", show=False),
        Binding("s", "search_email", "Search Gmail", show=True),
        Binding("u", "undo_card", "Undo", show=True),
        Binding("f", "flush", "Flush", show=True),
        Binding("escape", "back_to_list", "Back", show=True),
        Binding("ctrl+down", "scroll_down", "Scroll Down", show=False),
        Binding("ctrl+up", "scroll_up", "Scroll Up", show=False),
    ]

    class StatusChanged(Message):
        pass

    class FlushRequested(Message):
        pass

    class BackToList(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, db: ContactsDB, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db = db
        self._contacts: list[Contact] = []
        self._index: int = 0

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="card-container"):
            yield Static(id="card-actions")
            yield Static(id="card-position")
            yield Static(id="card-name")
            yield Static("Nickname", classes="card-label-optional", id="card-nickname-label")
            yield Static(id="card-nickname", classes="card-field")
            yield Static("Birthday", classes="card-label-optional", id="card-birthday-label")
            yield Static(id="card-birthday", classes="card-field")
            yield Static("Emails", classes="card-label")
            yield Static(id="card-email", classes="card-field")
            yield Static("Phones", classes="card-label")
            yield Static(id="card-phone", classes="card-field")
            yield Static("Organization", classes="card-label")
            yield Static(id="card-org", classes="card-field")
            yield Static("Websites", classes="card-label-optional", id="card-urls-label")
            yield Static(id="card-urls", classes="card-field")
            yield Static("Groups", classes="card-label-optional", id="card-groups-label")
            yield Static(id="card-groups", classes="card-field")
            yield Static(id="card-notes")

    @property
    def current_contact(self) -> Contact | None:
        if not self._contacts or self._index >= len(self._contacts):
            return None
        return self._contacts[self._index]

    def on_mount(self) -> None:
        self.focus()

    def reload_contacts(self, start_index: int = 0) -> None:
        self._contacts = self.db.get_contacts(exclude_protected=True)
        self._contacts = [
            c
            for c in self._contacts
            if c.status != Status.TRASHED and (c.display_name or c.emails or c.phones)
        ]
        self._index = min(start_index, max(0, len(self._contacts) - 1))
        self._render_card()

    def _render_card(self) -> None:
        contact = self.current_contact
        if contact is None:
            self.query_one("#card-position").update("No contacts remaining!")
            self.query_one("#card-name").update("")
            self.query_one("#card-email").update("")
            self.query_one("#card-phone").update("")
            self.query_one("#card-org").update("")
            self.query_one("#card-notes").update("")
            self.query_one("#card-actions").update("")
            for label in self.query(".card-label"):
                label.display = False
            for widget_id in ("#card-nickname-label", "#card-nickname",
                              "#card-birthday-label", "#card-birthday",
                              "#card-urls-label", "#card-urls",
                              "#card-groups-label", "#card-groups"):
                self.query_one(widget_id).display = False
            return

        total = len(self._contacts)
        self.query_one("#card-position").update(f"{self._index + 1} / {total}")
        self.query_one("#card-name").update(
            contact.display_name or contact.primary_email or contact.primary_phone or "(unknown)"
        )

        # Optional fields: nickname, birthday
        nickname = contact.nickname
        self.query_one("#card-nickname-label").display = bool(nickname)
        self.query_one("#card-nickname").display = bool(nickname)
        if nickname:
            self.query_one("#card-nickname").update(f"  {nickname}")

        birthday = contact.birthday
        self.query_one("#card-birthday-label").display = bool(birthday)
        self.query_one("#card-birthday").display = bool(birthday)
        if birthday:
            self.query_one("#card-birthday").update(f"  {birthday}")

        # Always-shown fields
        self.query_one("#card-email").update(
            "  " + "\n  ".join(contact.emails) if contact.emails else "  (none)"
        )
        self.query_one("#card-phone").update(
            "  " + "\n  ".join(contact.phones) if contact.phones else "  (none)"
        )

        org_parts = []
        for org in contact.organizations:
            parts = [org.get("name", ""), org.get("title", ""), org.get("department", "")]
            org_parts.append(" / ".join(p for p in parts if p))
        self.query_one("#card-org").update(
            "  " + "\n  ".join(org_parts) if org_parts else "  (none)"
        )

        # Optional: websites
        urls = contact.urls
        self.query_one("#card-urls-label").display = bool(urls)
        self.query_one("#card-urls").display = bool(urls)
        if urls:
            self.query_one("#card-urls").update("  " + "\n  ".join(urls))

        # Optional: groups
        system_groups = {
            "contactGroups/myContacts",
            "contactGroups/starred",
            "contactGroups/all",
        }
        group_names_map = self.db.get_group_names()
        raw = contact.raw_json
        if isinstance(raw, str):
            import json
            raw = json.loads(raw)
        memberships = raw.get("memberships", [])
        group_resource_names = [
            m["contactGroupMembership"]["contactGroupResourceName"]
            for m in memberships
            if "contactGroupMembership" in m
        ]
        display_groups = [
            group_names_map.get(rn, rn)
            for rn in group_resource_names
            if rn not in system_groups
        ]
        self.query_one("#card-groups-label").display = bool(display_groups)
        self.query_one("#card-groups").display = bool(display_groups)
        if display_groups:
            self.query_one("#card-groups").update("  " + "\n  ".join(display_groups))

        notes = contact.notes
        self.query_one("#card-notes").update(f"Notes: {escape(notes)}" if notes else "")

        for label in self.query(".card-label"):
            label.display = True

        self.query_one("#card-actions").update(
            "x: Trash  *: Protect  j/l: Next  h/k: Prev  s: Gmail  u: Undo  Esc: Back"
        )

    def action_next_card(self) -> None:
        if self._index < len(self._contacts) - 1:
            self._index += 1
            self._render_card()

    def action_prev_card(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render_card()

    def action_trash_card(self) -> None:
        contact = self.current_contact
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.TRASHED)
        self._contacts.pop(self._index)
        if self._index >= len(self._contacts):
            self._index = max(0, len(self._contacts) - 1)
        self._render_card()
        self.post_message(self.StatusChanged())

    def action_protect_card(self) -> None:
        contact = self.current_contact
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.PROTECTED)
        self._contacts.pop(self._index)
        if self._index >= len(self._contacts):
            self._index = max(0, len(self._contacts) - 1)
        self._render_card()
        self.post_message(self.StatusChanged())

    def action_undo_card(self) -> None:
        if not self.app._undo_stack:
            self.app.notify("Nothing to undo", severity="warning")
            return
        resource_name, prev_status = self.app._undo_stack.pop()
        self.db.set_status(resource_name, prev_status)
        self.reload_contacts(start_index=self._index)
        self.post_message(self.StatusChanged())

    def action_search_email(self) -> None:
        contact = self.current_contact
        if contact is None:
            return
        email = contact.primary_email
        if not email:
            self.app.notify("No email address for this contact", severity="warning")
            return
        query = urllib.parse.quote_plus(email)
        webbrowser.open(f"https://mail.google.com/mail/u/0/#search/{query}")

    def action_back_to_list(self) -> None:
        self.post_message(self.BackToList(self._index))

    def action_scroll_down(self) -> None:
        self.query_one("#card-container", VerticalScroll).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#card-container", VerticalScroll).scroll_up()

    def action_flush(self) -> None:
        self.post_message(self.FlushRequested())
