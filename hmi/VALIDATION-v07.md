# v0.7 candidate validation

The v0.6.2 baseline was physically validated by the station operator for a successful Class I measurement and compact receipt/PDF output. The v0.7 results below come from automated checks and the native simulator.

| Check | v0.7 evidence |
| --- | --- |
| Native files | Editable HMI extracted and checked again. The target remains NX8048T070_011R at 270°, 480 × 800 and 115200 baud. The page is still `keyboard`. |
| Compiled candidate | nxwright Basic build with the 1.68.2 firmware. All TFT sections and checksums verified. The TFT is 11,686,564 bytes. |
| RAM | Guide uses 3,452 of 3,584 bytes. QR uses 1,948 bytes plus the 1,565-byte render workspace. |
| Operator workflow | Tests cover DE factory default, persistence, language switching with a draft, report language override, fresh and ambiguous imports, warnings, cancellations, and measurement selection. |
| Screen layout | All 17 pages and every guided step and help state rendered in both languages. The guide tests check word wrapping and ensure its text fits the native components. |
| Report layout | Bilingual success, failure, incomplete, unknown and simulation samples rendered. Ordinary Class I samples remain one A4 page. Failed German receipts retain the two-line raster. |
| Units | Ω bitmap verified in the Nextion font table. PDF text extraction returns Ω and MΩ together with the original comparison operators and 500 V. The Epson stream switches only Ω to PC437 and restores PC850. |
| Settings | Render-only systemd units pass `systemd-analyze verify`. Printer endpoint fallback, explicit overrides and preserved custom values are regression tested. |

## Physical acceptance pending

1. Compile the editable HMI in official Nextion Editor 1.68.2. Leave the working v0.6.2 firmware available for rollback. Use a separate FAT32 microSD for the candidate.
2. Confirm DE/EN changes on the home screen. Keep an entry open, change language, resume it and verify text and selected report language. Power-cycle the station and check persistence.
3. Import available BENNING readings over the verified USB link. Check that the physical symbols shown for protection class, IPE/IB and STORE, RECALL and PRINT match the tester. Compare dates and raw verdicts against the tester.
4. Print Class I examples in both languages on the installed Epson. Check Ω and MΩ, the voltage spacing, the compact layout and the contrast of both raster headings. Compare the corresponding PDFs.
5. Recheck Wi-Fi scanning, remembered networks, the hotspot QR download, printer configuration, standby and autostart in both languages. Follow the installation guide to roll back if needed.

The experimental RS232 path remains subject to a separate hardware test. The v0.7 station was neither installed nor flashed during candidate preparation.
