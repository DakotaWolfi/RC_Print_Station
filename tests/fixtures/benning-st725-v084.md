# Genuine BENNING ST 725 captures

These bytes were supplied by the station operator for issue #4 and reviewed for inclusion. The USB rows contain only fixed tester designations, slots, dates, verdicts and readings. RS232 fields for identifying number, appliance, company and examiner are blank. The terminal transcript, user/host names and paths are excluded.

| Fixture | Contents | SHA-256 of committed file |
| --- | --- | --- |
| `benning-st725-hardware.jsonl` | Original 50-record database export. 41 USB record lines, nine RS232 printouts. Each row preserves the operator's original Base64 payload. | `f31d5bfd15c9431cb7ff8512aed6b9bb4e2cb4e4503f7e8387b5482efa9634ec` |
| `benning-st725-usb-hexdump.b64` | Exactly 5,088 observed bytes from the follow-up terminal hexdump. Original 28-column header with Latin-1-compatible accents, CRLF, 44 complete rows and the beginning of slot 045. | `ec359db07fa021bb276317a5a5129620fe758786de44b5d7157bd45ebe891204` |

The bundled USB rows match byte-for-byte with slots 001–041 from the hexdump. The receiver regression uses the unmodified captures in two ways. It replays the header and all 44 complete rows as a single test frame and separately rejects the exact interrupted dump. A live hexdump can stop before the complete transfer reaches its terminal display, so this tail does not establish what the tester sent after the last visible byte. The complete USB slot 045 frame is unavailable. The complete RS232 slot 045 report is included.

Matching the USB and RS232 records uses the original date and measured values as well as the slot. USB 020 is a genuine Class I IEA example. The USB RPE failure at 040 and IBer failure at 041 are genuine. Both captured RS232 cable results and the complete USB cable result are `Gut`. Failed or unknown cable cases in tests are clearly identified synthetic modifications, including the negative preview. Tests do not claim to have captured actual failed cable status spellings.
