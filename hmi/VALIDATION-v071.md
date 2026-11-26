# v0.7.1 validation

## Completed in the development environment

| Check | Evidence |
| --- | --- |
| Published v0.7 editable HMI and TFT | Verified both files against their v0.7 manifest. Extracted the HMI and inspected the TFT release blocks and component name hashes. Home page 0 had language button ID 11 and locale hotspot 22. Entry page 1 had report language button ID 27 and hotspot 39. Both release payloads were present. |
| Candidate hardware format | Native `keyboard`, NX8048T070 series T, 480 × 800 at 270°, 115200 baud. Protocol 71. TFT compiled with the nxwright toolchain using the Basic 1.68.2 firmware. All TFT section sizes and checksums verified. |
| Candidate component IDs | Home button 14 and locale hotspot 25. Entry blue report language button 27 and locale hotspot 39. The `home.lang` object is global. Both TFT button releases issue a fresh page report and the required `RC70` packet. Home render acknowledgments are present in the compiled refresh event. |
| Candidate editable file | Extracted the delivered HMI and ran its native events in nxwright's simulator against the backend. Both buttons were visible and touchable. Confirmed persisted language, alternate graphic selection, draft resumption, receipt language independence and display acknowledgment. |
| Limits | TFT 12,516,396 bytes. Home 2,216 bytes, guide 3,452 bytes and QR 1,948 plus 1,565 bytes of workspace within the 3,584-byte Basic RAM limit. |
| Software | Regression suite includes measurement selection, keyboard, Wi-Fi, printer, PDF and receipt layouts, offline rotation, stale UART routes, pet, milestones and simulated providers. Render-only main and both optional worker service profiles passed systemd verification. |

Repeat the artifact checks with the editable HMI and TFT from the *same* release.

```sh
nxwright check hmi/native
python tools/audit_language_artifacts.py /path/to/FMI_RC_native_v0_7_1.HMI /path/to/FMI_RC_native_v0_7_1.tft
nxwright tft-read /path/to/FMI_RC_native_v0_7_1.tft
python -m unittest discover -s tests
python tools/render_v06_previews.py /tmp/fmi-v071-previews
```

## Physical acceptance pending

- Compile the editable HMI in the official Nextion Editor. Verify the actual hardware model and use a spare test microSD. Keep the working firmware and service checkout available for rollback.
- Watch the station journal as described in the [language diagnostics guide](../docs/personality-v071.md). Test DE → EN → DE. Set the report language to the opposite language, back out, switch the station language, resume the draft and verify both the retained text and report override. Restart the backend and verify station-language persistence.
- Check normal BENNING guided/direct paths and USB imports. Wait on the guide for at least one rotation interval to confirm slogans and Easter eggs stay off the testing screens.
- Verify the mascot counter after restart, one-second hold for Engineering Mode, and the farewell during a confirmed shutdown. The statistics should distinguish real examinations from passes and simulations.
- Print both languages and compare the compact receipt, Ω/MΩ characters and ordinary one-page PDFs. Confirm failures retain the original verdict.
- Start the optional worker only when its resource and API limits are configured. Live Responses API billing and real llama.cpp inference on the Pi 4 were outside the automated test environment. The Orange Pi UART and service setup require physical bench verification.
