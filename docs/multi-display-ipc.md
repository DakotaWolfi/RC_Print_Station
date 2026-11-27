# Private station interface

One request and one response per Unix stream connection. Encode UTF-8 JSON followed by LF. Maximum request 8,192 bytes. Maximum response 524,288 bytes. The socket and runtime directory are accessible to the station user. The socket is an operator capability and is intended for trusted clients on the local host. The hotspot HTTP server exposes only the existing token-based PDF routes.

A read request is `{"op":"state","client":"hdmi"}`. Responses contain `{"ok":true,"data":...}` or `{"ok":false,"error":"..."}`. For mutations send a stable per-attempt `id` and use the current `epoch`. Repeating a cached mutation with the same client and ID returns its previous response during the core's lifetime. Use a newly generated ID only after the operator makes a new decision. The cache retains up to 256 entries across clients. If a frontend disconnected during a physical print, verify its status before making a new request.

## State and checkout

`state` supplies format version 1, epoch, sequence, language, filtered configuration, current draft, guide instructions and choices, the active BENNING batch and slots, selection, printer and Wi-Fi progress, and personality access. Read-only state can change between replies as a receiver or worker finishes. A frontend redraw is not a command. Fetch report and directory data on demand through `history`, `report.get`, `people` and `templates`. Limited collections are returned newest first where appropriate.

The per-draft version guards transitions. Entry and remark edits instead compare the previous values of the fields being changed so independent edits can merge. A client editing a draft locally can renew a 20-second `draft.editor` lease every five seconds. Leaving an editor releases the lease, and a crash expires it. Lease ownership does not transfer report or measurement authority to a display. UI views and uncommitted keyboard buffers remain local.

| Operation | Arguments and behavior |
| --- | --- |
| `draft.new` | `mode` is `guided` or `direct`. Refuses to replace a live draft. |
| `draft.editor` | `draft`, `active` boolean. Holds workflow submission from another editor while enabled. |
| `draft.edit` | `draft`, `previous`, `changes`. Fields include ticket, device, phase, slot, autofill and remarks. |
| `draft.discard` | `draft`, `version`, `confirmed:true`. |
| `exam.start`, `review.find` | `draft`, `version`. Starts the chosen workflow or deliberately opens existing readings for review. |
| `guide.choose` | `draft`, `version`, `step`, `choice` index from that step's choices. |
| `guide.back`, `guide.cancel` | `draft`, `version`. Cancel additionally requires confirmation. |
| `exam.function`, `person.pick`, `exam.submit` | Use current draft/version. Function uses a supported `value`. Person pick uses an active `examiner` ID. |
| `language.report` | `draft`, `version`, `language` set to de or en. |
| `review.manual`, `review.back` | `draft`, `version`. |
| `review.select`, `review.confirm` | `draft`, `version`, `record` pair from the state. Confirmation rechecks the current batch and the observed protection class and verdict. |
| `report.get`, `report.link`, `report.print` | `report` ID. Printing requires `confirmed:true`. The link is a restricted token, when configured. |
| `person.save`, `person.active` | Name and optional examiner ID, or examiner ID with active boolean and confirmation. |
| `settings.save` | `values` containing keys accepted by existing station configuration validation. |
| `wifi.scan`, `wifi.connect`, `wifi.hotspot`, `wifi.stop` | Connect uses current scan ID and optional password. Hotspot changes require confirmation. |
| `printer.probe`, `printer.test` | Test receipt requires confirmation. |
| `power.reboot`, `power.halt` | Requires a service permission option and explicit confirmation. |
| `system.info`, `personality.pet`, `personality.engineering` | Read diagnostics or trigger entertainment when allowed. |
| `novelty.print` | `kind` from awoo, pointless, jank or engineer, with `confirmed:true`. Shares the single print queue. |

Commands never ask the electrical tester to run a procedure. The station uses BENNING readings and original verdicts and keeps manual findings separate. Reconnect to the current snapshot after any frontend restart, and reconcile before reissuing an uncertain action.
