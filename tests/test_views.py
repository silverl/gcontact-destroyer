import pytest

from textual.app import App, ComposeResult

from textual.widgets import Static

from gcontact_destroyer.app import ConfirmScreen
from gcontact_destroyer.views.list_view import ListView
from gcontact_destroyer.views.card_view import CardView
from gcontact_destroyer.views.batch_view import BatchView
from gcontact_destroyer.views.expand_panel import ContactDetailScreen, ExpandPanel
from gcontact_destroyer.views.protected_view import ProtectedView
from gcontact_destroyer.views.trash_view import TrashView
from gcontact_destroyer.db import ContactsDB
from gcontact_destroyer.models import Contact, Status


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    cdb = ContactsDB(db_path)
    cdb.upsert_contacts(
        [
            Contact(
                resource_name="people/c1",
                display_name="Alice Smith",
                emails=["alice@example.com"],
                phones=["555-0001"],
                organizations=[{"name": "Acme"}],
                etag="e1",
            ),
            Contact(
                resource_name="people/c2",
                display_name="Bob Jones",
                emails=["bob@bigcorp.com"],
                phones=["555-0002"],
                etag="e2",
            ),
            Contact(
                resource_name="people/c3",
                display_name="Protected Person",
                emails=["protect@safe.com"],
                etag="e3",
            ),
        ]
    )
    cdb.set_status("people/c3", Status.PROTECTED)
    return cdb


class ListViewTestApp(App):
    def __init__(self, db: ContactsDB):
        super().__init__()
        self.db = db
        self._undo_stack: list[tuple[str, Status]] = []

    def compose(self) -> ComposeResult:
        yield ListView(db=self.db)


class TestListView:
    @pytest.mark.asyncio
    async def test_shows_contacts_excludes_protected(self, db):
        async with ListViewTestApp(db).run_test() as pilot:
            app = pilot.app
            list_view = app.query_one(ListView)
            table = list_view.table
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_trash_contact_with_x(self, db):
        async with ListViewTestApp(db).run_test() as pilot:
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            contact = db.get_contact("people/c1")
            assert contact.status == Status.TRASHED

    @pytest.mark.asyncio
    async def test_vim_navigation_j(self, db):
        async with ListViewTestApp(db).run_test() as pilot:
            app = pilot.app
            list_view = app.query_one(ListView)
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            assert list_view.table.cursor_row == 1


class CardViewTestApp(App):
    def __init__(self, db: ContactsDB):
        super().__init__()
        self.db = db
        self._undo_stack: list[tuple[str, Status]] = []

    def compose(self) -> ComposeResult:
        yield CardView(db=self.db)


