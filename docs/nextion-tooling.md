# Nextion tooling investigation — 25 November 2026

The latest compiling user project extracted without unknown-format warnings: NX8048T070, 270°, ISO-8859-1, pages `home`, `entry`, `qrpage`, `report`, `read`, stock `keybdA`, Program.s baud 9600. The candidate reuses the target, rotation, supplied branding and component defaults, replaces pages/events and generates full Latin-9 fonts.

| Primary source | Capability and project decision |
| --- | --- |
| [nxwright](https://github.com/nixiewright/nxwright), reviewed commit `e9443a409cc9deb866db7486854fa962d382accc` (0.5.6) | Selected: editable HMI extract/build, fonts/rotation, native event interpreter/simulator, Basic TFT compilation with separately acquired vendor firmware. Extraction, semantic round trip, event tests and TFT decompile/recompile succeeded. Official Editor/physical validation remain distinct gates. |
| [Nextion2Text](https://github.com/MMMZZZZ/Nextion2Text) | Readable dumps for diffs. Its README says it cannot convert text back to HMI; insufficient for this redesign alone. |
| [nextion-editor-pipeline-reverse-engineer](https://github.com/leehambley/nextion-editor-pipeline-reverse-engineer) | Existing-component/scaffold patching. Documented target differs, and same-length HMI patches cannot provide the required new pages/keyboard. |
| [tjc-hmi-toolkit](https://github.com/cmyfqwq/tjc-hmi-toolkit) | Container/component/event repacking. Its tested environment is TJC USART HMI 1.68.1 and TJC8048X270, a weaker match for this Nextion Basic. |
| [eseverson/nextion-hmi](https://github.com/eseverson/nextion-hmi), [UNUF/nxt-doc](https://github.com/UNUF/nxt-doc) | Useful HMI/TFT/ZI/checksum/protocol research. No manual patching of the working binary was needed. |
| [Official Nextion Editor](https://nextion.tech/nextion-editor/), [instruction set](https://nextion.tech/instruction-set/) | Independent authoring/compile/simulator/upload acceptance path. nxwright fetched Editor 1.68.2 firmware from Nextion for the TFT build; no vendor installation/firmware is committed here. |

The keyboard is newly implemented native event code, not a copied third-party skin. The supplied Repair Café/FMI banner is retained. Noto Sans is included under the accompanying SIL Open Font License; the repository's own licensing was not changed.

Basic-panel RAM is 3584 bytes. QR generation needs temporary RAM based on text capacity, in addition to global/page components. A 160-byte buffer exceeded it; 78 bytes fits an ordinary LAN origin plus a 24-character random token. Limits and actual native events are checked before delivery.
