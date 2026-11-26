# FMI Printstation v0.7 · Deutsch und Englisch

## Bedienung / Operation

**DE / EN** auf der Startseite wechselt die Stationssprache. Die Einstellung bleibt nach dem Neustart erhalten. **Entwurf fortsetzen** öffnet die bisherigen Angaben. Die Berichtsprache folgt zunächst der Stationssprache. Mit **Bericht: DE / EN** auf der Eingabeseite lässt sie sich für den aktuellen Bericht wechseln.

**EN / DE** on the home screen changes the station language. **Resume draft** opens the current draft. A new draft starts with the station language for receipts and PDFs. Tap **Report: EN / DE** on the entry screen to choose the other language. Saved reports retain their own language when you open, print or download them again. Older reports default to German.

The touchscreen follows the current station language, including when viewing a saved report. Names, custom appliance descriptions, remarks and BENNING data are stored as entered or imported. Button names and display messages such as PASS, FAIL, Lo LOAD, I LEAK, STORE, RECALL and PRINT refer to the same physical tester in either language. The [Swiss BENNING workflow references](benning-guided-workflows.md) still apply. The responsible examiner decides whether the appliance can be released.

Dates use DD.MM.YYYY (DE) or DD/MM/YYYY (EN). The display, receipt and PDF use Ω, kΩ and MΩ. The test voltage is shown with a space, for example 500 V. The test date, units, comparison signs and verdicts in the original import remain available in the database.

## Pi 4B and Nextion preparation

Use the [validation checklist](../hmi/VALIDATION-v07.md) and the [artifact checksums](../hmi/build/manifest-v07.json). The editable project and compiled candidate target the Nextion Basic NX8048T070_011R, 480 × 800 portrait at 270°, 115200 baud and native protocol **70**. Keep the backend and TFT from the same release.

1. Save the v0.6.2 checkout, its working TFT, both systemd units, the SQLite database and the service user's `~/.config/rc-printstation/receipt.json`. Save `/etc/rc-printstation/benning.env` and any device permissions used on the working Pi. Use a separate checkout and a copy of the database for bench tests.
2. Open `FMI_RC_native_v0_7.HMI` in Nextion Editor 1.68.2 and compile it for the target model. Check that the page is named `keyboard`. Compare the distributed candidate against the manifest before using it.
3. Use a separate, freshly formatted FAT32 microSD. Copy the single matching **TFT** to its root directory. Power the display off, insert the card, then power on with a stable supply. Wait for the successful update, power off, remove the card and power on again.
4. Stop the previous station backend before opening the Pi UART with the candidate. Bench-test with a copied database and maintain the existing USB tester permissions.

   ```sh
   /usr/bin/python3 native_ui.py --port /dev/serial0 --baud 115200 \
     --tester-mode usb --db /tmp/rc-v07-bench.sqlite3 \
     --auto-report-url --host 169.254.25.23 --printer-port 9100
   ```

5. Review the rendered units with the intended persistent database path. The render action writes only the requested unit files. The installer picks up explicit arguments or a previously customised service endpoint. Its fallback is **169.254.25.23:9100**. The saved printer host and port in the station configuration continue to take runtime precedence. Leave the Pi Ethernet address at **169.254.100.1/16**.

   ```sh
   bash tools/install_services.sh --render /tmp/rc-v07-units \
     --db /absolute/path/reports.sqlite3 \
     --printer-host 169.254.25.23 --printer-port 9100
   systemd-analyze verify /tmp/rc-v07-units/*.service
   ```

6. After a successful bench check, run the installer as the station user with the reviewed options, the real database path and `--replace`. Start the paired services manually. The installer enables them for subsequent boots. The loopback administration and authenticated file import follow the configured station language. The hotspot continues to serve tokenised PDF downloads on the download listener.

## Rollback

Stop `rc-printstation.service` and `rc-printstation-admin.service`. Save the candidate database and configuration separately so reports created during testing are available for review. Restore the working v0.6.2 checkout, units, database and configuration from the backup. Reflash the matching v0.6.2 TFT via microSD. Run `sudo systemctl daemon-reload`, restart the restored services and confirm the touchscreen, tester and Epson work together. Preserve candidate snapshots in their own SQLite copy.

## Rebuilding and translating

German source strings and `translations/en.json` form one catalogue. Adjust the English entry for copy changes, and keep the runtime formatting placeholders aligned. Generate the native source, result banners and previews with the pinned build requirements.

```sh
python tools/generate_hmi.py
python tools/generate_result_rasters.py
nxwright check hmi/native
nxwright build hmi/native /tmp/FMI_RC_native_v0_7.HMI --no-lock
nxwright compile hmi/native /tmp/FMI_RC_native_v0_7.tft --firmware /path/to/basic-1.68.2.tft
python tools/render_v06_previews.py /tmp/fmi-v07-previews
python -m unittest discover -s tests
```

Nextion stores the Ω bitmap in the unused 0xAD font slot for ISO-8859-15, outside the editable keyboard character set. The colour PDF uses the embedded Noto Sans glyph. Epson uses PC437 for the single Ω byte and immediately returns to PC850 for the surrounding text. [Epson ESC t reference](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/esc_lt.html) · [Epson PC437 table](https://download4.epson.biz/sec_pubs/pos/reference_en/charcode/page_00.html)
