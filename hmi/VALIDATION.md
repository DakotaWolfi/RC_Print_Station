# Native HMI v0.3 — candidate validation

Date: 25 November 2026. **Candidate for bench testing, not a validated replacement installation.** No display was flashed, printer contacted, working service changed or database migrated in this work.

## Completed checks

| Check | Result |
| --- | --- |
| Starting point | Latest compiling user file `FMI_RC_Printstation_dark_template(4).HMI` extracted without unknown-format warnings |
| Original preservation | `reference/FMI_RC_Printstation_working.zip` contains untouched `.HMI`, 14,531,498 bytes, SHA-256 `a8c8f53e1fa99f675c8aa562a95ea5dcb5d9ff88483d3ed6f9c9dde0084d0308` |
| Target | Basic NX8048T070, 270°, 480 × 800, startup baud 115200, protocol 3 |
| Editable HMI | Built with `--no-lock`; 19,969,618 bytes; no page passwords |
| Source validation | `nxwright check`: 0 errors, 0 warnings |
| HMI round trip | Extract candidate HMI, compare to source with `nxwright diff --no-lock`: no differences |
| TFT compilation | 11,366,244 bytes, within 16 MiB flash; firmware from Nextion Editor 1.68.2 acquired separately from Nextion |
| TFT verification | Every checksum, size and section location holds; decompiled source recompiles to the same content |
| Automated tests | 19 passed on Python 3.12 |
| Native workflow | Touch events → encoded field snapshot → SQLite simulation → existing receipt bytes → QR/history; page transitions performed by native events |
| Keyboard | Swiss Z/Y order, Shift, Caps without changing digits, umlauts, symbols including euro/quotes/backslash, cancel/commit, empty backspace and 32/64-byte limits |
| Failure handling | Wrong HMI/model refusal, fragmented UART/noise, offline retained drafts, duplicate print suppression, printer timeout without automatic retry, disabled QR, bad URL rejection |
| Actual PDF endpoint | Published token returns `application/pdf`, no-store; unknown token returns 404 |
| QR image | Decoded native rendered preview using ZXing-C++; exact preview URL recovered |
| Visual review | Ten native simulator states plus maximum-width 32/64-character fields inspected; no field clipping in those cases |
| Printing regression | Baseline German sample receipt equals main's `station.receipt` bytes, including `ESC J 240` and full cut; euro gains readable `EUR` fallback |

These checks use nxwright's compiler/simulator; they do **not** establish acceptance by the official Editor or the physical panel. TFT checksum/recompile checks are internal consistency checks, not hardware execution.

## Memory budget

Toolchain estimates include the cross-page globals, with the active page's local components:

| Page | Persistent/page RAM (bytes) |
| --- | ---: |
| home | 1680 |
| entry | 1616 |
| keybdA | 2736 |
| report | 1640 |
| qrpage | 1592 |
| history | 1580 |
| settings | 1664 |

The 78-byte QR text buffer additionally needs 1565 bytes of temporary memory: **3157 / 3584 bytes total** on the QR page. The native keyboard uses **2736 / 3584 bytes**. Raising QR capacity can cross a working-memory threshold; re-run `nxwright check/build` after such edits.

Exact HMI/TFT file hashes are in [build/manifest.json](build/manifest.json). The HMI is larger than the TFT because its editable container includes reserved areas and source assets; only the TFT size is the flash payload.

Both editable HMI files are packaged as ZIPs in Git to fit the publishing interface's request-size limit. Packaging verifies that each extracted HMI is byte-identical; it does not alter its format.

## Required before replacing the working project

- [ ] Open the candidate HMI in official Nextion Editor 1.68.2, confirm model/270°/Latin-9/font resources, save a separate copy and compile with zero errors.
- [ ] Run its official simulator: every page, native navigation, keyboard/cancel/commit and QR availability states.
- [ ] Upload to the development NX8048T070_011R; confirm portrait orientation and resistive-touch alignment at all screen corners.
- [ ] Confirm cold-boot communication at 115200; restart the host while retaining draft text; verify stale reports cannot print until reopened.
- [ ] Type `Mühle ÄÖÜ äöü éèà ç 123 @ €` using the physical keyboard; test all symbol banks, Shift/Caps and maximum field lengths.
- [ ] Create a simulation and print on the actual Gen 3 Epson. Verify German glyphs, `EUR`, simulation warning, feed and cutter. A TCP completion is not a physical print acknowledgement.
- [ ] Configure the Pi's actual reachable LAN URL; scan the QR on a phone and inspect the downloaded PDF's simulation marking.
- [ ] Disconnect the UART/host and printer in turn; verify retained drafts, clear messages and no automatic duplicate print.
- [ ] Restore the reference HMI and 9600-baud legacy backend once to prove rollback.
- [ ] Review results before merging/adopting the candidate. Repeat relevant tests on Orange Pi Zero 3 when it arrives.

The real tester remains unidentified and unsupported. Every report produced here has empty measurements, `SIMULATOR` source and `NOT TESTED` verdict. No pass result is inferred.
