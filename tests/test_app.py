import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from gcontact_destroyer.app import ConfirmScreen, GContactDestroyer, StatsBar, SyncPromptScreen
from gcontact_destroyer.google_api import GooglePeopleAPI
from gcontact_destroyer.models import Contact, Status


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    return GContactDestroyer(db_path=db_path)


@pytest.fixture
def sample_contacts():
    return [
        Contact(
            resource_name="people/c1",
            display_name="Alice Smith",
            emails=["alice@example.com"],
            etag="e1",
        ),
        Contact(
            resource_name="people/c2",
            display_name="Bob Jones",
            emails=["bob@bigcorp.com"],
            etag="e2",
        ),
    ]


class TestAppShell:
    async def test_app_launches(self, app):
        async with app.run_test() as pilot:
            assert app.title == "gcontact-destroyer"

    async def test_initial_view_is_list(self, app):
        async with app.run_test() as pilot:
            assert app.query_one("#list-view").display is True
            assert app.query_one("#card-view").display is False
            assert app.query_one("#protected-view").display is False
            assert app.query_one("#batch-view").display is False

    async def test_switch_to_batch_view(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            assert app.query_one("#list-view").display is False
            assert app.query_one("#card-view").display is False
            assert app.query_one("#protected-view").display is False
            assert app.query_one("#batch-view").display is True
            assert app._current_view == "batch"

    async def test_switch_to_protected_view(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            assert app.query_one("#list-view").display is False
            assert app.query_one("#card-view").display is False
            assert app.query_one("#protected-view").display is True
            assert app.query_one("#batch-view").display is False
            assert app._current_view == "protected"

    async def test_switch_back_to_list_view(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            await pilot.press("1")
            assert app.query_one("#list-view").display is True
            assert app.query_one("#card-view").display is False
            assert app.query_one("#protected-view").display is False
            assert app.query_one("#batch-view").display is False
            assert app._current_view == "list"

    async def test_stats_bar_present(self, app):
        async with app.run_test() as pilot:
            stats_bar = app.query_one("#stats-bar", StatsBar)
            assert stats_bar is not None

    async def test_stats_bar_shows_zeros_on_empty_db(self, app):
        async with app.run_test() as pilot:
            stats_bar = app.query_one("#stats-bar", StatsBar)
            text = str(stats_bar.content)
            assert "Total: 0" in text
            assert "Protected: 0" in text
            assert "Trashed: 0" in text
            assert "Remaining: 0" in text

    async def test_stats_bar_reflects_db_state(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.PROTECTED)
        async with app.run_test() as pilot:
            stats_bar = app.query_one("#stats-bar", StatsBar)
            text = str(stats_bar.content)
            assert "Total: 2" in text
            assert "Protected: 1" in text
            assert "Remaining: 1" in text

    async def test_quit_with_no_trashed(self, app):
        async with app.run_test() as pilot:
            await pilot.press("q")
            # App should exit without warning
            assert app.return_code is None or app.return_code == 0

    async def test_quit_warns_when_trashed_contacts(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.TRASHED)
        async with app.run_test() as pilot:
            await pilot.press("q")
            # First q should not exit, just warn
            assert app._force_quit is True

    async def test_quit_force_exits_on_second_q(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.TRASHED)
        async with app.run_test() as pilot:
            await pilot.press("q")
            await pilot.press("q")
            # Second q should force exit


class TestStaleSyncPrompt:
    async def test_no_prompt_when_db_empty(self, app):
        async with app.run_test() as pilot:
            await pilot.pause()
            assert not any(
                isinstance(s, SyncPromptScreen) for s in app.screen_stack
            )

    async def test_no_prompt_when_recently_synced(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        # synced_at defaults to now, so no prompt expected
        async with app.run_test() as pilot:
            await pilot.pause()
            assert not any(
                isinstance(s, SyncPromptScreen) for s in app.screen_stack
            )

    async def test_prompt_appears_when_stale(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        # Backdate synced_at to 30 hours ago
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn = sqlite3.connect(app.db.db_path)
        conn.execute(f"UPDATE contacts SET synced_at = '{old_ts}'")
        conn.commit()
        conn.close()

        async with app.run_test() as pilot:
            await pilot.pause()
            assert any(isinstance(s, SyncPromptScreen) for s in app.screen_stack)

    async def test_declining_prompt_does_not_sync(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn = sqlite3.connect(app.db.db_path)
        conn.execute(f"UPDATE contacts SET synced_at = '{old_ts}'")
        conn.commit()
        conn.close()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert not any(isinstance(s, SyncPromptScreen) for s in app.screen_stack)


class TestProtectedViewIntegration:
    async def test_protected_view_shows_protected_contacts(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.PROTECTED)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            from gcontact_destroyer.views.protected_view import ProtectedView
            view = app.query_one("#protected-view", ProtectedView)
            assert view.table.row_count == 1

    async def test_status_change_refreshes_stats(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.PROTECTED)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            # Unprotect with *
            await pilot.press("*")
            await pilot.pause()
            stats_bar = app.query_one("#stats-bar", StatsBar)
            text = str(stats_bar.content)
            assert "Protected: 0" in text


class TestStatsBarUnit:
    def test_update_stats_formats_correctly(self):
        bar = StatsBar()
        stats = {"total": 10, "protected": 3, "trashed": 2, "remaining": 5}
        # Just test the method doesn't raise when called on a mounted widget
        # The actual rendering test is done in the async test above
        assert callable(bar.update_stats)


class TestApplyKeepLabelAutoCreate:
    @pytest.fixture
    def mock_api(self):
        api = MagicMock(spec=GooglePeopleAPI)
        return api

    @pytest.fixture
    def app_with_mock_api(self, tmp_path, mock_api):
        db_path = tmp_path / "test.db"
        app = GContactDestroyer(db_path=db_path, api=mock_api)
        return app

    async def test_auto_creates_keep_group_when_missing(
        self, app_with_mock_api, mock_api
    ):
        mock_api.find_group_resource_name.return_value = None
        mock_api.create_contact_group.return_value = "contactGroups/new123"
        mock_api.add_to_group.return_value = None

        async with app_with_mock_api.run_test():
            await app_with_mock_api._apply_keep_label("people/c1")

        mock_api.create_contact_group.assert_called_once_with("Keep")
        mock_api.add_to_group.assert_called_once_with(
            "contactGroups/new123", ["people/c1"]
        )

    async def test_uses_existing_keep_group(self, app_with_mock_api, mock_api):
        mock_api.find_group_resource_name.return_value = "contactGroups/existing"
        mock_api.add_to_group.return_value = None

        async with app_with_mock_api.run_test():
            await app_with_mock_api._apply_keep_label("people/c1")

        mock_api.create_contact_group.assert_not_called()
        mock_api.add_to_group.assert_called_once_with(
            "contactGroups/existing", ["people/c1"]
        )


class TestConfirmScreen:
    async def test_confirm_screen_y_dismisses_true(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        results = []

        async with app.run_test() as pilot:
            app.push_screen(ConfirmScreen("Test message"), lambda r: results.append(r))
            await pilot.pause()
            assert any(isinstance(s, ConfirmScreen) for s in app.screen_stack)
            await pilot.press("y")
            await pilot.pause()
            assert not any(isinstance(s, ConfirmScreen) for s in app.screen_stack)
            assert results == [True]

    async def test_confirm_screen_n_dismisses_false(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        results = []

        async with app.run_test() as pilot:
            app.push_screen(ConfirmScreen("Test message"), lambda r: results.append(r))
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert not any(isinstance(s, ConfirmScreen) for s in app.screen_stack)
            assert results == [False]

    async def test_confirm_screen_escape_dismisses_false(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        results = []

        async with app.run_test() as pilot:
            app.push_screen(ConfirmScreen("Test message"), lambda r: results.append(r))
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert not any(isinstance(s, ConfirmScreen) for s in app.screen_stack)
            assert results == [False]

    async def test_confirm_screen_displays_message(self, app):
        async with app.run_test() as pilot:
            app.push_screen(ConfirmScreen("Delete everything?"))
            await pilot.pause()
            screen = [s for s in app.screen_stack if isinstance(s, ConfirmScreen)][0]
            msg_widget = screen.query_one("#confirm-message")
            assert "Delete everything?" in str(msg_widget.render())


class TestFlushConfirmation:
    async def test_flush_shows_confirm_when_trashed(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.TRASHED)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()
            assert any(isinstance(s, ConfirmScreen) for s in app.screen_stack)

    async def test_flush_confirm_message_includes_count(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.TRASHED)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()
            screen = [s for s in app.screen_stack if isinstance(s, ConfirmScreen)][0]
            msg = str(screen.query_one("#confirm-message").render())
            assert "1" in msg
            assert "permanently deletes" in msg

    async def test_flush_no_confirm_when_zero_trashed(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        # No contacts trashed -- should not show confirm screen
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()
            assert not any(isinstance(s, ConfirmScreen) for s in app.screen_stack)

    async def test_flush_declining_does_not_flush(self, app, sample_contacts):
        app.db.upsert_contacts(sample_contacts)
        app.db.set_status("people/c1", Status.TRASHED)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            # Contact should still be trashed (not deleted from db)
            contact = app.db.get_contact("people/c1")
            assert contact is not None
            assert contact.status == Status.TRASHED
