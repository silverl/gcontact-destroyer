from __future__ import annotations

import urllib.parse
import webbrowser

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Input, Static
from textual.message import Message

from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.models import Contact, Status


class ListView(Container):
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("x", "trash_selected", "Trash", show=True),
        Binding("asterisk", "protect_selected", "Protect", show=True),
        Binding("u", "undo", "Undo", show=True),
        Binding("slash", "focus_search", "Search", show=True),
        Binding("s", "search_email", "Search Gmail", show=True),
        Binding("f", "flush", "Flush to Google", show=True),
    ]

    class StatusChanged(Message):
        """Posted when a contact status changes so app can refresh stats."""

    class FlushRequested(Message):
        """Posted when user presses f to flush deletions."""

    class KeepLabelRequested(Message):
        def __init__(self, resource_name: str) -> None:
            super().__init__()
            self.resource_name = resource_name

    class OpenCard(Message):
        """Posted when user presses Enter to open card view at current index."""
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, db: ContactsDB, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db = db
        self._contacts: list[Contact] = []
        self._search_query: str = ""

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search contacts... (Esc to clear)", id="search-input")
        yield DataTable(id="contacts-table")

    @property
    def table(self) -> DataTable:
        return self.query_one("#contacts-table", DataTable)

    def on_mount(self) -> None:
        table = self.table
        table.cursor_type = "row"
        table.add_columns("Name", "Email", "Phone", "Org")
        self.search_input.display = False
        self.reload_contacts()
        table.focus()

    @property
    def search_input(self) -> Input:
        return self.query_one("#search-input", Input)

    def reload_contacts(self, restore_cursor: int | None = None) -> None:
        if self._search_query:
            self._contacts = self.db.search(self._search_query)
        else:
            self._contacts = self.db.get_contacts(exclude_protected=True)

        # Hide trashed contacts and ghost contacts (no name, no email, no phone)
        self._contacts = [
            c for c in self._contacts
            if c.status != Status.TRASHED
            and (c.display_name or c.emails or c.phones)
        ]

        table = self.table
        prev_row = restore_cursor if restore_cursor is not None else table.cursor_row
        table.clear()
        for c in self._contacts:
            # Build a useful display name: fall back to email or phone if no name
            name = c.display_name
            if not name:
                name = c.primary_email or c.primary_phone or "(unknown)"

            table.add_row(
                name,
                c.primary_email,
                c.primary_phone,
                c.primary_org,
                key=c.resource_name,
            )

        # Restore cursor to same position (or one up if we deleted the last row)
        if table.row_count > 0:
            target = min(prev_row, table.row_count - 1)
            table.move_cursor(row=max(0, target))

    def _get_selected_contact(self) -> Contact | None:
        table = self.table
        if table.row_count == 0:
            return None
        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self._contacts):
            return None
        return self._contacts[row_idx]

    def action_cursor_down(self) -> None:
        table = self.table
        if table.cursor_row < table.row_count - 1:
            table.move_cursor(row=table.cursor_row + 1)

    def action_cursor_up(self) -> None:
        table = self.table
        if table.cursor_row > 0:
            table.move_cursor(row=table.cursor_row - 1)

    def action_trash_selected(self) -> None:
        contact = self._get_selected_contact()
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.TRASHED)
        self.reload_contacts()
        self.post_message(self.StatusChanged())

    def action_protect_selected(self) -> None:
        contact = self._get_selected_contact()
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.PROTECTED)
        self.reload_contacts()
        self.post_message(self.StatusChanged())
        self.post_message(self.KeepLabelRequested(contact.resource_name))

    def action_undo(self) -> None:
        if not self.app._undo_stack:
            self.app.notify("Nothing to undo", severity="warning")
            return
        resource_name, prev_status = self.app._undo_stack.pop()
        self.db.set_status(resource_name, prev_status)
        self.reload_contacts()
        self.post_message(self.StatusChanged())

    def action_focus_search(self) -> None:
        self.search_input.display = True
        self.search_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._search_query = event.value
        self.reload_contacts()
        self.table.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._search_query = event.value
        self.reload_contacts()

    def on_key(self, event) -> None:
        if event.key == "escape" and self.search_input.display:
            self._search_query = ""
            self.search_input.value = ""
            self.search_input.display = False
            self.table.focus()
            self.reload_contacts()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table = self.table
        if table.row_count == 0:
            return
        self.post_message(self.OpenCard(table.cursor_row))

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

    def action_flush(self) -> None:
        self.post_message(self.FlushRequested())
