from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static

from gcontact_destroyer.config import DB_PATH, KEEP_LABEL, ensure_dirs
from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.google_api import GooglePeopleAPI
from gcontact_destroyer.models import Status
from gcontact_destroyer.views.batch_view import BatchView
from gcontact_destroyer.views.card_view import CardView
from gcontact_destroyer.views.expand_panel import ExpandPanel
from gcontact_destroyer.views.list_view import ListView
from gcontact_destroyer.views.protected_view import ProtectedView
from gcontact_destroyer.views.trash_view import TrashView


class SyncPromptScreen(ModalScreen[bool]):
    CSS = """
    SyncPromptScreen {
        align: center middle;
    }
    #sync-prompt-container {
        width: 50;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #sync-prompt-age {
        margin-bottom: 1;
    }
    #sync-prompt-question {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "decline", "No"),
        Binding("escape", "decline", "No"),
    ]

    def __init__(self, age: timedelta) -> None:
        super().__init__()
        hours = int(age.total_seconds() / 3600)
        if hours >= 48:
            self._age_str = f"{hours // 24} days"
        else:
            self._age_str = f"{hours} hours"

    def compose(self) -> ComposeResult:
        with Vertical(id="sync-prompt-container"):
            yield Static(
                f"Last sync was {self._age_str} ago.",
                id="sync-prompt-age",
            )
            yield Static("Sync now? (y/n)", id="sync-prompt-question")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_decline(self) -> None:
        self.dismiss(False)


class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #confirm-message {
        margin-bottom: 1;
    }
    #confirm-question {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "decline", "No"),
        Binding("escape", "decline", "No"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Static(self._message, id="confirm-message")
            yield Static("Continue? (y/n)", id="confirm-question")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_decline(self) -> None:
        self.dismiss(False)


class StatsBar(Static):
    def update_stats(self, stats: dict[str, int]) -> None:
        self.update(
            f" Total: {stats['total']}  |  "
            f"Protected: {stats['protected']}  |  "
            f"Trashed: {stats['trashed']}  |  "
            f"Remaining: {stats['remaining']}"
        )


class GContactDestroyer(App):
    CSS = """
    StatsBar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    TITLE = "gcontact-destroyer"

    BINDINGS = [
        Binding("1", "switch_view('list')", "List View", show=True),
        Binding("2", "switch_view('batch')", "Batch View", show=True),
        Binding("3", "switch_view('protected')", "Protected", show=True),
        Binding("4", "switch_view('trash')", "Trash Review", show=True),
        Binding("q", "quit_app", "Quit", show=True),
    ]

    def __init__(
        self, db_path: Path = DB_PATH, api: GooglePeopleAPI | None = None
    ) -> None:
        super().__init__()
        ensure_dirs()
        self.db = ContactsDB(db_path)
        self._api = api
        self._force_quit = False
        self._sync_on_start = False
        self._current_view = "list"
        self._undo_stack: list[tuple[str, Status]] = []

    async def _get_api(self) -> GooglePeopleAPI:
        if self._api is None:
            self._api = await GooglePeopleAPI.authenticate_async()
        return self._api

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(db=self.db, id="list-view")
        yield CardView(db=self.db, id="card-view")
        yield ProtectedView(db=self.db, id="protected-view")
        yield TrashView(db=self.db, id="trash-view")
        yield BatchView(db=self.db, id="batch-view")
        yield StatsBar(id="stats-bar")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#card-view").display = False
        self.query_one("#protected-view").display = False
        self.query_one("#trash-view").display = False
        self.query_one("#batch-view").display = False
        self.refresh_stats()

        # Focus the list view table so keyboard works immediately
        self.query_one("#list-view", ListView).table.focus()

        if self._sync_on_start:
            self.run_worker(self._do_sync())
        else:
            stats = self.db.get_stats()
            if stats["total"] == 0:
                self.notify(
                    "No contacts cached. Run with --sync to fetch from Google.",
                    severity="warning",
                )
            else:
                last_sync = self.db.get_last_sync_time()
                if last_sync is not None:
                    age = datetime.now(timezone.utc) - last_sync
                    if age > timedelta(hours=24):
                        def handle_sync_prompt(wants_sync: bool) -> None:
                            if wants_sync:
                                self.run_worker(self._do_sync())
                        self.push_screen(SyncPromptScreen(age), handle_sync_prompt)

    async def _do_sync(self) -> None:
        self.notify("Syncing contacts from Google...")
        try:
            api = await self._get_api()
            sync_token = self.db.get_sync_token()
            contacts = api.fetch_all_contacts(sync_token=sync_token)

            keep_group = api.find_group_resource_name(KEEP_LABEL)
            if keep_group is None:
                keep_group = api.create_contact_group(KEEP_LABEL)
            for c in contacts:
                if keep_group in c.group_resource_names:
                    c.status = Status.PROTECTED

            # Save contact group names for batch view labels
            groups = api.fetch_contact_groups()
            group_map = {g["resourceName"]: g["name"] for g in groups}
            self.db.save_group_names(group_map)

            self.db.upsert_contacts(contacts)

            # Full sync (no sync token): remove local contacts absent from Google
            if not sync_token:
                synced_names = {c.resource_name for c in contacts}
                stale = [
                    c.resource_name
                    for c in self.db.get_contacts()
                    if c.resource_name not in synced_names
                ]
                if stale:
                    self.db.delete_contacts(stale)

            self.notify(f"Synced {len(contacts)} contacts", severity="information")
            self.refresh_stats()

            # Apply Keep label to locally-protected contacts not in this sync batch.
            # Contacts IN the sync batch already reflect Google's current state,
            # so we only push Keep for contacts that weren't synced (e.g. locally
            # protected via * key but not yet changed in Google).
            if keep_group:
                synced_names = {c.resource_name for c in contacts}
                protected = self.db.get_contacts(status=Status.PROTECTED)
                missing = [
                    c.resource_name for c in protected
                    if c.resource_name not in synced_names
                ]
                if missing:
                    api.add_to_group(keep_group, missing)
                    self.notify(
                        f"Applied Keep label to {len(missing)} contacts",
                        severity="information",
                    )

            from gcontact_destroyer.views.list_view import ListView

            list_view = self.query_one("#list-view", ListView)
            list_view.reload_contacts()
        except FileNotFoundError as e:
            self.notify(str(e), severity="error")
        except Exception as e:
            self.notify(f"Sync failed: {e}", severity="error")

    async def _do_flush(self) -> None:
        trashed = self.db.get_contacts(status=Status.TRASHED)
        if not trashed:
            self.notify("Nothing to flush", severity="warning")
            return

        resource_names = [c.resource_name for c in trashed]
        self.notify(f"Flushing {len(resource_names)} contacts...")

        try:
            api = await self._get_api()

            # Batch delete
            failed = api.batch_delete(resource_names)

            # Remove successful deletes from local DB
            succeeded = [n for n in resource_names if n not in failed]
            self.db.delete_contacts(succeeded)

            if failed:
                self.notify(
                    f"Deleted {len(succeeded)}, {len(failed)} failed",
                    severity="warning",
                )
            else:
                self.notify(
                    f"Successfully deleted {len(succeeded)} contacts",
                    severity="information",
                )

            self.refresh_stats()
            from gcontact_destroyer.views.list_view import ListView

            list_view = self.query_one("#list-view", ListView)
            list_view.reload_contacts()

            trash_view = self.query_one("#trash-view", TrashView)
            trash_view.reload_contacts()

        except Exception as e:
            self.notify(f"Flush failed: {e}", severity="error")

    def action_switch_view(self, view: str) -> None:
        for name in ("list", "card", "protected", "trash", "batch"):
            widget = self.query_one(f"#{name}-view")
            widget.display = name == view
        self._current_view = view

        # Reload and focus the active view
        active = self.query_one(f"#{view}-view")
        if hasattr(active, "reload_contacts"):
            active.reload_contacts()
        elif hasattr(active, "reload_data"):
            active.reload_data()
        if hasattr(active, "table"):
            active.table.focus()
        else:
            active.focus()

    def action_quit_app(self) -> None:
        stats = self.db.get_stats()
        if stats["trashed"] > 0:
            self.notify(
                f"{stats['trashed']} contacts marked for trash but not flushed. "
                "Press f to flush or q again to quit.",
                severity="warning",
            )
            if self._force_quit:
                self.exit()
            else:
                self._force_quit = True
        else:
            self.exit()

    def refresh_stats(self) -> None:
        stats = self.db.get_stats()
        self.query_one("#stats-bar", StatsBar).update_stats(stats)

    def on_list_view_status_changed(self, event: ListView.StatusChanged) -> None:
        self.refresh_stats()

    def _confirm_flush(self) -> None:
        count = self.db.get_stats()["trashed"]
        if count == 0:
            self.run_worker(self._do_flush())
            return

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self.run_worker(self._do_flush())

        self.push_screen(
            ConfirmScreen(
                f"Flush {count} trashed contacts? This permanently deletes them from Google."
            ),
            on_confirm,
        )

    def on_list_view_flush_requested(self, event) -> None:
        self._confirm_flush()

    def on_list_view_open_card(self, event: ListView.OpenCard) -> None:
        card_view = self.query_one("#card-view", CardView)
        for name in ("list", "card", "batch"):
            self.query_one(f"#{name}-view").display = name == "card"
        self._current_view = "card"
        card_view.reload_contacts(start_index=event.index)
        card_view.focus()

    def on_card_view_status_changed(self, event: CardView.StatusChanged) -> None:
        self.refresh_stats()

    def on_card_view_flush_requested(self, event) -> None:
        self._confirm_flush()

    def on_card_view_back_to_list(self, event: CardView.BackToList) -> None:
        list_view = self.query_one("#list-view", ListView)
        for name in ("list", "card", "batch"):
            self.query_one(f"#{name}-view").display = name == "list"
        self._current_view = "list"
        list_view.reload_contacts(restore_cursor=event.index)
        list_view.table.focus()

    def on_batch_view_status_changed(self, event: BatchView.StatusChanged) -> None:
        self.refresh_stats()

    def on_batch_view_flush_requested(self, event) -> None:
        self._confirm_flush()

    def on_protected_view_status_changed(self, event: ProtectedView.StatusChanged) -> None:
        self.refresh_stats()

    def on_protected_view_flush_requested(self, event) -> None:
        self._confirm_flush()

    def on_trash_view_status_changed(self, event: TrashView.StatusChanged) -> None:
        self.refresh_stats()

    def on_trash_view_flush_requested(self, event) -> None:
        self._confirm_flush()

    def on_trash_view_keep_label_requested(self, event: TrashView.KeepLabelRequested) -> None:
        self.run_worker(self._apply_keep_label(event.resource_name))

    def on_list_view_keep_label_requested(self, event: ListView.KeepLabelRequested) -> None:
        self.run_worker(self._apply_keep_label(event.resource_name))

    def on_card_view_keep_label_requested(self, event: CardView.KeepLabelRequested) -> None:
        self.run_worker(self._apply_keep_label(event.resource_name))

    def on_expand_panel_keep_label_requested(self, event: ExpandPanel.KeepLabelRequested) -> None:
        self.run_worker(self._apply_keep_label(event.resource_name))

    async def _apply_keep_label(self, resource_name: str) -> None:
        try:
            api = await self._get_api()
            group = api.find_group_resource_name(KEEP_LABEL)
            if group is None:
                group = api.create_contact_group(KEEP_LABEL)
            api.add_to_group(group, [resource_name])
        except Exception as e:
            self.notify(f"Failed to apply Keep label: {e}", severity="error")


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Google Contact Destroyer")
    parser.add_argument(
        "--sync", action="store_true", help="Sync contacts from Google on startup"
    )
    args = parser.parse_args()

    # Pre-authenticate before Textual takes over the terminal.
    # This keeps the OAuth browser flow in the normal terminal where
    # Ctrl+C and other input still work.
    api = None
    if args.sync:
        try:
            api = GooglePeopleAPI.authenticate()
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Authentication failed: {e}", file=sys.stderr)
            sys.exit(1)

    app = GContactDestroyer(api=api)
    app._sync_on_start = args.sync
    app.run()

    if DB_PATH.exists():
        print(
            f"\nNote: A local copy of your contacts is stored at\n"
            f"  {DB_PATH}\n"
            "You can delete it any time if you no longer need it."
        )


if __name__ == "__main__":
    main()
