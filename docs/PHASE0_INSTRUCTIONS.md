# Phase 0 — Feasibility & Component Validation: How-To

Companion to ROADMAP.md §7 Phase 0. This is a physical-hardware phase — **you
do all the steps below**; nothing here can be done remotely. What's already
built for you:

- `firmware/tx_node/` — PlatformIO project that drives the MAX98357A +
  speaker with a sine sweep or tone bursts, on command.
- `prototype/phase0_analyze.py` — records from your laptop mic (or loads a
  WAV you already have), plots a spectrogram / envelope, and prints a
  data-driven report.

Nothing in the repo assumes a final f0/f1, symbol duration, or guard
interval yet — those get decided after you run this and share the results.

---

## 0. What you need physically

From ROADMAP.md §4:

- 1x ESP32 dev board
- 1x MAX98357A I2S Class-D amp breakout
- 1x small full-range speaker (3W, 4-8 Ω)
- Breadboard + jumper wires + USB cable
- Your laptop, with its built-in microphone

You do **not** need the INMP441 mic or a second ESP32 for this first pass —
task 3(b) in the roadmap explicitly allows using the laptop's own mic to
move faster. The INMP441 comes in later phases.

## 1. Wiring (physical — you do this)

MAX98357A → ESP32 (ROADMAP.md §4):

| MAX98357A pin | ESP32 pin |
|---|---|
| VIN | 5V (check your module's datasheet — 3.3V may also be fine) |
| GND | GND |
| LRC | GPIO25 |
| BCLK | GPIO26 |
| DIN | GPIO22 |
| GAIN | leave floating (default gain) |
| SD | tie to 3.3V (enables the amp) |
| Speaker +/− | to the speaker terminals |

Double check pin labels against your specific board's silkscreen — GPIO
numbering can vary between ESP32 dev board variants.

## 2. Software setup (you do this once)

**PlatformIO** (to flash the ESP32):
- Easiest path: install the [PlatformIO IDE extension for VS Code](https://platformio.org/install/ide?install=vscode).
- Or install the CLI: `pip install platformio`

**Python environment** (to run the analysis script):
```bash
cd gnatsonic/prototype
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Flash the TX firmware (you do this)

```bash
cd gnatsonic/firmware/tx_node
pio run -t upload
pio device monitor
```
(Or, in the VS Code PlatformIO extension: open `firmware/tx_node/` as the
project folder, click the checkmark to build, the arrow to upload, and the
plug icon to open the serial monitor.)

Once the serial monitor is open and the ESP32 has booted, you should see:

```
GnatSonic Phase 0 TX test firmware
Commands (type into Serial Monitor, newline-terminated):
  s          - run 15kHz-22kHz, 5s sine sweep
  b<freqHz>  - run tone-burst test at freqHz, e.g. b18000
```

Leave this monitor open — you'll type commands into it in the steps below.

## 4. Find your laptop's mic device index (you do this)

```bash
cd gnatsonic/prototype
python3 phase0_analyze.py list-devices
```

This prints a numbered list of audio devices. Note the index of your
laptop's **built-in microphone** (input device) — you'll pass it as
`--device N`. If you skip `--device`, it uses your system's default input,
which is usually fine.

## 5. Run the sweep test (you do this — it's a two-hands operation)

Setup: place the ESP32+speaker and laptop at your baseline test distance
(**start at 0.5 m**, per ROADMAP.md §7 Phase 0 acceptance criterion). Quiet
room for this first pass.

1. In one terminal, start the recorder — it starts recording immediately
   and tells you when to trigger the sweep:
   ```bash
   python3 phase0_analyze.py sweep --record 8 --device N
   ```
2. As soon as it prints `Recording 8.0s ... Start the TX firmware command
   NOW`, switch to the Serial Monitor and type `s` + Enter.
3. Wait for both to finish (the firmware prints `SWEEP_END`, the script
   prints `Recording finished.`).

The script will then automatically:
- Save the raw recording to `docs/spectrograms/sweep_raw_<timestamp>.wav`
- Save a spectrogram image to `docs/spectrograms/sweep_spectrogram_<timestamp>.png`
- Save a text report to `docs/spectrograms/sweep_report_<timestamp>.txt`
- Print a per-500Hz-band SNR table and a candidate f0/f1 suggestion to your
  terminal

**What to look for in the spectrogram image:** a clean diagonal line
sweeping from 15 kHz to 22 kHz, roughly constant in brightness (constant
SNR) across the sweep. If the line fades out or disappears above some
frequency, that's the rolloff point — the usable band stops there. If the
whole thing is very faint everywhere, something's wrong before frequency
selection matters (check wiring, amp gain, speaker connection, volume/level
of ambient noise).

**Repeat this at 1 m and 2 m if time allows** (not required for Phase 0
acceptance, but useful early data for Phase 4's distance sweep later) —
just rerun the same two steps at a new distance, results get new
timestamps automatically so nothing overwrites.

## 6. Run the burst / settling-time test (you do this)

Pick a candidate frequency from the sweep report (e.g. if the report
suggested `f0~18000 Hz`, use that).

1. Start the recorder:
   ```bash
   python3 phase0_analyze.py burst --freq 18000 --record 8 --device N
   ```
2. When it says to start, switch to the Serial Monitor and type `b18000`
   (matching the frequency above) + Enter.
3. Wait for `BURST_END` and `Recording finished.`

The script saves an envelope plot (`burst_envelope_<timestamp>.png`) and a
report (`burst_report_<timestamp>.txt`) with a measured settling time per
burst and a suggested guard interval.

**What to look for in the envelope plot:** six clear peaks (one per burst)
that rise quickly and decay back down before the next peak starts. If a
peak hasn't decayed back to near the floor before the next one begins,
that's a real ringing problem — note it, it directly affects the guard
interval decision.

## 7. What to send back

Once you've run steps 5 and 6 at least once (ideally at 0.5 m in a quiet
room to satisfy the Phase 0 acceptance criterion):

- The spectrogram PNG and sweep report
- The burst envelope PNG and burst report
- Which distance(s)/conditions you tested
- Anything that looked visibly wrong (weak signal, no response, distorted
  audio, etc.)

With that real data, f0/f1/guard-interval get finalized and Phase 1 (the
Python desktop prototype) starts.

---

## Troubleshooting

- **No visible sweep in the spectrogram at all**: check the amp's SD pin is
  tied high (enabled), check speaker polarity/connection, check the ESP32
  serial monitor actually printed `SWEEP_START`/`SWEEP_END` (confirms the
  firmware ran), try moving the mic closer (10-20 cm) as a sanity check.
- **`sounddevice`/PortAudio import error**: on macOS this is usually
  resolved by `pip install sounddevice` inside the venv (it bundles
  PortAudio); on Linux you may need `sudo apt install libportaudio2` first.
- **PlatformIO can't find the board / upload fails**: check the USB cable
  supports data (not charge-only), check you selected the right serial
  port, try holding the ESP32's BOOT button during upload if it doesn't
  auto-reset.
