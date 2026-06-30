# Target PC — Dad's Dell XPS 15 9530

Reference hardware and recommended Ledgerly settings for the primary Windows portable install (Docker Desktop).

## Device specifications

| Field | Value |
|--------|--------|
| **Machine** | Dell XPS 15 9530 |
| **Device name** | XPS-15 |
| **Processor** | 13th Gen Intel Core i7-13700H (2.40 GHz, 14 cores / 20 threads) |
| **RAM** | 32 GB (4800 MT/s) |
| **GPU** | NVIDIA GeForce RTX 4060 Laptop (8 GB) + Intel Iris Xe |
| **Storage** | ~954 GB SSD |
| **OS** | Windows 11 Pro 25H2 (build 26200.8655) |
| **Install location** | `%LocalAppData%\Ledgerly` (after `Setup.bat`) |

Captured: October 2024 (Windows install date on device).

## Why use the portable profile on a powerful laptop?

This machine has plenty of RAM, but Ledgerly's Docker stack runs **Ollama inside a Linux VM on CPU** (no NVIDIA passthrough in the default compose file). Sustained inference heats a thin chassis and spins the fan. The **portable** profile trades speed for **cooler, quieter** operation: smaller models, queued Ask, and one Ollama job at a time.

## One-time configuration

After `Setup.bat`, in `%LocalAppData%\Ledgerly`:

```bat
copy .env.portable-xps15.example .env
```

Then restart Ledgerly from the desktop shortcut (or run `Start.bat`).

If you build the portable ZIP yourself, this template is included at the project root and copied into the zip.

## Recommended `.env` (summary)

See [`.env.portable-xps15.example`](../.env.portable-xps15.example) for the full file. Key settings:

| Variable | Value | Purpose |
|----------|--------|---------|
| `LEDGERLY_PROFILE` | `portable` | `qwen2.5:3b`, `moondream`, queued Ask |
| `OLLAMA_NUM_THREADS` | `4` | Cap CPU threads (explicit; cooler than auto-detect max of 8 on 20-thread CPU) |
| `OLLAMA_MAX_CONCURRENT` | `1` | Serial Ollama HTTP calls |
| `LLM_INTER_CALL_SLEEP_SEC` | `2` | Pause between prep LLM steps in Ask |
| `ASK_QUEUE_INTER_JOB_SLEEP_SEC` | `5` | Pause between queued questions |
| `OLLAMA_WARMUP_ENABLED` | `false` | Less idle heat when switching tabs |

Do **not** set `LLM_MODEL` or `LLAVA_MODEL` — portable defaults apply.

## Verify after start

```bat
curl http://localhost:8000/health
```

Expect: `"ask_mode":"queued"`, `"profile":"portable"`.

```bat
docker compose exec ollama printenv OLLAMA_NUM_THREADS
```

Expect: `4`.

## User tips (PDF ingest)

For scanned PDFs, use **Auto** or **OCR** in the Ingest UI instead of **Vision** when possible — OCR avoids per-page vision model calls.

## Related docs

- [install-instructions.md](../install-instructions.md) — first-time Windows setup
- [installer/README.md](../installer/README.md) — building the portable ZIP
- [setup_and_testing.md](../setup_and_testing.md) — portable profile details
