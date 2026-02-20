# Google Cloud Setup for gcontact-destroyer

## 1. Create a Google Cloud Project

1. Go to <https://console.cloud.google.com/>
2. Click "Select a project" > "New Project"
3. Name it "gcontact-destroyer" (or anything)
4. Click "Create"

## 2. Enable the People API

1. Go to <https://console.cloud.google.com/apis/library>
2. Search for "People API"
3. Click "Google People API" > "Enable"

## 3. Create OAuth Credentials

1. Go to <https://console.cloud.google.com/apis/credentials>
2. Click "Create Credentials" > "OAuth client ID"
3. If prompted to configure consent screen:
   - Choose "External" user type
   - Fill in app name: "gcontact-destroyer"
   - Add your email as test user
   - Add scope: `https://www.googleapis.com/auth/contacts`
4. Application type: "Desktop app"
5. Name: "gcontact-destroyer"
6. Click "Create"
7. Download the JSON file
8. Rename it to `credentials.json`
9. Place it at `~/.config/gcontact-destroyer/credentials.json`

   **macOS / Linux:**
   ```bash
   mkdir -p ~/.config/gcontact-destroyer
   mv ~/Downloads/client_secret_*.json ~/.config/gcontact-destroyer/credentials.json
   ```

   **Windows (PowerShell):**
   ```powershell
   mkdir -Force "$HOME\.config\gcontact-destroyer"
   mv "$HOME\Downloads\client_secret_*.json" "$HOME\.config\gcontact-destroyer\credentials.json"
   ```

## 4. First Run

```bash
gcd --sync
```

This opens your browser for Google sign-in. After authorization, contacts sync to the local database.

## 5. Subsequent Runs

```bash
gcd
```

Uses cached contacts. Run with `--sync` again to refresh.
