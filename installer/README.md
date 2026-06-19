# Ledgerly Windows Installer

Two ways to give Ledgerly to someone (e.g. your dad). **Docker Desktop must already be installed** on the target PC.

- **Portable ZIP (Docker-only build)** – No Inno Setup. You build a ZIP with a script that only needs Docker. He unzips and runs `Setup.bat` once.
- **Inno Setup .exe** – Single installer executable; requires Inno Setup 6 on your machine to build.

---

## Option A: Portable ZIP (build with Docker only)

You only need Docker to build. No Inno Setup.

### Build the ZIP

**Mac/Linux** (from project root):
```bash
./installer/build-portable.sh
```

**Windows** (from project root or from `installer`):
```bat
installer\build-portable.bat
```

**Without Docker** (Python 3 only; same zip layout as the scripts above):

```bash
python3 installer/build_portable_zip.py
```

Output: **`installer/output/Ledgerly-Portable.zip`**

### Give it to your dad

1. Send him **Ledgerly-Portable.zip**
2. He unzips it (e.g. to Desktop or Downloads). He’ll get a folder **Ledgerly** with `Setup.bat`, `Start.bat`, **install-instructions.md**, etc. inside. Point him at **install-instructions.md** first—it explains **how long the first startup can take** (large downloads are normal) vs later starts.
3. He double-clicks **Setup.bat** once. It copies Ledgerly to `%LocalAppData%\Ledgerly` and creates a **Ledgerly** shortcut on the desktop.
4. He can delete the unzipped folder if he likes. To start Ledgerly: double-click the desktop shortcut (Docker must be running).

To stop: open a terminal in `%LocalAppData%\Ledgerly` and run `docker compose down`, or we could add a Stop Ledgerly shortcut later.

The Docker stack includes **internal Postgres + pgvector** (no DB port exposed on the PC — only the Ledgerly container talks to it). Your dad does not need Supabase CLI or a separate database install.

### Target PC (Dad's Dell XPS 15 9530)

Hardware and cool/quiet **`.env`** defaults: [`docs/target-pc-dad-xps15.md`](../docs/target-pc-dad-xps15.md).

The portable ZIP includes **`.env.portable-xps15.example`**. **`Setup.bat`** copies it to **`.env`** on first install (when no `.env` exists yet). **`Start.bat`** auto-detects **`OLLAMA_NUM_THREADS`** when unset (same conservative formula as `start.sh`) and pulls **`qwen2.5:3b`** + **`moondream`** when **`LEDGERLY_PROFILE=portable`** is in `.env`.

---

## Option B: Inno Setup .exe installer

### What the installer does

- Copies the Ledgerly app (all files under the project root, except `.env`, `.git`, `__pycache__`, `.venv`, and this `installer/` folder) to `%LocalAppData%\Ledgerly`.
- Creates Start Menu entries: **Ledgerly** (start), **Stop Ledgerly** (run `docker compose down`), and Uninstall.
- Optionally creates a desktop shortcut and a “Start Ledgerly now” step at the end of setup.
- No administrator rights required (installs to user’s AppData).

### Building the Inno installer

1. **Install Inno Setup 6** (free): https://jrsoftware.org/isinfo.php  
   - Use the default install; the command-line compiler `iscc` will be on your PATH.

2. **From the project root**, ensure the app folder is complete (Dockerfile, docker-compose.yml, Start.bat, app/, static/, etc.).

3. **Build the installer:**
   ```bat
   cd installer
   iscc ledgerly.iss
   ```

4. The resulting executable is:
   - `installer\output\LedgerlySetup.exe`

### Giving it to your dad (Inno)

1. Copy **LedgerlySetup.exe** to his computer (USB, cloud, etc.).
2. He runs **LedgerlySetup.exe** and follows the wizard.
3. He leaves “Start Ledgerly now” checked if he wants it to launch right after install (optional).
4. After that, he can start Ledgerly anytime from the desktop shortcut or Start Menu → Ledgerly → **Ledgerly**.  
   To stop: Start Menu → Ledgerly → **Stop Ledgerly**, or open a terminal in the install folder and run `docker compose down`.

The installed folder includes **install-instructions.md**—good to open once so he knows **first-time startup can take a long time** (Docker images + AI models) and later starts are much quicker.

## Requirements on his PC (both options)

- **Windows 10 or 11** (or compatible).
- **Docker Desktop** installed and running. If Docker isn’t installed, the installer will still copy files and create shortcuts, but starting Ledgerly will fail until Docker is installed and the PC has been restarted if the installer prompted for it.

The stack includes **internal Postgres + pgvector** (for fast RAG), **Ollama**, a small **finance-mcp** container (compound interest + optional Finnhub stock quotes), and the **Ledgerly** app. Add **`FINNHUB_API_KEY`** to `.env` in the install folder if he wants live quotes; **Ask** in the web app uses the tools automatically when Compose is running. MCP clients can use **`http://localhost:8001/mcp`** (with `mcp-remote`) while Docker is up.

## Uninstall

**Inno install:** Use **Settings → Apps → Ledgerly → Uninstall**, or run **Uninstall Ledgerly** from the Start Menu.

**Portable (Setup.bat) install:** Delete the desktop shortcut and the folder `%LocalAppData%\Ledgerly`.

In both cases, Docker and any images/volumes are left as-is (he can remove those separately if desired).