class TestCardView:
    @pytest.mark.asyncio
    async def test_shows_first_contact(self, db):
        async with CardViewTestApp(db).run_test() as pilot:
            app = pilot.app
            card = app.query_one(CardView)
            card.reload_contacts()
            await pilot.pause()
            assert card.current_contact is not None
            assert card.current_contact.resource_name in ("people/c1", "people/c2")

    @pytest.mark.asyncio
    async def test_trash_advances(self, db):
        async with CardViewTestApp(db).run_test() as pilot:
            app = pilot.app
            card = app.query_one(CardView)
            card.reload_contacts()
            await pilot.pause()
            first = card.current_contact.resource_name
            await pilot.press("x")  # trash
            assert card.current_contact.resource_name != first

    @pytest.mark.asyncio
    async def test_next_advances(self, db):
        async with CardViewTestApp(db).run_test() as pilot:
            app = pilot.app
            card = app.query_one(CardView)
            card.reload_contacts()
            await pilot.pause()
            first = card.current_contact.resource_name
            await pilot.press("j")  # next
            assert card.current_contact.resource_name != first

    @pytest.mark.asyncio
    async def test_undo_goes_back(self, db):
        async with CardViewTestApp(db).run_test() as pilot:
            app = pilot.app
            card = app.query_one(CardView)
            card.reload_contacts()
            await pilot.pause()
            first = card.current_contact.resource_name
            await pilot.press("x")  # trash
            await pilot.press("u")  # undo
            assert card.current_contact.resource_name == first

    @pytest.mark.asyncio
    async def test_groups_shown_when_present(self, db):
        """Groups section appears when contact has non-system group memberships."""
        db.save_group_names({"contactGroups/friends": "Friends"})
        db.upsert_contacts([
            Contact(
                resource_name="people/cg1",
                display_name="Grouped Person",
                emails=["grouped@example.com"],
                etag="eg1",
                raw_json={
                    "memberships": [
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/myContacts"}},
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/friends"}},
                    ]
                },
            ),
        ])
        async with CardViewTestApp(db).run_test() as pilot:
            card = pilot.app.query_one(CardView)
            card.reload_contacts()
            await pilot.pause()
            # Navigate to the grouped contact
            while card.current_contact and card.current_contact.resource_name != "people/cg1":
                await pilot.press("j")
                await pilot.pause()
            assert card.current_contact.resource_name == "people/cg1"
            groups_label = pilot.app.query_one("#card-groups-label")
            groups_value = pilot.app.query_one("#card-groups")
            assert groups_label.display is True
            assert groups_value.display is True
            assert "Friends" in str(groups_value.render())

    @pytest.mark.asyncio
    async def test_groups_hidden_when_only_system_groups(self, db):
        """Groups section is hidden when contact only has system group memberships."""
        db.upsert_contacts([
            Contact(
                resource_name="people/cg2",
                display_name="System Only",
                emails=["sys@example.com"],
                etag="eg2",
                raw_json={
                    "memberships": [
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/myContacts"}},
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/starred"}},
                    ]
                },
            ),
        ])
        async with CardViewTestApp(db).run_test() as pilot:
            card = pilot.app.query_one(CardView)
            card.reload_contacts()
            await pilot.pause()
            while card.current_contact and card.current_contact.resource_name != "people/cg2":
                await pilot.press("j")
                await pilot.pause()
            assert card.current_contact.resource_name == "people/cg2"
            groups_label = pilot.app.query_one("#card-groups-label")
            groups_value = pilot.app.query_one("#card-groups")
            assert groups_label.display is False
            assert groups_value.display is False

    @pytest.mark.asyncio
    async def test_groups_hidden_when_no_memberships(self, db):
        """Groups section is hidden when contact has no memberships at all."""
        async with CardViewTestApp(db).run_test() as pilot:
            card = pilot.app.query_one(CardView)
            card.reload_contacts()
            await pilot.pause()
            # Default fixture contacts have no raw_json memberships
            groups_label = pilot.app.query_one("#card-groups-label")
            groups_value = pilot.app.query_one("#card-groups")
            assert groups_label.display is False
            assert groups_value.display is False


class ContactDetailScreenTestApp(App):
    def __init__(self, contacts: list[Contact], index: int = 0,
                 group_names: dict[str, str] | None = None):
        super().__init__()
        self._contacts = contacts
        self._index = index
        self._group_names = group_names

    def compose(self) -> ComposeResult:
        yield Static("base")

    def on_mount(self) -> None:
        self.push_screen(
            ContactDetailScreen(
                self._contacts, self._index, group_names=self._group_names
            )
        )


