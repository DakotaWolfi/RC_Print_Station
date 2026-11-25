# v0.4 validation and 12 December readiness

**v0.3**: user confirmed hardware (including QR); official Editor compiled after renaming the keyboard page to `keyboard`. **v0.4**: separate candidate, tested in software only. No Pi settings, service, display firmware or printer were changed during this work.

| Software check | Scope |
| --- | --- |
| HMI source and build | nxwright 0.5.6, unlocked editable HMI; extract/diff round trip |
| TFT compilation | Basic model, vendor firmware 1.68.2 from the existing v0.3 TFT; nxwright structural and round-trip checks |
| Memory | 2572/3584 bytes for keyboard; 1888/3584 for Wi-Fi; QR 1352 + 1565 temporary = 2917/3584 bytes |
| Print regression | Existing graphical header bytes and 45 mm cut sequence retained at default; density command opt-in; test receipt explicitly a simulation |
| Tests | Native event simulator for masking/cancel, async scan/activation, QR changes, offline printing, shared config, display settings and confirmation; mock NetworkManager D-Bus for profile persistence and restoration; existing report/history/PDF regressions |
| Startup unit review | Shell syntax, rendered service definitions and systemd unit verification; not installed |
| Simulator preview | 17 rendered states, including Wi-Fi, masked keyboard, printer, receipt and system pages |

## Bench acceptance before replacing v0.3

- [ ] Open v0.4 HMI in official Editor 1.68.2; confirm correct target, portrait 270°, `keyboard` page, then compile it independently and check all native pages.
- [ ] Save a separate official TFT. Verify power-cycle baud at 115200 and physical touch alignment.
- [ ] On Pi 4B under the actual service user: boot without Wi-Fi, open setup, scan, enter a known wrong password, retry with a correct one and confirm IP/SSID. Verify the previous profile is restored where appropriate and successful WLAN reconnects after cold boot. Test the actual Landauer WLAN and phone reachability; check client isolation.
- [ ] While Wi-Fi scans/connects and with Wi-Fi off, confirm the Epson can print on Ethernet. Verify used IP/port, test receipt, physical graphical header, feed/cutter and German characters.
- [ ] Open a PDF from its QR, change WLAN/IP and confirm a fresh QR points to the new address; verify no stale code remains offline.
- [ ] Toggle receipt settings from the panel and web admin in turn; send a receipt after each update. Keep density at Druckervorgabe unless the exact printer is verified compatible.
- [ ] Check display dimming/standby/wake after cold boot. Test cancel/expiry for reboot/shutdown and then exercise confirmed actions only after logind authorization on the bench.
- [ ] Preserve and test rollback. Install/autostart with the paired TFT and backend only after acceptance. Orange Pi migration deferred.
