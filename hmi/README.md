# Native Nextion HMI

The current source in `native/` is v0.5. See [the Pi 4 and BENNING guide](../docs/benning-v05.md) and [v0.5 validation](VALIDATION-v05.md). Earlier HMI archives and their documentation are retained.

## Build v0.5

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-build.txt
nxwright check hmi/native
python -m unittest discover -s tests -v
nxwright build hmi/native /tmp/FMI_RC_native_v0_5.HMI --no-lock
nxwright compile hmi/native /tmp/FMI_RC_native_v0_5.tft --download
```

If a 1.68.2 Basic-series TFT is available, use `--firmware PATH` instead of the download. Open and compile the generated HMI in official Editor 1.68.2 as an independent check before flashing. `tools/generate_hmi.py` replaces the generated source in `native/`; keep manual edits in version control before regenerating. `tools/render_hmi.py` produces simulated UI previews. See the [v0.5 manifest](build/manifest-v05.json) for exact artifact hashes.

# Native portrait HMI candidate v0.3

Target: **Nextion Basic NX8048T070_011R**, 270°, **480 × 800**, UART **115200**. The supplied compiling project is the starting point: its target, orientation, branded banner and component defaults were retained. The original HMI and legacy backend are preserved.

## Files

| Path | Purpose |
| --- | --- |
| `reference/FMI_RC_Printstation_working.zip` | Untouched user HMI, originally `FMI_RC_Printstation_dark_template(4).HMI`; extract before opening |
| `build/FMI_RC_native_v0_3.zip` | Editable candidate HMI; extract before opening; pages unlocked, no passwords |
| `native/` | Text source, native events, fonts and individual page artwork |
| `design/` | Supplied banner, licensed typeface and readable keyboard mapping |
| `previews/` | Actual native simulator renderings, including symbols and accents |
| `VALIDATION.md` | Completed checks and remaining physical validation gates |

The HMI ZIPs preserve exact project bytes and fit the publishing interface's per-request limit. Extract the candidate archive to obtain `FMI_RC_native_v0_3.HMI`. The compiled `FMI_RC_native_v0_3.tft` is a separate deliverable; it includes vendor firmware and is not committed to this source repository. It can also be compiled locally.

## Interface

Home, appliance entry, keyboard, simulation report, QR download, five-item history and station information are real native pages. Native `page` instructions perform transitions; Python supplies field values and completion flags. There is no host-side screen drawing or coordinate polling.

The keyboard has Swiss QWERTZ letter order, numbers, direct ä/ö/ü, uppercase Ä/Ö/Ü, one-shot **Aa**, **Caps**, backspace, clear, space and two symbol banks. **123 → é / § → ABC** cycles the banks. Caps changes letters only; Shift also changes numbers and punctuation. This is a touchscreen adaptation: Shift gives uppercase umlauts directly instead of reproducing every dead-key combination of a physical Swiss keyboard. Accents are separate characters, not dead keys. There is no ß on the main Swiss keyboard.

**Übernehmen** commits the field; **Abbrechen** keeps its prior value. Ticket length is 32 bytes and device length 64 bytes. The new HMI/backend use **ISO-8859-15 (Latin-9)** for German/French characters and `€`. The legacy UI retains Latin-1. The Epson PC850 receipt represents `€` as `EUR`.

Simulation warnings are permanent artwork on home/report/download; receipts and PDFs identify simulations too. No electrical tester integration or safety verdict is implemented.

## Build and edit

Python 3.11 or later; checked here with Python 3.12 and pinned nxwright 0.5.6. Use a development checkout.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-build.txt
nxwright check hmi/native
python -m unittest discover -s tests -v
nxwright build hmi/native hmi/build/FMI_RC_native_v0_3.HMI --no-lock --overwrite
```

Open the resulting HMI in the official Nextion Editor, verify the device and compile it there. Alternatively:

```sh
nxwright compile hmi/native /tmp/FMI_RC_native_v0_3.tft --download
```

`--download` permits the first compile to fetch Nextion Editor 1.68.2's firmware from Nextion. Later builds reuse the cache. Otherwise supply an installed Editor with `--editor PATH` or compatible TFT with `--firmware PATH`. Vendor firmware is not supplied in Git. After rebuilding, refresh the HMI ZIPs and manifest with `python tools/package_hmi.py --tft /tmp/FMI_RC_native_v0_3.tft`.

Edit `native/pages/` directly for component/event changes. The HMI's pictures and fonts are resources editable in the official Editor. For systematic artwork/layout changes, edit `tools/generate_hmi.py`, then run it and rebuild. **The generator replaces the candidate source pages and artwork**, so commit manual source edits first. It never writes `reference/`. `tools/render_hmi.py` refreshes the review images.

If editing the HMI in the Editor, save a separate copy and extract it into a new source folder before rebuilding. A build from the old source otherwise replaces those Editor-only changes. Review them with `nxwright diff`.

## Bench startup

1. Keep the working HMI, checkout and database backed up. Use a separate checkout and database copy for the candidate.
2. Open the candidate in the official Editor and complete `VALIDATION.md`. Upload only to a development display using the Editor, UART uploader or FAT32 microSD. No script here flashes the panel automatically.
3. Stop only the old display process owning the UART. The candidate starts at 115200 on every boot using `baud`, not persistent `bauds`.
4. Install `requirements.txt` on the host, then run:

   ```sh
   python3 native_ui.py --port /dev/serial0 --baud 115200 \
     --host 169.254.223.252 --printer-port 9100 --db reports-candidate.sqlite3
   ```

5. For PDF/QR add the Pi's reachable LAN URL:

   ```sh
   python3 native_ui.py --port /dev/serial0 --host 169.254.223.252 \
     --db reports-candidate.sqlite3 --report-url http://192.168.1.42:8080
   ```

   Replace the example IP. HTTP listens on 8080 by default (`--web-port` changes it). The phone must be on a network that reaches it. The QR cannot configure Wi-Fi or provide Internet hosting. The origin is limited to 51 ASCII characters; the complete token URL to 78 bytes, to fit Basic-panel QR working memory. Disabled downloads produce an explanation instead of a stale QR.

The backend checks model and protocol before updating UI variables. A heartbeat runs every two seconds; after approximately seven seconds without one, the display reports disconnection, retains draft text and blocks submission. Native editing/navigation continue. Printer jobs run in a worker so TCP timeouts do not block the heartbeat. A completed send confirms TCP submission; check the physical receipt. Failed or uncertain jobs are never automatically retried.

## Rollback

Stop `native_ui.py`, extract `reference/FMI_RC_Printstation_working.zip`, then compile/upload its untouched `.HMI` and restart unchanged `nextion_ui.py` from the working checkout. The original HMI boots at **9600**:

```sh
python3 nextion_ui.py --port /dev/serial0 --baud 9600 \
  --host 169.254.223.252 --native-keyboard --db reports.sqlite3
```

Use the existing `--fast` option only after the 9600-baud handshake if desired. Never run both backends on one UART. Both use the existing database schema; a candidate database avoids mixing bench simulations into working history. Building this candidate changes no system services, network settings or working HMI.