class TestContactDetailScreenGroups:
    @pytest.mark.asyncio
    async def test_groups_shown_in_detail_screen(self):
        """ContactDetailScreen shows groups when contact has non-system memberships."""
        contacts = [
            Contact(
                resource_name="people/d1",
                display_name="Detail Person",
                emails=["detail@example.com"],
                raw_json={
                    "memberships": [
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/myContacts"}},
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/work"}},
                    ]
                },
            ),
        ]
        group_names = {"contactGroups/work": "Work Colleagues"}
        async with ContactDetailScreenTestApp(
            contacts, 0, group_names=group_names
        ).run_test() as pilot:
            await pilot.pause()
            screen = [
                s for s in pilot.app.screen_stack
                if isinstance(s, ContactDetailScreen)
            ][0]
            groups_label = screen.query_one("#detail-groups-label")
            groups_value = screen.query_one("#detail-groups")
            assert groups_label.display is True
            assert groups_value.display is True
            assert "Work Colleagues" in str(groups_value.render())

    @pytest.mark.asyncio
    async def test_groups_hidden_in_detail_when_only_system(self):
        """ContactDetailScreen hides groups when only system groups present."""
        contacts = [
            Contact(
                resource_name="people/d2",
                display_name="System Person",
                emails=["sys@example.com"],
                raw_json={
                    "memberships": [
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/myContacts"}},
                    ]
                },
            ),
        ]
        async with ContactDetailScreenTestApp(contacts, 0).run_test() as pilot:
            await pilot.pause()
            screen = [
                s for s in pilot.app.screen_stack
                if isinstance(s, ContactDetailScreen)
            ][0]
            groups_label = screen.query_one("#detail-groups-label")
            groups_value = screen.query_one("#detail-groups")
            assert groups_label.display is False
            assert groups_value.display is False

    @pytest.mark.asyncio
    async def test_groups_hidden_in_detail_when_no_memberships(self):
        """ContactDetailScreen hides groups when no memberships exist."""
        contacts = [
            Contact(
                resource_name="people/d3",
                display_name="No Groups Person",
                emails=["nogroups@example.com"],
                raw_json={},
            ),
        ]
        async with ContactDetailScreenTestApp(contacts, 0).run_test() as pilot:
            await pilot.pause()
            screen = [
                s for s in pilot.app.screen_stack
                if isinstance(s, ContactDetailScreen)
            ][0]
            groups_label = screen.query_one("#detail-groups-label")
            groups_value = screen.query_one("#detail-groups")
            assert groups_label.display is False
            assert groups_value.display is False

    @pytest.mark.asyncio
    async def test_groups_shows_multiple(self):
        """ContactDetailScreen shows multiple group names joined."""
        contacts = [
            Contact(
                resource_name="people/d4",
                display_name="Multi Group",
                emails=["multi@example.com"],
                raw_json={
                    "memberships": [
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/friends"}},
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/work"}},
                    ]
                },
            ),
        ]
        group_names = {
            "contactGroups/friends": "Friends",
            "contactGroups/work": "Work",
        }
        async with ContactDetailScreenTestApp(
            contacts, 0, group_names=group_names
        ).run_test() as pilot:
            await pilot.pause()
            screen = [
                s for s in pilot.app.screen_stack
                if isinstance(s, ContactDetailScreen)
            ][0]
            groups_value = screen.query_one("#detail-groups")
            rendered = str(groups_value.render())
            assert "Friends" in rendered
            assert "Work" in rendered

    @pytest.mark.asyncio
    async def test_groups_falls_back_to_resource_name(self):
        """ContactDetailScreen falls back to resource name when group_names mapping is empty."""
        contacts = [
            Contact(
                resource_name="people/d5",
                display_name="Unmapped Group",
                emails=["unmapped@example.com"],
                raw_json={
                    "memberships": [
                        {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/unknown123"}},
                    ]
                },
            ),
        ]
        async with ContactDetailScreenTestApp(
            contacts, 0, group_names={}
        ).run_test() as pilot:
            await pilot.pause()
            screen = [
                s for s in pilot.app.screen_stack
                if isinstance(s, ContactDetailScreen)
            ][0]
            groups_value = screen.query_one("#detail-groups")
            assert groups_value.display is True
            assert "contactGroups/unknown123" in str(groups_value.render())


class BatchViewTestApp(App):
    def __init__(self, db: ContactsDB):
        super().__init__()
        self.db = db
        self._undo_stack: list[tuple[str, Status]] = []

    def compose(self) -> ComposeResult:
        yield BatchView(db=self.db)


class TestBatchView:
    @pytest.mark.asyncio
    async def test_domain_tab_shows_domains(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            app = pilot.app
            batch = app.query_one(BatchView)
            domain_table = batch.domain_table
            assert domain_table.row_count >= 1

    @pytest.mark.asyncio
    async def test_sparse_tab_shows_categories(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            app = pilot.app
            batch = app.query_one(BatchView)
            batch.action_show_sparse()
            sparse_table = batch.sparse_table
            assert sparse_table is not None

    @pytest.mark.asyncio
    async def test_expand_shows_right_panel(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            panel = pilot.app.query_one(ExpandPanel)
            assert panel.display is True
            assert batch._expanded is True

    @pytest.mark.asyncio
    async def test_collapse_hides_right_panel(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            panel = pilot.app.query_one(ExpandPanel)
            assert panel.display is False
            assert batch._expanded is False

    @pytest.mark.asyncio
    async def test_expand_populates_contacts(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            panel = pilot.app.query_one(ExpandPanel)
            assert panel.contacts_table.row_count >= 1

    @pytest.mark.asyncio
    async def test_tab_switches_focus_to_right_panel(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("enter")  # expand
            await pilot.pause()
            assert batch._focus_panel == "right"
            await pilot.press("shift+tab")
            await pilot.pause()
            assert batch._focus_panel == "left"
            await pilot.press("tab")
            await pilot.pause()
            assert batch._focus_panel == "right"

    @pytest.mark.asyncio
    async def test_x_in_expand_trashes_individual(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("enter")  # expand
            await pilot.pause()
            panel = pilot.app.query_one(ExpandPanel)
            initial_count = panel.contacts_table.row_count
            await pilot.press("x")  # trash individual
            await pilot.pause()
            assert panel.contacts_table.row_count == initial_count - 1


class ExpandPanelTestApp(App):
    def __init__(self, db: ContactsDB):
        super().__init__()
        self.db = db
        self._undo_stack: list[tuple[str, Status]] = []

    def compose(self) -> ComposeResult:
        yield ExpandPanel(db=self.db)


class TestExpandPanel:
    @pytest.mark.asyncio
    async def test_load_contacts_populates_table(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            panel.load_contacts("example.com", [
                Contact(
                    resource_name="people/c1",
                    display_name="Alice Smith",
                    emails=["alice@example.com"],
                    phones=["555-0001"],
                ),
            ])
            await pilot.pause()
            assert panel.contacts_table.row_count == 1

    @pytest.mark.asyncio
    async def test_load_contacts_updates_header(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            panel.load_contacts("example.com", [
                Contact(resource_name="people/c1", display_name="Alice"),
            ])
            await pilot.pause()
            header = pilot.app.query_one("#expand-header", Static)
            assert "example.com" in str(header.render())

    @pytest.mark.asyncio
    async def test_load_contacts_filters_trashed(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            panel.load_contacts("example.com", [
                Contact(resource_name="people/c1", display_name="Alice", status=Status.UNMARKED),
                Contact(resource_name="people/c2", display_name="Bob", status=Status.TRASHED),
            ])
            await pilot.pause()
            assert panel.contacts_table.row_count == 1

    @pytest.mark.asyncio
    async def test_trash_contact(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            contact = db.get_contact("people/c1")
            assert contact.status == Status.TRASHED

    @pytest.mark.asyncio
    async def test_protect_contact(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("*")
            await pilot.pause()
            contact = db.get_contact("people/c1")
            assert contact.status == Status.PROTECTED

    @pytest.mark.asyncio
    async def test_undo_restores_status(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()
            contact = db.get_contact("people/c1")
            assert contact.status == Status.UNMARKED

    @pytest.mark.asyncio
    async def test_flush_posts_message(self, db):
        messages = []

        class CapturingApp(App):
            def __init__(self_app):
                super().__init__()
                self_app._undo_stack: list[tuple[str, Status]] = []

            def compose(self_app):
                yield ExpandPanel(db=db)

            def on_expand_panel_flush_requested(self_app, event):
                messages.append(event)

        async with CapturingApp().run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()
            assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_enter_opens_detail_screen(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            from gcontact_destroyer.views.expand_panel import ContactDetailScreen
            screens = [s for s in pilot.app.screen_stack if isinstance(s, ContactDetailScreen)]
            assert len(screens) == 1


class ProtectedViewTestApp(App):
    def __init__(self, db: ContactsDB):
        super().__init__()
        self.db = db
        self._undo_stack: list[tuple[str, Status]] = []

    def compose(self) -> ComposeResult:
        yield ProtectedView(db=self.db)


class TestProtectedView:
    @pytest.mark.asyncio
    async def test_shows_only_protected_contacts(self, db):
        async with ProtectedViewTestApp(db).run_test() as pilot:
            view = pilot.app.query_one(ProtectedView)
            table = view.table
            # db fixture has 1 protected contact (people/c3)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_vim_navigation_j_k(self, db):
        # Add a second protected contact
        db.upsert_contacts([
            Contact(
                resource_name="people/c4",
                display_name="Another Protected",
                emails=["ap@safe.com"],
                status=Status.PROTECTED,
            ),
        ])
        async with ProtectedViewTestApp(db).run_test() as pilot:
            view = pilot.app.query_one(ProtectedView)
            await pilot.pause()
            assert view.table.cursor_row == 0
            await pilot.press("j")
            await pilot.pause()
            assert view.table.cursor_row == 1
            await pilot.press("k")
            await pilot.pause()
            assert view.table.cursor_row == 0

    @pytest.mark.asyncio
    async def test_asterisk_unprotects_contact(self, db):
        async with ProtectedViewTestApp(db).run_test() as pilot:
            view = pilot.app.query_one(ProtectedView)
            await pilot.pause()
            await pilot.press("*")
            await pilot.pause()
            contact = db.get_contact("people/c3")
            assert contact.status == Status.UNMARKED
            assert view.table.row_count == 0

    @pytest.mark.asyncio
    async def test_x_trashes_contact(self, db):
        async with ProtectedViewTestApp(db).run_test() as pilot:
            view = pilot.app.query_one(ProtectedView)
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            contact = db.get_contact("people/c3")
            assert contact.status == Status.TRASHED
            assert view.table.row_count == 0

    @pytest.mark.asyncio
    async def test_undo_restores_unprotect(self, db):
        async with ProtectedViewTestApp(db).run_test() as pilot:
            view = pilot.app.query_one(ProtectedView)
            await pilot.pause()
            await pilot.press("*")
            await pilot.pause()
            assert view.table.row_count == 0
            await pilot.press("u")
            await pilot.pause()
            assert view.table.row_count == 1
            contact = db.get_contact("people/c3")
            assert contact.status == Status.PROTECTED

    @pytest.mark.asyncio
    async def test_undo_restores_trash(self, db):
        async with ProtectedViewTestApp(db).run_test() as pilot:
            view = pilot.app.query_one(ProtectedView)
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            assert view.table.row_count == 0
            await pilot.press("u")
            await pilot.pause()
            assert view.table.row_count == 1
            contact = db.get_contact("people/c3")
            assert contact.status == Status.PROTECTED

    @pytest.mark.asyncio
    async def test_shift_u_unprotects_all_visible(self, db):
        db.upsert_contacts([
            Contact(
                resource_name="people/c4",
                display_name="Another Protected",
                emails=["ap@safe.com"],
                status=Status.PROTECTED,
            ),
        ])
        async with ProtectedViewTestApp(db).run_test() as pilot:
            view = pilot.app.query_one(ProtectedView)
            await pilot.pause()
            assert view.table.row_count == 2
            await pilot.press("U")
            await pilot.pause()
            assert view.table.row_count == 0
            assert db.get_contact("people/c3").status == Status.UNMARKED
            assert db.get_contact("people/c4").status == Status.UNMARKED


@pytest.fixture
def trash_db(tmp_path):
    db_path = tmp_path / "trash_test.db"
    cdb = ContactsDB(db_path)
    cdb.upsert_contacts(
        [
            Contact(
                resource_name="people/t1",
                display_name="Trashed Alice",
                emails=["talice@example.com"],
                phones=["555-1001"],
                organizations=[{"name": "TrashCorp"}],
                etag="et1",
            ),
            Contact(
                resource_name="people/t2",
                display_name="Trashed Bob",
                emails=["tbob@example.com"],
                phones=["555-1002"],
                etag="et2",
            ),
            Contact(
                resource_name="people/t3",
                display_name="Unmarked Charlie",
                emails=["charlie@example.com"],
                etag="et3",
            ),
        ]
    )
    cdb.set_status("people/t1", Status.TRASHED)
    cdb.set_status("people/t2", Status.TRASHED)
    return cdb


class TrashViewTestApp(App):
    def __init__(self, db: ContactsDB):
        super().__init__()
        self.db = db
        self._undo_stack: list[tuple[str, Status]] = []

    def compose(self) -> ComposeResult:
        yield TrashView(db=self.db)


class TestTrashView:
    @pytest.mark.asyncio
    async def test_shows_only_trashed_contacts(self, trash_db):
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            table = view.table
            # trash_db fixture has 2 trashed contacts (people/t1, people/t2)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_vim_navigation_j_k(self, trash_db):
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            assert view.table.cursor_row == 0
            await pilot.press("j")
            await pilot.pause()
            assert view.table.cursor_row == 1
            await pilot.press("k")
            await pilot.pause()
            assert view.table.cursor_row == 0

    @pytest.mark.asyncio
    async def test_u_untrashes_selected(self, trash_db):
        """Pressing u directly un-trashes the selected contact."""
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            assert view.table.row_count == 2
            await pilot.press("u")
            await pilot.pause()
            contact = trash_db.get_contact("people/t1")
            assert contact.status == Status.UNMARKED
            assert view.table.row_count == 1

    @pytest.mark.asyncio
    async def test_z_undoes_untrash(self, trash_db):
        """Pressing z after un-trashing restores TRASHED status."""
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            await pilot.press("u")  # un-trash
            await pilot.pause()
            assert view.table.row_count == 1
            await pilot.press("z")  # undo
            await pilot.pause()
            assert view.table.row_count == 2
            restored = trash_db.get_contact("people/t1")
            assert restored.status == Status.TRASHED

    @pytest.mark.asyncio
    async def test_asterisk_protects_contact(self, trash_db):
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            await pilot.press("*")
            await pilot.pause()
            contact = trash_db.get_contact("people/t1")
            assert contact.status == Status.PROTECTED
            assert view.table.row_count == 1

    @pytest.mark.asyncio
    async def test_z_undoes_protect(self, trash_db):
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            await pilot.press("*")
            await pilot.pause()
            assert view.table.row_count == 1
            await pilot.press("z")  # undo
            await pilot.pause()
            assert view.table.row_count == 2
            contact = trash_db.get_contact("people/t1")
            assert contact.status == Status.TRASHED

    @pytest.mark.asyncio
    async def test_flush_posts_message(self, trash_db):
        messages = []

        class CapturingApp(App):
            def __init__(self_app):
                super().__init__()
                self_app._undo_stack: list[tuple[str, Status]] = []

            def compose(self_app):
                yield TrashView(db=trash_db)

            def on_trash_view_flush_requested(self_app, event):
                messages.append(event)

        async with CapturingApp().run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            view.table.focus()
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()
            assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_enter_opens_detail_screen(self, trash_db):
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            view.table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            from gcontact_destroyer.views.expand_panel import ContactDetailScreen
            screens = [s for s in pilot.app.screen_stack if isinstance(s, ContactDetailScreen)]
            assert len(screens) == 1

    @pytest.mark.asyncio
    async def test_protect_posts_keep_label_requested(self, trash_db):
        messages = []

        class CapturingApp(App):
            def __init__(self_app):
                super().__init__()
                self_app._undo_stack: list[tuple[str, Status]] = []

            def compose(self_app):
                yield TrashView(db=trash_db)

            def on_trash_view_keep_label_requested(self_app, event):
                messages.append(event)

        async with CapturingApp().run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            view.table.focus()
            await pilot.pause()
            await pilot.press("*")
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].resource_name == "people/t1"

    @pytest.mark.asyncio
    async def test_search_filters_contacts(self, trash_db):
        async with TrashViewTestApp(trash_db).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            assert view.table.row_count == 2
            # Activate search and type a query
            await pilot.press("slash")
            await pilot.pause()
            view.search_input.value = "Alice"
            view._search_query = "Alice"
            view.reload_contacts()
            await pilot.pause()
            assert view.table.row_count == 1

    @pytest.mark.asyncio
    async def test_empty_table_actions_safe(self, tmp_path):
        """Actions on empty trash view should not crash."""
        db_path = tmp_path / "empty.db"
        cdb = ContactsDB(db_path)
        cdb.upsert_contacts([
            Contact(
                resource_name="people/e1",
                display_name="Not Trashed",
                emails=["nottrashed@example.com"],
                etag="ee1",
            ),
        ])
        async with TrashViewTestApp(cdb).run_test() as pilot:
            view = pilot.app.query_one(TrashView)
            await pilot.pause()
            assert view.table.row_count == 0
            # These should not crash
            await pilot.press("*")
            await pilot.pause()
            await pilot.press("u")  # un-trash
            await pilot.pause()
            await pilot.press("z")  # undo
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()


class TestBatchCategoryTrashConfirmation:
    @pytest.mark.asyncio
    async def test_x_on_left_panel_shows_confirm(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            assert any(isinstance(s, ConfirmScreen) for s in pilot.app.screen_stack)

    @pytest.mark.asyncio
    async def test_x_confirm_y_trashes_category(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            # Get the first domain category contact
            contacts_before = db.get_contacts_by_domain("example.com")
            assert len(contacts_before) >= 1
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            # Contact should now be trashed
            contact = db.get_contact("people/c1")
            assert contact.status == Status.TRASHED

    @pytest.mark.asyncio
    async def test_x_confirm_n_does_not_trash(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            # Contact should still be unmarked
            contact = db.get_contact("people/c1")
            assert contact.status == Status.UNMARKED

    @pytest.mark.asyncio
    async def test_x_confirm_message_includes_count_and_category(self, db):
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            screen = [s for s in pilot.app.screen_stack if isinstance(s, ConfirmScreen)][0]
            msg = str(screen.query_one("#confirm-message").render())
            assert "example.com" in msg or "bigcorp.com" in msg

    @pytest.mark.asyncio
    async def test_x_in_right_panel_no_confirm(self, db):
        """Single-contact x in expanded right panel should not show confirmation."""
        async with BatchViewTestApp(db).run_test() as pilot:
            batch = pilot.app.query_one(BatchView)
            await pilot.pause()
            batch.domain_table.focus()
            await pilot.pause()
            await pilot.press("enter")  # expand
            await pilot.pause()
            panel = pilot.app.query_one(ExpandPanel)
            initial_count = panel.contacts_table.row_count
            await pilot.press("x")  # single-contact trash
            await pilot.pause()
            # Should NOT show confirm screen, should trash immediately
            assert not any(isinstance(s, ConfirmScreen) for s in pilot.app.screen_stack)
            assert panel.contacts_table.row_count == initial_count - 1


class TestExpandPanelTrashAllConfirmation:
    @pytest.mark.asyncio
    async def test_shift_x_shows_confirm(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("X")
            await pilot.pause()
            assert any(isinstance(s, ConfirmScreen) for s in pilot.app.screen_stack)

    @pytest.mark.asyncio
    async def test_shift_x_confirm_y_trashes_all(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("X")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            contact = db.get_contact("people/c1")
            assert contact.status == Status.TRASHED

    @pytest.mark.asyncio
    async def test_shift_x_confirm_n_does_not_trash(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("X")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            contact = db.get_contact("people/c1")
            assert contact.status == Status.UNMARKED

    @pytest.mark.asyncio
    async def test_shift_x_confirm_message_includes_count(self, db):
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("X")
            await pilot.pause()
            screen = [s for s in pilot.app.screen_stack if isinstance(s, ConfirmScreen)][0]
            msg = str(screen.query_one("#confirm-message").render())
            assert "1" in msg
            assert "visible" in msg

    @pytest.mark.asyncio
    async def test_shift_x_on_empty_panel_no_confirm(self, db):
        """Trash-all-visible on empty panel should not show confirmation."""
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            panel.load_contacts("empty", [])
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("X")
            await pilot.pause()
            assert not any(isinstance(s, ConfirmScreen) for s in pilot.app.screen_stack)

    @pytest.mark.asyncio
    async def test_single_x_no_confirm(self, db):
        """Single-contact x should NOT show confirmation."""
        async with ExpandPanelTestApp(db).run_test() as pilot:
            panel = pilot.app.query_one(ExpandPanel)
            contacts = db.get_contacts_by_domain("example.com")
            panel.load_contacts("example.com", contacts)
            await pilot.pause()
            panel.contacts_table.focus()
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            assert not any(isinstance(s, ConfirmScreen) for s in pilot.app.screen_stack)
            contact = db.get_contact("people/c1")
            assert contact.status == Status.TRASHED


class TestSharedUndoStack:
    """Tests for undo stack persistence across view switches."""

    @pytest.fixture
    def shared_db(self, tmp_path):
        db_path = tmp_path / "shared_undo.db"
        cdb = ContactsDB(db_path)
        cdb.upsert_contacts([
            Contact(
                resource_name="people/s1",
                display_name="Shared Alice",
                emails=["salice@example.com"],
                phones=["555-0001"],
                etag="es1",
            ),
            Contact(
                resource_name="people/s2",
                display_name="Shared Bob",
                emails=["sbob@example.com"],
                phones=["555-0002"],
                etag="es2",
            ),
            Contact(
                resource_name="people/s3",
                display_name="Shared Protected",
                emails=["sprotected@safe.com"],
                etag="es3",
            ),
        ])
        cdb.set_status("people/s3", Status.PROTECTED)
        return cdb

    @pytest.fixture
    def shared_app(self, shared_db, tmp_path):
        from gcontact_destroyer.app import GContactDestroyer
        return GContactDestroyer(db_path=shared_db.db_path)

    @pytest.mark.asyncio
    async def test_undo_within_list_view_still_works(self, shared_app):
        """Undo within a single view still works (existing behavior preserved)."""
        async with shared_app.run_test() as pilot:
            await pilot.pause()
            list_view = shared_app.query_one("#list-view", ListView)
            list_view.table.focus()
            await pilot.pause()
            # Trash the first contact
            first_contact = list_view._contacts[0].resource_name
            await pilot.press("x")
            await pilot.pause()
            contact = shared_app.db.get_contact(first_contact)
            assert contact.status == Status.TRASHED
            # Undo should restore it
            await pilot.press("u")
            await pilot.pause()
            contact = shared_app.db.get_contact(first_contact)
            assert contact.status == Status.UNMARKED

    @pytest.mark.asyncio
    async def test_undo_persists_across_view_switch(self, shared_app):
        """Trash in list view, switch to protected view, undo still restores."""
        async with shared_app.run_test() as pilot:
            await pilot.pause()
            list_view = shared_app.query_one("#list-view", ListView)
            list_view.table.focus()
            await pilot.pause()
            first_contact = list_view._contacts[0].resource_name
            # Trash a contact in list view
            await pilot.press("x")
            await pilot.pause()
            assert shared_app.db.get_contact(first_contact).status == Status.TRASHED
            assert len(shared_app._undo_stack) == 1
            # Switch to protected view
            await pilot.press("3")
            await pilot.pause()
            # Stack should still have the entry
            assert len(shared_app._undo_stack) == 1
            # Undo from protected view
            await pilot.press("u")
            await pilot.pause()
            contact = shared_app.db.get_contact(first_contact)
            assert contact.status == Status.UNMARKED
            assert len(shared_app._undo_stack) == 0

    @pytest.mark.asyncio
    async def test_stack_shared_trash_in_list_undo_in_trash_view(self, shared_app):
        """Trash in list view, switch to trash view, undo restores the contact."""
        async with shared_app.run_test() as pilot:
            await pilot.pause()
            list_view = shared_app.query_one("#list-view", ListView)
            list_view.table.focus()
            await pilot.pause()
            first_contact = list_view._contacts[0].resource_name
            await pilot.press("x")
            await pilot.pause()
            assert shared_app.db.get_contact(first_contact).status == Status.TRASHED
            # Switch to trash view
            await pilot.press("4")
            await pilot.pause()
            # Undo from trash view (uses 'z' binding)
            await pilot.press("z")
            await pilot.pause()
            contact = shared_app.db.get_contact(first_contact)
            assert contact.status == Status.UNMARKED

    @pytest.mark.asyncio
    async def test_multiple_undos_across_views(self, shared_app):
        """Multiple operations across views all stack correctly."""
        async with shared_app.run_test() as pilot:
            await pilot.pause()
            list_view = shared_app.query_one("#list-view", ListView)
            list_view.table.focus()
            await pilot.pause()
            first_contact = list_view._contacts[0].resource_name
            second_contact = list_view._contacts[1].resource_name
            # Trash first contact
            await pilot.press("x")
            await pilot.pause()
            # Trash second contact
            await pilot.press("x")
            await pilot.pause()
            assert len(shared_app._undo_stack) == 2
            # Switch to protected view
            await pilot.press("3")
            await pilot.pause()
            # Undo last action (second contact)
            await pilot.press("u")
            await pilot.pause()
            assert shared_app.db.get_contact(second_contact).status == Status.UNMARKED
            assert shared_app.db.get_contact(first_contact).status == Status.TRASHED
            # Switch back to list view
            await pilot.press("1")
            await pilot.pause()
            # Undo first action (first contact)
            await pilot.press("u")
            await pilot.pause()
            assert shared_app.db.get_contact(first_contact).status == Status.UNMARKED
            assert len(shared_app._undo_stack) == 0

    @pytest.mark.asyncio
    async def test_app_starts_with_empty_undo_stack(self, shared_app):
        """App should initialize with an empty undo stack."""
        assert shared_app._undo_stack == []
        async with shared_app.run_test() as pilot:
            await pilot.pause()
            assert shared_app._undo_stack == []

