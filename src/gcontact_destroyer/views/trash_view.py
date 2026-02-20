from __future__ import annotations

import urllib.parse
import webbrowser

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Input
from textual.message import Message

from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.models import Contact, Status


class TrashView(Container):
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("u", "untrash_selected", "Un-trash", show=True),
        Binding("asterisk", "protect_selected", "Protect", show=True),
        Binding("z", "undo", "Undo", show=True),
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

    def __init__(self, db: ContactsDB, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db = db
        self._contacts: list[Contact] = []
        self._search_query: str = ""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search trashed contacts... (Esc to clear)",
            id="trash-search-input",
        )
        yield DataTable(id="trash-table")

    @property
    def table(self) -> DataTable:
        return self.query_one("#trash-table", DataTable)

    @property
    def search_input(self) -> Input:
        return self.query_one("#trash-search-input", Input)

    def on_mount(self) -> None:
        table = self.table
        table.cursor_type = "row"
        table.add_columns("Name", "Email", "Phone", "Org")
        self.search_input.display = False
        self.reload_contacts()
        table.focus()

    def reload_contacts(self, restore_cursor: int | None = None) -> None:
        if self._search_query:
            all_contacts = self.db.search(self._search_query, exclude_protected=False)
            self._contacts = [c for c in all_contacts if c.status == Status.TRASHED]
        else:
            self._contacts = self.db.get_contacts(status=Status.TRASHED)

        self._contacts = [
            c for c in self._contacts if c.display_name or c.emails or c.phones
        ]

        table = self.table
        prev_row = restore_cursor if restore_cursor is not None else table.cursor_row
        table.clear()
        for c in self._contacts:
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

    def action_untrash_selected(self) -> None:
        contact = self._get_selected_contact()
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.UNMARKED)
        self.reload_contacts()
        self.post_message(self.StatusChanged())

    def action_undo(self) -> None:
        if not self.app._undo_stack:
            self.app.notify("Nothing to undo", severity="warning")
            return
        resource_name, prev_status = self.app._undo_stack.pop()
        self.db.set_status(resource_name, prev_status)
        self.reload_contacts()
        self.post_message(self.StatusChanged())

    def action_protect_selected(self) -> None:
        contact = self._get_selected_contact()
        if contact is None:
            return
        self.app._undo_stack.append((contact.resource_name, contact.status))
        self.db.set_status(contact.resource_name, Status.PROTECTED)
        self.post_message(self.KeepLabelRequested(contact.resource_name))
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
        self._show_detail()

    def _show_detail(self) -> None:
        if not self._contacts:
            return
        index = self.table.cursor_row
        if index < 0 or index >= len(self._contacts):
            return

        from gcontact_destroyer.views.expand_panel import ContactDetailScreen

        def handle_result(result: tuple[str | None, Contact | None]) -> None:
            action, contact = result
            if contact is None:
                return
            if action == "trash":
                # Already trashed; un-trash (toggle behavior)
                self.app._undo_stack.append((contact.resource_name, contact.status))
                self.db.set_status(contact.resource_name, Status.UNMARKED)
                self.reload_contacts()
                self.post_message(self.StatusChanged())
            elif action == "protect":
                self.app._undo_stack.append((contact.resource_name, contact.status))
                self.db.set_status(contact.resource_name, Status.PROTECTED)
                self.post_message(self.KeepLabelRequested(contact.resource_name))
                self.reload_contacts()
                self.post_message(self.StatusChanged())

        self.app.push_screen(
            ContactDetailScreen(
                self._contacts, index, group_names=self.db.get_group_names()
            ),
            handle_result,
        )

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
