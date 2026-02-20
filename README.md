# gcontact-destroyer

## Why I Built This

Over many years, phones, email accounts and employers, my Contacts database in my personal Google account had become hopelessly polluted. I had over 3,000 contacts and acquaintances. I wanted to strip things down to just "friends and family".

The Google Contacts UI is not helpful for this kind of task.

I could have exported the entire contact list to CSV or some other format, wiped out the online version and reimported the ones I care about.

But I decided to build this tool instead.

## What Is It?

A keyboard-driven TUI for rapidly purging Google Contacts.

Built with [Textual](https://textual.textualize.io/), gcontact-destroyer syncs your contacts to a local SQLite database so you can review, trash, and protect contacts quickly, then batch-flush deletions to Google when you're ready.

Deleted contacts land in Google Contacts trash and stay recoverable for at least 30 days, so there's little risk of permanent data loss.

## Disclaimer

This project was 100% vibe-coded with [Claude Code](https://claude.ai/). The author takes no responsibility for any damage this application does to your contacts. Use at your own risk. That said, deleted contacts go to Google's trash and are recoverable for 30 days, so the blast radius is limited.

## Before You Start

This app talks directly to the Google People API using OAuth, which means you need to set up your own Google Cloud project before it will do anything. That involves creating a project in the Google Cloud Console, enabling the People API, configuring an OAuth consent screen, and downloading a credentials JSON file. If you've never done this before, expect to spend 10-15 minutes clicking through Google's setup wizards. The full walkthrough is in [Google Cloud Setup](docs/google-setup.md).

If that sounds like too much, this tool probably isn't for you. There's no way around it since Google doesn't offer a simpler path for personal API access.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A Google Cloud project with OAuth credentials (see above)

## Install

```bash
git clone <repo-url>
cd gcontact-destroyer
uv sync
```

## Quick Start

```bash
# First run: syncs contacts from Google (opens browser for OAuth)
gcd --sync

# Subsequent runs: uses cached local database
gcd
```

Run `gcd --sync` again any time you want to refresh from Google.

## Typical Use

You've got 2,000 Google Contacts accumulated over fifteen years and most of them are strangers. Here's how a cleanup session goes:

1. Run `gcd --sync`. The app pulls your contacts and drops you into List View, a scrollable table of names, emails, phones, and orgs.

2. Scroll with `j`/`k` and press `*` on contacts you want to keep. This marks them as protected and adds them to a "Keep" group in Google Contacts. Use `/` to search by name or email if you're looking for someone specific.

3. Press `x` on contacts you don't recognize. Accidentally trash someone? Press `u` to undo (undo is in-memory and per-view, so it won't survive switching views or quitting). Want more detail before deciding? Press `Enter` to open the Card View, where you can see all emails, phones, orgs, and notes. Press `s` to search their email in Gmail and see if you've ever actually talked to them.

4. Press `2` to switch to Batch View. The "By Domain" tab groups contacts by email domain. If you've got 80 contacts from a company you left in 2014, press `x` to trash the whole domain at once. Press `Enter` to expand a domain first and cherry-pick individuals.

5. Switch to the "Sparse Contacts" tab to find contacts with missing names, no email, or no phone. The "By Label" tab groups by your existing Google contact labels.

6. Press `3` for Protected View to see everything you've marked as keep. Change your mind? Press `*` to unprotect, or `x` to trash.

7. Press `f` from any view to flush. This batch-deletes all trashed contacts from Google. They land in Google Contacts trash and are recoverable for 30 days. If you quit with unflushed changes, the app warns you.

Nothing is permanent until you flush, and even then Google gives you 30 days to recover anything you regret.

## Views

### List View (default)

Full-width table of all contacts with vim-style navigation.

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up |
| `/` | Search contacts |
| `x` | Trash selected contact |
| `X` | Trash all visible contacts |
| `*` | Protect selected contact (adds to "Keep" group) |
| `u` | Undo last status change (in-memory, current view only) |
| `Enter` | Open contact detail card |
| `f` | Flush: delete trashed contacts from Google |
| `2` | Switch to Batch View |

### Card View

Full contact details for a single contact. Open it by pressing `Enter` on any contact in List View.

| Key | Action |
|-----|--------|
| `n` / `j` / `l` | Next contact |
| `h` / `k` | Previous contact |
| `x` | Trash |
| `*` | Protect |
| `u` | Undo |
| `s` | Search contact in Gmail |
| `Escape` | Back to List View |

### Batch View

Bulk operations across three tabs: **By Domain**, **Sparse Contacts**, and **By Label**.

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Switch between category list and expanded contacts |
| `Enter` | Expand a category to see individual contacts |
| `x` | Trash entire category or individual contact |
| `X` | Trash all contacts in expanded view |
| `*` | Protect |
| `u` | Undo |
| `f` | Flush |
| `1` | Switch to List View |

## How It Works

Contacts are fetched from the Google People API and stored locally in a SQLite database. You mark contacts as trashed or protected, but nothing touches Google until you explicitly flush. Trashed contacts are batch-deleted from Google; protected contacts are added to a "Keep" contact group. Deleted contacts stay in Google's trash for at least 30 days, so you can recover them at any time by visiting [Google Contacts](https://contacts.google.com/) and checking the Trash.

## Data Storage

Where `~` is your home directory (`$HOME` on macOS/Linux, `%USERPROFILE%` on Windows):

| Path | Purpose |
|------|---------|
| `~/.config/gcontact-destroyer/credentials.json` | Your Google OAuth credentials |
| `~/.local/share/gcontact-destroyer/contacts.db` | SQLite database with synced contacts |
| `~/.local/share/gcontact-destroyer/token.json` | Cached OAuth token (auto-refreshes) |

## License

MIT
