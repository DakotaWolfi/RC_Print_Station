# FMI Printstation v0.7.1

## Language and home screen

**DE / EN** on the home screen changes the interface language and saves it in the station user's `~/.config/rc-printstation/receipt.json`. **Bericht: DE / Report: EN** is the blue button beside the examination phase. It selects the language for the current report independently of the interface. **Entwurf fortsetzen / Resume draft** returns to the same entry data. Previously saved reports retain their saved output language.

A short repair slogan rotates every five minutes while the home screen is available. The 106 curated German and English pairs work offline and are cycled through before reuse. The station pauses rotation while a guided measurement is active. Five taps on the FMI logo open the workshop wolf. Tap **Streicheln / Pet the wolf** to increment the persistent counter. Hold the version number on the home screen for one second to open the read-only engineering page.

Milestones recognise future crossings of 10, 50, 100 and 500 documented examinations. Both BENNING reports and incomplete examination reports count. Simulations are excluded. Passed tests count distinct BENNING records attached to reports, with reported verdicts preserved. A pass is neither a successful repair count nor an appliance release. A milestone briefly occupies the slogan area when the operator returns home.

The printer connectivity metric checks TCP only. The BENNING metric reflects the receiver's current state. CPU load is the one-minute Linux load average. RAM is used memory based on `MemAvailable`. Disk usage is for the report database's filesystem. Shutdown is queued immediately on confirmation. The display shows a short farewell as Linux begins the shutdown.

To disable the mascot, milestones and farewell, set `Environment=FMI_EASTER_EGGS=0` in a main service drop-in. Slogans and read-only diagnostics remain available.

## Upgrade and rollback

1. Keep a copy of the currently working firmware, checkout, units, SQLite report database and station settings. Stop report writes briefly or use SQLite's backup command for a consistent copy. Bench-test against a separate database copy.
2. Compare the artifacts with [the manifest](../hmi/build/manifest-v071.json). Open the HMI in the official Nextion Editor and compile for **NX8048T070_011R**, 480 × 800 portrait, 270°. The candidate TFT uses 115200 baud and handshake protocol **71**. Firmware and backend from different protocol versions will fail the handshake.
3. With the display powered off, insert a FAT32 microSD whose root contains only the matching TFT. Power on with a stable supply, wait for the successful update, power off and remove the card. Load the matching v0.7.1 backend on the separate test checkout. Use the normal BENNING and printer configuration.
4. Render the candidate units before installation, keeping the existing printer configuration and using the bench database initially.

   ```sh
   bash tools/install_services.sh --render /tmp/fmi-v071-units --db /absolute/path/bench.sqlite3 --enable-local-power
   systemd-analyze verify /tmp/fmi-v071-units/*.service
   ```

   Include `--enable-local-power` only on a station that already permits touchscreen power actions. The Raspberry Pi default UART remains `/dev/serial0`. On the Orange Pi, use the UART device exported by the configured image in the service command, and bench-test its enumeration and permissions before deployment. Printer fallback is `169.254.25.23:9100`.
5. Run the [bench checklist](../hmi/VALIDATION-v071.md) first. If adopting the release, stop both old services and run the installer with the reviewed options, `--replace` and the correct report database path. The optional slogan worker has its own installation below.

For rollback, stop the optional slogan worker timer and the two station services. Back up the candidate database and settings separately to retain any new reports. Restore the previous checkout, units and settings, and use microSD to restore the previous matching TFT. Reload systemd and start the previous services. The separate slogan cache can remain in place while the previous station runs.

## Diagnosing language events

Use the journal while testing both blue language buttons. The event sequence identifies whether the request was lost at the display, UART or persistence layer.

```sh
sudo journalctl -fu rc-printstation
```

| Check | Expected result |
| --- | --- |
| Service startup | `Printstation v0.7.1, native HMI protocol 71, saved station language de` or `en`. |
| Home toggle | `Language event station received on home`, then `Station language persisted: en` and `Panel confirmed station language render`. |
| Report override | `Language event report received on entry`, the selected output language, then `Panel confirmed report language render`. |
| Missing or stale page report | `needs page resync`. The host requests the actual page ID and rejects the action if it cannot confirm the expected page. |
| Write or redraw problem | Persistence failure, a panel return code with its page and language context, or an acknowledgment timeout. |

The v0.7 HMI and TFT both contain the two buttons and their original events. The precise reason the physical station failed to switch was not reproduced. v0.7.1 places a fresh page report before each language event, invokes native refresh by compiled component ID within the home page, and confirms the rendered language or report-button text. No customer text or raw UART frame is logged by the language diagnostics.

## Optional slogan providers

