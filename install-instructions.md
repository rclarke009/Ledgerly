# Ledgerly — Install instructions

**First-time startup can take a long time** (many gigabytes of downloads). That’s normal—see **[How long startup takes](#how-long-startup-takes-normal-not-broken)** before your first launch.

Follow these steps once. After that, you’ll start Ledgerly from the desktop shortcut.

## Before you start

- **Windows 10 or 11**
- **Docker Desktop** installed and running  
  - If you’re not sure: look for the Docker icon in the system tray (bottom-right). If it’s there and not grayed out, you’re good.  
  - If you don’t have it: install from [docker.com](https://www.docker.com/products/docker-desktop/), then restart the PC if it asks you to.

---

## Step 1: Get the portable ZIP

You should have **Ledgerly-Portable.zip** (from a download, USB stick, or email).

---

## Step 2: Unzip it

1. Right-click **Ledgerly-Portable.zip**.
2. Click **Extract All…**.
3. Choose a place (e.g. **Desktop** or **Downloads**) and click **Extract**.
4. You’ll get a new folder named **Ledgerly** with several files inside, including **Setup.bat**, **Start.bat**, **starting.html** (startup progress page), **Check-Ledgerly.bat** (troubleshooting), **Backup.bat** (optional database backup), and this file (**install-instructions.md**).

---

## Step 3: Run the installer once

1. Open the **Ledgerly** folder.
2. Double-click **Setup.bat**.
3. A black window will open and copy files. When it says installation is complete and a **Ledgerly** shortcut is on your desktop, you’re done.
4. On first install, **Setup.bat** creates a **`.env`** file with cool/quiet defaults for this PC (smaller AI models, slower but gentler on the fan). You can close that window. You can also delete the **Ledgerly** folder you just unzipped if you like; the app is now installed under `%LocalAppData%\Ledgerly`.

---

## How long startup takes (normal, not broken)

Ledgerly uses **Docker** to run several parts on your PC: a small database, the **Ledgerly** web app, and **Ollama** (the local AI that powers **Ask** and document search). The first time you start—or the first time after Docker’s data was cleared—you may wait a **long** time. That is expected.

| Situation | What’s happening | Typical time |
|-----------|-------------------|--------------|
| **First start on this PC** (or after resetting Docker volumes) | Docker may **download container images**. The startup step then **downloads three AI models** (text, embeddings, and vision). Together this is **many gigabytes**. | Often **about 15–45+ minutes** on a home connection; slower Wi‑Fi or internet can take **longer**. It can look idle; that’s normal while files download. |
| **Later starts** (you’ve run Ledgerly successfully before) | Images and models are already on disk. Docker just **starts** the containers and checks that the models exist. | Often **about 1–3 minutes** until the window says **Ready** and the browser can open **http://localhost:8000/**. |
| **First question right after startup** | The AI **loads a model into memory** the first time it’s needed. | An extra **30 seconds to a few minutes** is normal; later questions in the same session usually feel faster. |

**Tips**

- Leave the **black window** open until it says **Ready** (or shows an error you can read). Closing it too early can stop the stack.
- Your browser opens a **Starting Ledgerly** page (`starting.html`) right away. It shows elapsed time and opens the app automatically when ready—**first start may take 30+ minutes**; that page is normal.
- Watch the **black window** for Docker image and AI model download progress (numbered steps 1–7).
- **Docker must be running** before you double-click the shortcut (whale icon in the system tray, not grayed out).
- Your data and downloaded models stay in Docker’s storage on this computer—you **don’t** re-download everything every day unless someone removed Docker volumes or reinstalled from scratch.

For developers or manual Docker use, see **setup_and_testing.md** in the same folder.

---

## Step 4: Start Ledgerly

1. Make sure **Docker is running** (Docker icon in the system tray).
2. Double-click the **Ledgerly** shortcut on your desktop (or **Start.bat** in `%LocalAppData%\Ledgerly`).
3. Two things open:
   - A **black window** with numbered steps (Docker images, AI models, etc.) — **leave it open**.
   - A browser tab titled **Starting Ledgerly…** — it counts elapsed time and opens **http://localhost:8000/** automatically when ready.
4. **Read [How long startup takes](#how-long-startup-takes-normal-not-broken)** above so you know what to expect—especially the **first** time (often **30+ minutes**). When the black window says **LEDGERLY IS READY** and the browser shows the app, you’re in. Open **How to use** in the app for a short guide, or read **instructions.md** in the install folder.

---

## To stop Ledgerly

- Close the black window that opened when you started the stack, **or**
- Open **File Explorer**, go to the address bar, type `%LocalAppData%\Ledgerly`, press Enter, open a Command Prompt in that folder, and run: `docker compose down`.

---

## Upgrading from an older install (finelly database credentials)

Older Ledgerly builds used Docker Postgres user/database name **`finelly`**. Current builds use **`ledgerly`**. If you upgrade in place, Postgres may fail to start against the old volume.

**Before upgrading:** run **Backup.bat** (or the manual backup steps below) while the old stack still runs.

Then from `%LocalAppData%\Ledgerly`:

```text
docker compose down -v
docker compose up -d
```

The `-v` flag removes the old Postgres volume so Docker creates a fresh **`ledgerly`** database. To reproduce your data, restore from your `.dump` file (see **Restoring on a new or reset PC** below).

---

## Back up your data (before an upgrade or a new PC)

Your **documents and Ask history** live in the **Postgres** database inside Docker. Models and big downloads are separate; this backup is **only the database** (compact and easy to move).

**When to do it:** Before a Ledgerly update, before reinstalling Docker, or any time you want a safety copy.

**Requirements:** **Docker running**, and Ledgerly **started once** so the database exists (black window can still say **Ready**—that’s fine).

### Easy way: Backup.bat

1. Open **File Explorer** and go to: `%LocalAppData%\Ledgerly`
2. Double-click **Backup.bat**
3. When it finishes, you’ll get a file on your **Desktop** named like `ledgerly-backup-20260506-143022.dump`
4. Copy that file somewhere safe (cloud folder, USB drive, another PC)

If the script says Postgres isn’t running, start Ledgerly from the desktop shortcut, wait until **Ready**, then run **Backup.bat** again.

### Manual way (Command Prompt)

1. Open **File Explorer** → address bar → type `%LocalAppData%\Ledgerly` → Enter
2. Click in the folder’s empty space, hold **Shift**, right‑click → **Open in Terminal** or **Open PowerShell window here** (or open Command Prompt and run `cd /d %LocalAppData%\Ledgerly`)
3. Run:

```text
docker compose exec -T postgres pg_dump -U ledgerly -d ledgerly -Fc -f /tmp/ledgerly-backup.dump
docker compose cp postgres:/tmp/ledgerly-backup.dump .\ledgerly-backup.dump
docker compose exec -T postgres rm -f /tmp/ledgerly-backup.dump
```

4. Move **`ledgerly-backup.dump`** from that folder to a safe place.

### Restoring on a new or reset PC (short outline)

1. Install Ledgerly and **start it once** so Docker creates the database.
2. Copy your **`.dump`** file into `%LocalAppData%\Ledgerly`
3. Open a terminal in that folder and run:

```text
docker compose cp .\ledgerly-backup.dump postgres:/tmp/ledgerly-restore.dump
docker compose exec -T postgres pg_restore -U ledgerly -d ledgerly --clean --if-exists /tmp/ledgerly-restore.dump
```

4. Restart Ledgerly (**To stop Ledgerly**, then start from the shortcut again). If anything errors, walk through the steps with your support contact.

If **pg_restore** says another program is using the database, fully stop the stack (**close the Ledgerly start window** or run `docker compose down` from `%LocalAppData%\Ledgerly`), then start only Postgres (`docker compose up -d postgres`), wait about 10 seconds, run the two **restore** lines again, then start Ledgerly from the desktop shortcut as usual.

**Developers** using SQLite only or a remote database (e.g. Supabase) should use **setup_and_testing.md** instead—those setups use different backup steps.

---

## If something goes wrong

- **Nothing seems to work and you’re not sure why**  
  → Double-click **Check-Ledgerly.bat** (in the **Ledgerly** folder or in `%LocalAppData%\Ledgerly`). It checks install paths, Docker, containers, and the web app, shows clear **[OK]** / **[WARNING]** / **[FAILED]** lines, and saves **ledgerly-diagnose.txt** on your **Desktop** to send to support.

- **“Docker is not running”** or the shortcut does nothing useful  
  → Start **Docker Desktop** from the Start menu and wait until its icon in the system tray shows it’s running. Try the shortcut again.

- **The black window closes too fast**  
  → Run **Setup.bat** again from the unzipped **Ledgerly** folder or from `%LocalAppData%\Ledgerly`. It’s safe to run more than once.

- **No desktop shortcut**  
  → Press **Win+R**, paste `%LocalAppData%\Ledgerly`, press **Enter**, then double-click **Start.bat**. Or run **Check-Ledgerly.bat** for step-by-step hints.

- **Browser doesn’t open or the page doesn’t load**  
  → Wait a minute and open your browser yourself. Go to: **http://localhost:8000/**  
  → Run **Check-Ledgerly.bat** to see whether the app is actually running.

---

*Ledgerly runs on your PC. Your data stays in Docker on this computer unless you change settings.*

---

## Optional: live stock quotes (Finnhub)

If you add **`FINNHUB_API_KEY`** to your `.env` in the installed folder (get a free key at [finnhub.io](https://finnhub.io/register)) and restart with Docker, the app can show current prices when you ask in **Ask**. Compound-interest math works without any API key.
