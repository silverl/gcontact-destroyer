from __future__ import annotations

import urllib.parse
import webbrowser

from rich.markup import escape

from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from textual.message import Message

from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.models import Contact, Status


class ContactDetailScreen(ModalScreen[tuple[str | None, Contact | None]]):
    """Modal overlay showing full contact details with j/k navigation."""

    BINDINGS = [
        Binding("escape", "dismiss_detail", "Close", show=True),
        Binding("x", "trash_detail", "Trash", show=True),
        Binding("asterisk", "protect_detail", "Protect", show=True),
        Binding("j", "next_contact", "Next", show=True),
        Binding("k", "prev_contact", "Prev", show=True),
        Binding("ctrl+down", "scroll_down", "Scroll Down", show=False),
        Binding("ctrl+up", "scroll_up", "Scroll Up", show=False),
    ]

    CSS = """
    ContactDetailScreen {
        align: left top;
    }
    #detail-container {
        margin: 5 0 0 5;
        width: 70;
        height: auto;
        max-height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #detail-actions {
        color: yellow;
        margin-bottom: 1;
    }
    #detail-scroll {
        height: auto;
        max-height: 100%;
    }
    #detail-position {
        color: $text-muted;
        margin-bottom: 1;
    }
    #detail-name {
        margin-bottom: 1;
    }
    .detail-label {
        color: $text-muted;
    }
    .detail-value {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        contacts: list[Contact],
        index: int,
        group_names: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._contacts = contacts
        self._index = index
        self._group_names = group_names or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-container"):
            yield Static(
                "x: Trash  *: Protect  j/k: Next/Prev  Esc: Close",
                id="detail-actions",
            )
            with VerticalScroll(id="detail-scroll"):
                yield Static(id="detail-position")
                yield Static(id="detail-name")
                yield Static("Nickname", classes="detail-label", id="detail-nickname-label")
                yield Static(id="detail-nickname", classes="detail-value")
                yield Static("Birthday", classes="detail-label", id="detail-birthday-label")
                yield Static(id="detail-birthday", classes="detail-value")
                yield Static("Emails", classes="detail-label", id="detail-emails-label")
                yield Static(id="detail-emails", classes="detail-value")
                yield Static("Phones", classes="detail-label", id="detail-phones-label")
                yield Static(id="detail-phones", classes="detail-value")
                yield Static(
                    "Organizations", classes="detail-label", id="detail-orgs-label"
                )
                yield Static(id="detail-orgs", classes="detail-value")
                yield Static("Websites", classes="detail-label", id="detail-urls-label")
                yield Static(id="detail-urls", classes="detail-value")
                yield Static("Groups", classes="detail-label", id="detail-groups-label")
                yield Static(id="detail-groups", classes="detail-value")
                yield Static("Notes", classes="detail-label", id="detail-notes-label")
                yield Static(id="detail-notes", classes="detail-value")

    def on_mount(self) -> None:
        self._render_contact()

    def _render_contact(self) -> None:
        c = self._contacts[self._index]
        total = len(self._contacts)

        self.query_one("#detail-position").update(f"{self._index + 1} / {total}")
        self.query_one("#detail-name").update(
            c.display_name or c.primary_email or c.primary_phone or "(unknown)"
        )

        nickname = c.nickname
        self.query_one("#detail-nickname-label").display = bool(nickname)
        self.query_one("#detail-nickname").display = bool(nickname)
        if nickname:
            self.query_one("#detail-nickname").update(f"  {nickname}")

        birthday = c.birthday
        self.query_one("#detail-birthday-label").display = bool(birthday)
        self.query_one("#detail-birthday").display = bool(birthday)
        if birthday:
            self.query_one("#detail-birthday").update(f"  {birthday}")

        self.query_one("#detail-emails-label").display = bool(c.emails)
        self.query_one("#detail-emails").display = bool(c.emails)
        if c.emails:
            self.query_one("#detail-emails").update("  " + "\n  ".join(c.emails))

        self.query_one("#detail-phones-label").display = bool(c.phones)
        self.query_one("#detail-phones").display = bool(c.phones)
        if c.phones:
            self.query_one("#detail-phones").update("  " + "\n  ".join(c.phones))

        self.query_one("#detail-orgs-label").display = bool(c.organizations)
        self.query_one("#detail-orgs").display = bool(c.organizations)
        if c.organizations:
            org_lines = []
            for org in c.organizations:
                parts = [
                    org.get("name", ""),
                    org.get("title", ""),
                    org.get("department", ""),
                ]
                org_lines.append("  " + " / ".join(p for p in parts if p))
            self.query_one("#detail-orgs").update("\n".join(org_lines))

        urls = c.urls
        self.query_one("#detail-urls-label").display = bool(urls)
        self.query_one("#detail-urls").display = bool(urls)
        if urls:
            self.query_one("#detail-urls").update("  " + "\n  ".join(urls))

        # Optional: groups
        system_groups = {
            "contactGroups/myContacts",
            "contactGroups/starred",
            "contactGroups/all",
        }
        raw = c.raw_json
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
            self._group_names.get(rn, rn)
            for rn in group_resource_names
            if rn not in system_groups
        ]
        self.query_one("#detail-groups-label").display = bool(display_groups)
        self.query_one("#detail-groups").display = bool(display_groups)
        if display_groups:
            self.query_one("#detail-groups").update("  " + "\n  ".join(display_groups))

        notes = c.notes
        self.query_one("#detail-notes-label").display = bool(notes)
        self.query_one("#detail-notes").display = bool(notes)
        if notes:
            self.query_one("#detail-notes").update(f"  {escape(notes)}")

        self.query_one("#detail-scroll", VerticalScroll).scroll_to(
            0, 0, animate=False
        )

    def action_next_contact(self) -> None:
        if self._index < len(self._contacts) - 1:
            self._index += 1
            self._render_contact()

    def action_prev_contact(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render_contact()

    def action_scroll_down(self) -> None:
        self.query_one("#detail-scroll", VerticalScroll).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#detail-scroll", VerticalScroll).scroll_up()

    def action_dismiss_detail(self) -> None:
        self.dismiss((None, None))

    def action_trash_detail(self) -> None:
        self.dismiss(("trash", self._contacts[self._index]))

    def action_protect_detail(self) -> None:
        self.dismiss(("protect", self._contacts[self._index]))


class ExpandPanel(Vertical):
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("x", "trash_selected", "Trash", show=True),
        Binding("X", "trash_all_visible", "Trash All", show=True),
        Binding("asterisk", "protect_selected", "Protect", show=True),
        Binding("u", "undo", "Undo", show=True),
        Binding("s", "search_email", "Search Gmail", show=True),
        Binding("enter", "show_detail", "Detail", show=True),
        Binding("f", "flush", "Flush", show=True),
    ]

    class StatusChanged(Message):
        pass

    class FlushRequested(Message):
        pass

    class PanelEmpty(Message):
        pass

    class KeepLabelRequested(Message):
        def __init__(self, resource_name: str) -> None:
            super().__init__()
            self.resource_name = resource_name

    def __init__(self, db: ContactsDB, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db = db
        self._contacts: list[Contact] = []
        self._category: str = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="expand-header")
        yield DataTable(id="expand-contacts-table")

    @property
    def contacts_table(self) -> DataTable:
        return self.query_one("#expand-contacts-table", DataTable)

    def on_mount(self) -> None:
        table = self.contacts_table
        table.cursor_type = "row"
        table.add_columns("Name", "Email", "Phone", "Org")

    def load_contacts(self, category: str, contacts: list[Contact]) -> None:
        self._category = category
        self._contacts = [
            c for c in contacts if c.status not in (Status.TRASHED, Status.PROTECTED)
        ]
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.contacts_table
        prev_row = table.cursor_row if table.row_count > 0 else 0
        table.clear()
        header = self.query_one("#expand-header", Static)
        header.update(f"{self._category} ({len(self._contacts)} contacts)")
        for c in self._contacts:
            name = c.display_name or c.primary_email or c.primary_phone or "(unknown)"
            table.add_row(
                name,
                c.primary_email,
                c.primary_phone,
                c.primary_org,
                key=c.resource_name,
            )
        if table.row_count > 0:
            target = min(prev_row, table.row_count - 1)
            table.move_cursor(row=max(0, target))
        else:
            self.post_message(self.PanelEmpty())

    def _get_selected_contact(self) -> Contact | None:
        table = self.contacts_table
        if table.row_count == 0:
            return None
        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self._contacts):
            return None
        return self._contacts[row_idx]

    def action_cursor_down(self) -> None:
        table = self.contacts_table
        if table.cursor_row < table.row_count - 1:
            table.move_cursor(row=table.cursor_row + 1)

    def action_cursor_up(self) -> None:
        table = self.contacts_table
        if table.cursor_row > 0:
            table.move_cursor(row=table.cursor_row - 1)

    def action_trash_selected(self) -> None:
        contact = self._get_selected_contact()
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.TRASHED)
        self._contacts = [
            c for c in self._contacts if c.resource_name != contact.resource_name
        ]
        self._refresh_table()
        self.post_message(self.StatusChanged())

    def action_trash_all_visible(self) -> None:
        if not self._contacts:
            return

        from gcontact_destroyer.app import ConfirmScreen

        count = len(self._contacts)

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            for c in self._contacts:
                if c.status != Status.TRASHED:
                    self.app._undo_stack.append((c.resource_name, c.status))
                    self.db.set_status(c.resource_name, Status.TRASHED)
            self._contacts.clear()
            self._refresh_table()
            self.post_message(self.StatusChanged())

        self.app.push_screen(
            ConfirmScreen(f"Trash all {count} visible contacts?"),
            on_confirm,
        )

    def action_protect_selected(self) -> None:
        contact = self._get_selected_contact()
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.PROTECTED)
        self._contacts = [
            c for c in self._contacts if c.resource_name != contact.resource_name
        ]
        self._refresh_table()
        self.post_message(self.StatusChanged())
        self.post_message(self.KeepLabelRequested(contact.resource_name))

    def action_undo(self) -> None:
        if not self.app._undo_stack:
            self.app.notify("Nothing to undo", severity="warning")
            return
        resource_name, prev_status = self.app._undo_stack.pop()
        self.db.set_status(resource_name, prev_status)
        contact = self.db.get_contact(resource_name)
        if contact and contact.status not in (Status.TRASHED, Status.PROTECTED):
            self._contacts.append(contact)
        self._refresh_table()
        self.post_message(self.StatusChanged())

    def action_flush(self) -> None:
        self.post_message(self.FlushRequested())

    def action_search_email(self) -> None:
        contact = self._get_selected_contact()
        if contact is None:
            return
        email = contact.primary_email
        if not email:
            self.app.notify("No email address for this contact", severity="warning")
            return
        query = urllib.parse.quote_plus(email)
        webbrowser.open(f"https://mail.google.com/mail/u/0/#search/{query}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_show_detail()

    def action_show_detail(self) -> None:
        if not self._contacts:
            return
        row_idx = self.contacts_table.cursor_row
        if row_idx < 0 or row_idx >= len(self._contacts):
            return

        def handle_result(result: tuple[str | None, Contact | None]) -> None:
            action, contact = result
            if contact is None:
                return
            if action == "trash":
                self.app._undo_stack.append((contact.resource_name, contact.status))
                self.db.set_status(contact.resource_name, Status.TRASHED)
                self._contacts = [
                    c
                    for c in self._contacts
                    if c.resource_name != contact.resource_name
                ]
                self._refresh_table()
                self.post_message(self.StatusChanged())
            elif action == "protect":
                self.app._undo_stack.append((contact.resource_name, contact.status))
                self.db.set_status(contact.resource_name, Status.PROTECTED)
                self._contacts = [
                    c
                    for c in self._contacts
                    if c.resource_name != contact.resource_name
                ]
                self._refresh_table()
                self.post_message(self.StatusChanged())
                self.post_message(self.KeepLabelRequested(contact.resource_name))

        self.app.push_screen(
            ContactDetailScreen(
                self._contacts, row_idx, group_names=self.db.get_group_names()
            ),
            handle_result,
        )