The offline catalogue is the default. Either optional provider runs in a separate, low-priority systemd service with no report database argument. Both models select bilingual combinations from approved repair-themed clauses. Local validation rejects free-form text, duplicates and invalid IDs before saving the combination. The cache lives at `~/.local/state/rc-printstation/slogans.sqlite3` and contains only slogan data, usage counters and personality statistics. Reports and the BENNING workflow never read generated text.

| Target | Provider | Resource budget |
| --- | --- | --- |
| Orange Pi Zero 3, 1 GB | Offline catalogue, or optional OpenAI API worker | No resident model. The worker's cold Python import used around 16 MiB RSS on the build host. Estimate 20–45 MiB with HTTPS and decoding. Its service limit is 96 MiB. |
| Raspberry Pi 4B, 8 GB | Optional llama.cpp and Qwen2.5-0.5B-Instruct GGUF | Q4_0 weights are 429 MB and Q4_K_M weights are 491 MB. Estimate 0.6–1.1 GiB RSS with one CPU thread and a 2,048-token context. The local service has a 1,200 MiB memory limit, 70% of one CPU quota, nice level 15 and a default 90-second inference timeout. |

The model sizes come from [Qwen's published formats](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF). The optional local runtime uses [llama.cpp's native CLI](https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md). Pi 4 token throughput, memory and thermals still need on-device measurement. Keep local inference disabled until printer, serial and PDF responsiveness are verified during a run.

### Enable the OpenAI provider

1. As the station user, render the optional worker and timer.

   ```sh
   bash tools/install_services.sh --render-slogan-worker /tmp/fmi-slogans
   systemd-analyze verify /tmp/fmi-slogans/*.service /tmp/fmi-slogans/*.timer
   ```

2. Create a root-owned environment file with mode 0600. Edit it with `sudoedit`. The OpenAI key belongs only in this file. For a new file, use the following commands before adding the key.

   ```sh
   sudo mkdir -p /etc/rc-printstation
   sudo touch /etc/rc-printstation/slogans.env
   sudo chown root:root /etc/rc-printstation/slogans.env
   sudo chmod 0600 /etc/rc-printstation/slogans.env
   sudoedit /etc/rc-printstation/slogans.env
   ```

   ```ini
   FMI_SLOGAN_PROVIDER=openai
   OPENAI_API_KEY=<your project API key>
   FMI_OPENAI_MODEL=gpt-5.4-mini
   FMI_SLOGAN_INTERVAL=1800
   FMI_OPENAI_DAILY_REQUESTS=4
   FMI_OPENAI_DAILY_TOKENS=40000
   ```

3. Inspect the rendered units, then install and enable only this timer when ready.

   ```sh
   sudo install -m 0644 /tmp/fmi-slogans/*.service /tmp/fmi-slogans/*.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now rc-printstation-slogans.timer
   ```

The worker checks the cache every five minutes. Below 12 unseen slogans, and after the configured minimum generation interval, it asks the OpenAI Responses API for 50 pairings. The model is configurable and must support structured responses. The worker sends only approved clauses, a short random seed and the output schema. It uses a 15-second socket timeout and a 120-second service deadline. Cached slogans remain usable after the worker is stopped. When the cache empties, the offline catalogue takes over. [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) · [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) · [GPT‑5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)

Daily limits and Engineering Mode totals use UTC. The token figure is the Responses API's returned usage when available. Timeouts and errors can leave a conservative token reservation until the next UTC day. The station's request and token caps are local application limits. To turn generation off, disable and stop `rc-printstation-slogans.timer` and stop any running `rc-printstation-slogans.service`.

### Enable local inference on the Pi 4

Build a 64-bit ARM CPU version of llama.cpp from a pinned revision that provides `llama-cli`, `--grammar`, `--single-turn` and `--simple-io`. Download the 0.5B Q4_K_M GGUF in advance and verify the downloaded file. Check that the service user can read it. Render with `--render-slogan-worker /tmp/fmi-slogans --local-llm` to select the local resource profile. Set the following entries in the private environment file, using absolute paths.

```ini
FMI_SLOGAN_PROVIDER=local
FMI_LLAMA_CLI=/usr/local/bin/llama-cli
FMI_LLAMA_MODEL=/opt/models/qwen2.5-0.5b-instruct-q4_k_m.gguf
FMI_LLAMA_TIMEOUT=90
FMI_SLOGAN_INTERVAL=1800
```

From the chosen llama.cpp source checkout, build a standalone CPU CLI with static project libraries. Use the resulting absolute path as `FMI_LLAMA_CLI` if you run it from the build directory.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF
cmake --build build --config Release --target llama-cli -j2
build/bin/llama-cli --version
```

The local runtime generates eight structured pairings per attempt. During the first run, watch the worker journal, CPU temperature and memory use. Verify that the station remains responsive during active testing, printing and PDF downloads. On the 1 GB Orange Pi use the offline catalogue or the OpenAI profile rather than loading local weights.
