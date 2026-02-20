from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import DataTable, Static, TabbedContent, TabPane
from textual.message import Message

from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.models import Status
from gcontact_destroyer.views.expand_panel import ExpandPanel


class BatchView(Container):
    DEFAULT_CSS = """
    BatchView Horizontal {
        height: 1fr;
    }
    BatchView #batch-left {
        width: 1fr;
    }
    BatchView #batch-left.expanded {
        width: 2fr;
    }
    BatchView ExpandPanel {
        width: 3fr;
    }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "prev_tab", "Prev Tab", show=True),
        Binding("l", "next_tab", "Next Tab", show=True),
        Binding("x", "trash_category", "Trash Category", show=True),
        Binding("enter", "expand_category", "Expand", show=True),
        Binding("escape", "collapse", "Back", show=True),
        Binding("f", "flush", "Flush", show=True),
        Binding("tab", "switch_panel", "Switch Panel", show=False),
        Binding("shift+tab", "switch_panel", "Switch Panel", show=False),
    ]

    class StatusChanged(Message):
        pass

    class FlushRequested(Message):
        pass

    def __init__(self, db: ContactsDB, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db = db
        self._expanded: bool = False
        self._active_tab: str = "domain"
        self._focus_panel: str = "left"

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Container(id="batch-left"):
                with TabbedContent():
                    with TabPane("By Domain", id="domain-tab"):
                        yield DataTable(id="domain-table")
                    with TabPane("Sparse Contacts", id="sparse-tab"):
                        yield DataTable(id="sparse-table")
                    with TabPane("By Label", id="label-tab"):
                        yield DataTable(id="label-table")
            yield ExpandPanel(db=self.db, id="expand-panel")
        yield Static(id="batch-confirm", markup=True)

    @property
    def domain_table(self) -> DataTable:
        return self.query_one("#domain-table", DataTable)

    @property
    def sparse_table(self) -> DataTable:
        return self.query_one("#sparse-table", DataTable)

    @property
    def label_table(self) -> DataTable:
        return self.query_one("#label-table", DataTable)

    @property
    def expand_panel(self) -> ExpandPanel:
        return self.query_one("#expand-panel", ExpandPanel)

    def on_mount(self) -> None:
        dt = self.domain_table
        dt.cursor_type = "row"
        dt.add_columns("Domain", "Count")

        st = self.sparse_table
        st.cursor_type = "row"
        st.add_columns("Category", "Count")

        lt = self.label_table
        lt.cursor_type = "row"
        lt.add_columns("Label", "Count")

        self.query_one("#batch-confirm").display = False
        self.expand_panel.display = False
        self.reload_data()

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        tab_id = event.pane.id or ""
        if "domain" in tab_id:
            self._active_tab = "domain"
        elif "sparse" in tab_id:
            self._active_tab = "sparse"
        elif "label" in tab_id:
            self._active_tab = "label"

    def focus(self, scroll_visible: bool = True) -> None:
        self._get_active_table().focus(scroll_visible)

    def reload_data(self) -> None:
        self._load_domains()
        self._load_sparse()
        self._load_labels()

    def _load_domains(self) -> None:
        table = self.domain_table
        table.clear()
        counts = self.db.get_domain_counts()
        for domain, count in counts.items():
            table.add_row(domain, str(count), key=domain)

    def _load_sparse(self) -> None:
        table = self.sparse_table
        table.clear()
        counts = self.db.get_sparse_counts()
        for label, count in counts.items():
            table.add_row(label, str(count), key=label)

    def _load_labels(self) -> None:
        table = self.label_table
        table.clear()
        label_counts = self.db.get_label_counts()
        group_names = self.db.get_group_names()
        if not label_counts:
            table.add_row("(no non-protected labels)", "", key="__empty__")
            return
        for resource_name, count in label_counts.items():
            display_name = group_names.get(resource_name, resource_name)
            table.add_row(display_name, str(count), key=resource_name)

    def _get_active_table(self) -> DataTable:
        if self._active_tab == "sparse":
            return self.sparse_table
        if self._active_tab == "label":
            return self.label_table
        return self.domain_table

    _TAB_ORDER = ["domain", "sparse", "label"]
    _TAB_PANE_IDS = {"domain": "domain-tab", "sparse": "sparse-tab", "label": "label-tab"}

    def action_prev_tab(self) -> None:
        if self._focus_panel == "right" and self._expanded:
            return
        idx = self._TAB_ORDER.index(self._active_tab)
        new_idx = (idx - 1) % len(self._TAB_ORDER)
        self._switch_to_tab(self._TAB_ORDER[new_idx])

    def action_next_tab(self) -> None:
        if self._focus_panel == "right" and self._expanded:
            return
        idx = self._TAB_ORDER.index(self._active_tab)
        new_idx = (idx + 1) % len(self._TAB_ORDER)
        self._switch_to_tab(self._TAB_ORDER[new_idx])

    def _switch_to_tab(self, tab_name: str) -> None:
        self._active_tab = tab_name
        tabbed = self.query_one(TabbedContent)
        tabbed.active = self._TAB_PANE_IDS[tab_name]
        self._get_active_table().focus()

    def action_show_sparse(self) -> None:
        self._active_tab = "sparse"

    def action_cursor_down(self) -> None:
        if self._focus_panel == "right" and self._expanded:
            self.expand_panel.action_cursor_down()
            return
        table = self._get_active_table()
        if table.cursor_row < table.row_count - 1:
            table.move_cursor(row=table.cursor_row + 1)

    def action_cursor_up(self) -> None:
        if self._focus_panel == "right" and self._expanded:
            self.expand_panel.action_cursor_up()
            return
        table = self._get_active_table()
        if table.cursor_row > 0:
            table.move_cursor(row=table.cursor_row - 1)

    def action_trash_category(self) -> None:
        if self._focus_panel == "right" and self._expanded:
            self.expand_panel.action_trash_selected()
            return

        result = self._get_selected_category_contacts()
        if result is None:
            return
        category, contacts = result

        if not contacts:
            return

        from gcontact_destroyer.app import ConfirmScreen

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            for c in contacts:
                if c.status != Status.PROTECTED:
                    self.db.set_status(c.resource_name, Status.TRASHED)

            table = self._get_active_table()
            prev_row = table.cursor_row

            self.app.notify(
                f"Marked {len(contacts)} contacts as trashed",
                severity="information",
            )
            self.reload_data()

            table = self._get_active_table()
            if table.row_count > 0:
                target = min(prev_row, table.row_count - 1)
                table.move_cursor(row=max(0, target))

            self.post_message(self.StatusChanged())

        self.app.push_screen(
            ConfirmScreen(f"Trash {len(contacts)} contacts in '{category}'?"),
            on_confirm,
        )

    def _get_selected_category_contacts(self) -> tuple[str, list] | None:
        table = self._get_active_table()
        if table.row_count == 0:
            return None
        row_idx = table.cursor_row
        row_key = list(table.rows.keys())[row_idx]
        category = str(row_key.value)

        if self._active_tab == "domain":
            contacts = self.db.get_contacts_by_domain(category)
        elif self._active_tab == "sparse":
            contacts = self.db.get_contacts_by_completeness(category)
        elif self._active_tab == "label":
            contacts = self.db.get_contacts_by_label(category)
        else:
            return None
        return category, contacts

    def action_expand_category(self) -> None:
        if self._focus_panel == "right" and self._expanded:
            return  # ExpandPanel handles its own Enter via on_data_table_row_selected

        result = self._get_selected_category_contacts()
        if result is None:
            return
        category, contacts = result

        self._expanded = True
        self._focus_panel = "right"
        self.expand_panel.display = True
        self.query_one("#batch-left").add_class("expanded")
        self.expand_panel.load_contacts(category, contacts)
        self.expand_panel.contacts_table.focus()

    def action_collapse(self, restore_cursor: int | None = None) -> None:
        if self._expanded:
            self._expanded = False
            self._focus_panel = "left"
            self.expand_panel.display = False
            self.query_one("#batch-left").remove_class("expanded")
            table = self._get_active_table()
            prev_row = restore_cursor if restore_cursor is not None else table.cursor_row
            self.reload_data()
            table = self._get_active_table()
            if table.row_count > 0:
                target = min(prev_row, table.row_count - 1)
                table.move_cursor(row=max(0, target))
            table.focus()
        else:
            self.reload_data()

    def action_switch_panel(self) -> None:
        if not self._expanded:
            return
        if self._focus_panel == "left":
            self._focus_panel = "right"
            self.expand_panel.contacts_table.focus()
        else:
            self._focus_panel = "left"
            self._get_active_table().focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        left_tables = {"domain-table", "sparse-table", "label-table"}
        if event.data_table.id in left_tables:
            event.stop()
            self.action_expand_category()

    def action_flush(self) -> None:
        self.post_message(self.FlushRequested())

    def on_expand_panel_flush_requested(self, event: ExpandPanel.FlushRequested) -> None:
        self.post_message(self.FlushRequested())

    def on_expand_panel_status_changed(self, event: ExpandPanel.StatusChanged) -> None:
        table = self._get_active_table()
        prev_row = table.cursor_row
        self.reload_data()
        table = self._get_active_table()
        if table.row_count > 0:
            target = min(prev_row, table.row_count - 1)
            table.move_cursor(row=max(0, target))
        self.post_message(self.StatusChanged())

    def on_expand_panel_panel_empty(self, event: ExpandPanel.PanelEmpty) -> None:
        prev_row = self._get_active_table().cursor_row
        self.action_collapse(restore_cursor=prev_row)
