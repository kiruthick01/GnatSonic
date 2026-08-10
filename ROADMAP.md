# GnatSonic — Project Roadmap

**GnatSonic** is the project name (chosen for the insect-themed tie-in with
this research area — moths and other insects operate acoustically in
frequency bands other animals can't perceive, the same trick this project
uses). Folder/package name: `gnatsonic`.

**This document is the single source of truth for this project.** It
contains the full context, architecture, and phased build plan needed to
implement it from scratch with no other prior conversation history. Read it
fully before writing any code.

---

## 1. Quick Facts

| | |
|---|---|
| **Project name** | GnatSonic (folder: `acoustic-airgap-link` / `gnatsonic`) |
| **One-liner** | Two ESP32 boards exchange short text messages using near-ultrasonic sound — no WiFi, no Bluetooth, no wires, nothing visibly connecting them. |
| **Category** | Embedded systems / signal processing / hardware security research (covert channels) |
| **Hardware budget** | ~₹2,500–3,200 total (both nodes) — see §4, upgraded from an earlier cheaper draft; see design note below |
| **Estimated build time** | 6–8 days of part-time work, structured in 7 phases below |
| **Primary toolchain** | PlatformIO + Arduino framework, targeting ESP32 |
| **Prototype toolchain** | Python 3 (numpy, scipy, sounddevice, matplotlib) |
| **End goal** | A working, benchmarked, well-documented GitHub repo + demo video for portfolio use |

**Design note — build this properly, not cheaply.** An earlier draft of
this plan used a passive piezo alarm buzzer driven by a raw PWM square wave
as the transmitter. That combination is a real risk to the whole project:
cheap piezo buzzer elements are usually mechanically resonant around a
fixed alarm frequency (often a few kHz), not broadband transducers, so
driving one at 18–19 kHz may produce very weak, unreliable output — and a
PWM square wave is full of harmonics that muddy a frequency-selective
detector like Goertzel. This revision replaces that with a proper digital
audio signal chain (I2S DAC/amp into a real speaker) on the transmit side.
See §4 and the design rationale in §2 for why, grounded in how real
commercial data-over-sound products (LISNR) actually do this.

---

## 2. Motivation & Background

This project is inspired by a real, published area of security research
called **air-gap covert channels**: techniques for moving data between
computers that have *no network connection at all*, using physical side
channels instead — sound, light, heat, electromagnetic emissions, even fan
noise. The most directly relevant prior art is:

- **MOSQUITO** — Guri, Solewicz, Elovici, *"MOSQUITO: Covert Ultrasonic
  Transmissions between Two Air-Gapped Computers using Speaker-to-Speaker
  Communication"*, IEEE DSC 2018 (arXiv:1803.03422). MOSQUITO showed that
  ordinary PC speakers/headphones can be reprogrammed at the audio-driver
  level to act as *microphones*, and used this to exchange data acoustically
  in the near-ultrasonic band (18–24 kHz) between two air-gapped machines up
  to 9 meters apart, entirely inaudible to nearby people.

This project is **not** a reproduction of MOSQUITO — we use a real digital
MEMS microphone on the receive side rather than the speaker-reversal trick,
which is a reasonable and honest simplification for a hobbyist build. The
speaker-as-microphone trick is listed as a stretch goal in Phase 7 if
there's appetite to get closer to the original research.

**Component quality is a deliberate decision, not an afterthought.** LISNR
— a real, commercially deployed data-over-sound company used for
contactless payments and proximity detection — encodes data into
approximately the 14–19 kHz band and transmits it "using just speakers and
microphones," i.e. ordinary consumer-grade audio hardware, not lab
equipment. That's the bar this project should hit: a genuine working link,
not a fragile toy that only works in a silent room at 5 cm. Concretely,
that means driving the transmitter with a clean digital-audio signal chain
(I2S DAC/amp into a real speaker) rather than a crude PWM square wave into
a resonant piezo alarm buzzer. See §4 for the resulting hardware choice and
§7 Phase 0 for how this gets empirically validated before anything else is
built on top of it — "should work in theory" is not the same as "measured
and confirmed on the actual parts."

**Why this is worth building:** air-gapped systems (secure facilities,
industrial control systems, classified networks) are assumed safe *because*
they have no network connection. Covert acoustic channels are a real,
demonstrated way that assumption breaks down. Building a working, minimal
example — and being honest in the documentation about what it does and
doesn't prove — is a legitimate, portfolio-relevant demonstration of
understanding a real attack class, not just "two microcontrollers talking."

**Ethical scope:** this is a benign, defensive-research-style demo built and
operated entirely on hardware the builder owns, exchanging messages between
two devices under the builder's own control. It is not built or documented
as a tool for exfiltrating data from systems the builder doesn't own or
lack permission to test. Keep the documentation framed this way throughout.

---

## 3. System Architecture

```
 TX NODE (ESP32 #1)                          RX NODE (ESP32 #2)
 ───────────────────                         ───────────────────
 [Serial input: text message]                [Serial output: decoded message]
        │                                            ▲
        ▼                                            │
 [Framer: preamble + sync +           [Frame parser: preamble detect,
  length + payload + CRC-8]            CRC check, message reassembly]
        │                                            ▲
        ▼                                            │
 [BFSK symbol encoder]                 [Goertzel dual-tone detector,
        │                               sliding window]
        ▼                                            ▲
 [Sine-tone synthesis, I2S out]             [I2S sample stream]
        │                                            ▲
        ▼                                            │
 [MAX98357A I2S class-D amp]                [INMP441 I2S MEMS mic]
        │                                            ▲
        ▼                                            │
   [Small full-range speaker]     ~~~ air ~~~>  (receives acoustic signal)
```

Both nodes are independent, self-clocked ESP32 boards with no shared wiring
or synchronization signal — timing is recovered per-message from the
preamble, not from a shared clock. This is a deliberate design choice, not
an oversight (see §7, Risks).

Note the TX and RX chains are now symmetric in sophistication: both use a
real I2S digital-audio peripheral (I2S out on TX, I2S in on RX), not a
"proper" receive chain paired with a "hacky" transmit chain. This symmetry
is what actually gives this project a shot at a reliable link rather than a
best-case demo.

---

## 4. Hardware Bill of Materials

| Qty | Part | Approx. cost (INR) | Notes |
|---|---|---|---|
| 2 | ESP32 dev board (any common variant, e.g. ESP32-DevKitC / NodeMCU-32S) | ₹350–450 each | Needs I2S peripheral (all standard ESP32s have this, and have two independent I2S controllers — I2S0/I2S1 — so a single board could in principle do both TX and RX, though this project keeps them on separate boards per §3) |
| 2 | INMP441 I2S MEMS microphone breakout | ₹150–250 each | RX side. Buy 2 so either node can act as TX or RX during testing |
| 2 | **MAX98357A I2S Class-D amplifier breakout** | ₹200–300 each | TX side. Takes clean I2S digital audio in and drives a speaker directly — this is what replaces the earlier piezo-buzzer + PWM approach, and is the single most common ESP32 audio-output breakout used in maker projects for exactly this reason: it sidesteps the ESP32's weak built-in 8-bit DAC entirely |
| 2 | Small full-range speaker (3W, 4–8 Ω, ~40 mm) | ₹100–150 each | A genuine speaker cone has meaningfully cleaner high-frequency response than a resonant piezo alarm buzzer, which is typically tuned to a fixed low-kHz alarm tone, not our 17.5–19.5 kHz target band |
| — | Breadboards, jumper wires, USB cables | ₹200–300 | |
| 1 (optional, Phase 5) | Small SSD1306 OLED (I2C, 0.96") | ₹150–250 | For live message display on the RX node during demos |

**Total: roughly ₹2,500–3,200** — a deliberate step up from an earlier
cheaper draft (~₹1,500–2,000 using a piezo buzzer), because the transmit
signal chain is the part most likely to make or break whether this actually
works, not the part to cut cost on.

**Suggested default I2S pin mapping — RX node, INMP441 → ESP32** (confirm
against the specific dev board's silkscreen before wiring):

| INMP441 pin | ESP32 pin |
|---|---|
| VDD | 3.3V |
| GND | GND |
| L/R | GND (selects left channel / mono) |
| WS (word select) | GPIO25 |
| SCK (bit clock) | GPIO26 |
| SD (data out) | GPIO22 |

**Suggested default I2S pin mapping — TX node, MAX98357A → ESP32:**

| MAX98357A pin | ESP32 pin |
|---|---|
| VIN | 5V (or 3.3V per module spec — confirm datasheet) |
| GND | GND |
| LRC (word select) | GPIO25 |
| BCLK (bit clock) | GPIO26 |
| DIN (data in) | GPIO22 |
| GAIN | leave floating for default gain, or set per datasheet for a specific gain level |
| SD (shutdown/enable, active high) | tie to 3.3V to enable, or drive from a GPIO if software-controlled mute is wanted |
| Speaker output (+/−) | to the small speaker |

TX and RX boards use the *same* GPIO numbers for their respective I2S
signals purely because that's the common convention in tutorials for each
chip — this is fine since they're on separate physical boards with no
shared wiring.

---

## 5. Physical / Link Layer Design

### 5.1 Frequency band — **must be empirically validated, not assumed**

Datasheet research done ahead of this build surfaced a real risk worth
flagging explicitly: the INMP441's commonly-cited frequency response spec is
**60 Hz–15 kHz**, even though its digital anti-aliasing filter has a passband
extending to ~20.3 kHz at a 48 kHz sample rate. In plain terms: the mic's
digital filter *won't* block a 18–19 kHz tone, but the physical MEMS element
may be somewhat less sensitive up there than in its rated band. LISNR's own
use of the 14–19 kHz band with "just speakers and microphones" on ordinary
consumer devices is good evidence this is workable in practice — consumer
MEMS mics are routinely used successfully in this exact band commercially —
but confirm it on the actual parts purchased rather than assuming.

**Do not hardcode a frequency and move on.** Phase 0 below exists
specifically to measure this before any protocol code is written. Starting
hypothesis: a band around **17.5–19.5 kHz** (two tones, e.g. f0 = 18000 Hz,
f1 = 19000 Hz, 1 kHz apart) — high enough to be faint/inaudible to most
adults, low enough to have a realistic chance of surviving both the
speaker's output rolloff and the mic's sensitivity rolloff. Be ready to
shift the whole band lower (e.g. 15–17 kHz) if Phase 0 measurements show
poor SNR at 18kHz+ with the specific components purchased.

### 5.2 Modulation: Binary FSK (BFSK)

- Bit `0` → transmit a clean sine tone at frequency `f0` for one symbol
  period
- Bit `1` → transmit a clean sine tone at frequency `f1` for one symbol
  period
- A short **guard interval** (silence) between symbols. With a proper
  speaker driven by a clean I2S sine wave (rather than a resonant piezo
  buzzer), mechanical ringing/decay should be substantially less of a
  problem than in the earlier draft — but still measure the actual settling
  time empirically in Phase 0/1 rather than assuming zero.

**Starting parameters (tune empirically, do not treat as final):**
- Symbol duration: 20 ms
- Guard interval: 3–5 ms (likely reducible from the piezo-era estimate now
  that the transducer is a proper speaker, but confirm in Phase 0/1)
- Effective baud rate: ~40–50 bits/sec → roughly 5–6 bytes/sec before framing overhead

### 5.3 Frame format

```
[ PREAMBLE ][ SYNC BYTE ][ LENGTH BYTE ][ PAYLOAD (LENGTH bytes) ][ CRC-8 ][ END MARKER ]
```

- **PREAMBLE**: fixed alternating pattern, e.g. 8 symbols of `f0,f1,f0,f1,...`
  — used by the receiver to detect "a frame is starting" and to lock onto
  symbol timing (this is the mechanism that replaces a shared clock — see
  §7).
- **SYNC BYTE**: fixed value, e.g. `0xA5` — a second confirmation that this
  is a real frame and not noise that happened to look like a preamble.
- **LENGTH BYTE**: number of payload bytes that follow (0–255).
- **PAYLOAD**: the actual message bytes.
- **CRC-8**: checksum over LENGTH + PAYLOAD, for frame integrity. Any
  standard CRC-8 polynomial is fine (e.g. CRC-8-CCITT); consistency between
  TX and RX implementations matters more than the specific polynomial.
- **END MARKER**: a short fixed silence or fixed symbol pattern signaling
  frame completion.

### 5.4 Detection algorithm: Goertzel

Chosen over a full FFT because we only ever need the energy at exactly two
known frequencies (f0, f1), not a full spectrum — this is dramatically
cheaper to run in real time on a microcontroller. It's also a well-proven,
non-experimental technique: it's the same algorithm real telecom systems
use for DTMF (touch-tone) detection.

```
function goertzel_power(samples, target_freq, sample_rate):
    N = len(samples)
    k = round(N * target_freq / sample_rate)
    omega = 2 * pi * k / N
    coeff = 2 * cos(omega)
    s_prev, s_prev2 = 0, 0
    for sample in samples:
        s = sample + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
    return s_prev2^2 + s_prev^2 - coeff * s_prev * s_prev2
```

Per symbol window, compute `power(f0)` and `power(f1)`:
- If both are below an ambient noise-floor threshold → idle / no symbol
  present (used for preamble/frame-boundary detection).
- Otherwise, decide bit = `1` if `power(f1) > power(f0)`, else bit = `0`.

Window length must give enough frequency resolution to cleanly separate f0
and f1 (frequency resolution = sample_rate / N). At 48 kHz sampling with a
20 ms window (N = 960 samples), resolution is 50 Hz — comfortably enough to
separate tones 1 kHz apart. Driving the transmitter with a clean sine wave
(rather than a harmonic-rich square wave) also directly improves Goertzel's
accuracy, since there's far less energy leaking into frequencies other than
the intended tone.

---

## 6. Software Architecture

**Toolchain:** PlatformIO with the Arduino framework, targeting `esp32dev`
(or the specific board purchased). PlatformIO over the plain Arduino IDE
because it gives a clean, professional project structure that reads well in
a portfolio repo and makes dependency management (I2S libraries) reliable.

**Repo layout (target end state):**

```
gnatsonic/
├── ROADMAP.md                  (this file)
├── README.md                   (written in Phase 6, for public/portfolio consumption)
├── LICENSE
├── prototype/                  (Phase 1 — Python desktop validation)
│   ├── tx_prototype.py
│   ├── rx_prototype.py
│   ├── goertzel.py
│   ├── framing.py
│   └── results/                (BER logs, spectrograms from testing)
├── firmware/
│   ├── tx_node/                (PlatformIO project — I2S out via MAX98357A)
│   │   ├── platformio.ini
│   │   └── src/main.cpp
│   └── rx_node/                (PlatformIO project — I2S in via INMP441)
│       ├── platformio.ini
│       └── src/main.cpp
├── shared/                     (C headers shared between tx_node/rx_node if using a PlatformIO lib, e.g. goertzel.h, framing.h)
└── docs/
    ├── spectrograms/           (Phase 0 validation evidence)
    ├── ber_tables/             (Phase 4 hardening evidence)
    └── demo.mp4 / demo.gif
```

---

## 7. Phased Development Plan

Each phase has a clear objective, concrete tasks, a deliverable, and an
acceptance criterion — do not move to the next phase until the current
phase's acceptance criterion is met and documented.

### Phase 0 — Feasibility & Component Validation (0.5–1 day)

**Objective:** De-risk the two biggest unknowns before writing any protocol
code: can the MAX98357A + speaker combo actually produce clean, sufficient
energy in the near-ultrasonic band, and can the INMP441 actually detect it
with usable SNR at the intended demo distance.

**Tasks:**
1. Acquire all BOM hardware (§4).
2. Wire one ESP32 to the MAX98357A → speaker chain. Generate a clean sine
   sweep from 15 kHz to 22 kHz over ~5 seconds via I2S.
3. Record the sweep using either (a) the INMP441 + a second ESP32 streaming
   raw I2S samples over serial, or (b) faster to set up: a laptop's built-in
   mic + a simple Python script using `sounddevice`, for a first pass.
4. Plot a spectrogram of the recording (`scipy.signal.spectrogram` +
   `matplotlib`). Identify the frequency band with the best combination of
   transmit amplitude and receive sensitivity, and confirm it's meaningfully
   cleaner (less harmonic spread) than a PWM/piezo approach would have been.
5. Pick final `f0` and `f1` based on real data, not the §5.1 starting
   hypothesis alone.
6. While set up, also measure the speaker's ring/settling time after a tone
   stops, to set a real guard interval instead of the §5.2 placeholder.

**Deliverable:** a spectrogram image saved to `docs/spectrograms/`, plus a
short note in the same folder recording the chosen f0/f1, the measured
settling time, and why.

**Acceptance criterion:** a spectrogram clearly showing distinguishable,
narrowband energy at the two chosen frequencies when transmitted and
received at the baseline demo distance (start with 0.5 m; note distance as
a variable to push further in Phase 4).

---

### Phase 1 — Desktop Software Prototype in Python (1 day)

**Objective:** Validate the full encode → transmit → receive → decode
pipeline in a fast-iteration environment (laptop) before committing to
firmware, where debugging is much slower.

**Tasks:**
1. Implement a tone generator (`numpy`) producing f0/f1 at the chosen
   symbol duration and guard interval.
2. Implement the Goertzel detector (§5.4) in Python.
3. Implement the frame format (§5.3): preamble, sync byte, length byte,
   payload, CRC-8, end marker.
4. `tx_prototype.py`: takes a text message from the command line, encodes
   it to a framed symbol sequence, plays it out the laptop speakers via
   `sounddevice`.
5. `rx_prototype.py`: records from the laptop mic continuously, runs a
   sliding-window Goertzel scan, detects the preamble, decodes the frame,
   validates the CRC, and prints the recovered message.
6. Test loopback across at least 3 conditions: quiet room at 0.5 m, quiet
   room at 2 m, room with background noise (music/talking) at 0.5 m. Log
   bit error rate for each.

**Deliverable:** working scripts in `prototype/`, plus a BER results table
in `prototype/results/`.

**Acceptance criterion:** ≥90% successful frame decode rate in the quiet
room / 0.5 m condition. Other conditions are logged honestly even if worse
— the goal here is real measured data, not a perfect result.

---

### Phase 2 — ESP32 Firmware Bring-up, I/O Only (1 day)

**Objective:** Get raw hardware I/O working correctly on each board
independently, before merging in any protocol logic — isolates hardware
bugs from protocol bugs.

**Tasks:**
1. Set up two PlatformIO projects (`firmware/tx_node`, `firmware/rx_node`).
2. TX firmware: use the I2S peripheral to stream a clean, digitally
   synthesized sine tone at f0, then f1, to the MAX98357A, switchable via a
   serial command. Verify using the same spectrogram method as Phase 0.
3. RX firmware: configure the I2S peripheral for the INMP441 (§4 pin
   mapping), stream raw samples out over serial to a laptop, and confirm
   the waveform looks sane (visible periodic signal when a tone is
   playing nearby, silence/noise otherwise).

**Deliverable:** `tx_tone_test` and `rx_i2s_test` minimal sketches proving
each half of the hardware chain works in isolation.

**Acceptance criterion:** RX firmware's streamed samples, analyzed offline,
show a clear, narrowband spectral peak at whatever frequency the TX
firmware is currently outputting — with visibly less harmonic spread than
a square-wave source would produce.

---

### Phase 3 — Port the Modem to Firmware (2 days)

**Objective:** Move the Phase 1 encode/decode logic from Python onto the
ESP32s as real-time C/C++, running on real hardware end to end.

**Tasks:**
1. Port the Goertzel detector to C++ (floating point is fine — ESP32 has a
   hardware FPU).
2. Implement real-time sliding-window symbol detection on the RX firmware,
   processing incoming I2S sample chunks sized to match the symbol
   duration.
3. Implement TX-side framing in firmware (I2S sine synthesis per symbol),
   triggered by a message typed into the TX node's serial monitor.
4. Implement RX-side frame parsing: preamble detection, CRC-8 validation,
   message reassembly, printed to the RX node's serial monitor.

**Deliverable:** complete `tx_node` and `rx_node` firmware that can send an
arbitrary short text message from one ESP32 to the other, purely
acoustically.

**Acceptance criterion:** a message typed into the TX serial monitor
appears correctly on the RX serial monitor, at the Phase 0 baseline
distance, repeatably across at least 10 consecutive trials.

---

### Phase 4 — Reliability & Framing Hardening (1 day)

**Objective:** Make the link robust enough to demo live without babysitting
or repeated retries, and push distance/reliability further than the Phase 0
baseline now that the signal chain is solid.

**Tasks:**
1. Enforce CRC-8 validation with automatic rejection of corrupted frames
   (scaffolded in Phase 3, now actually enforced).
2. Add either a repetition code (send each frame N times, majority-vote
   decode) or a simple retransmit-on-failure scheme — choose based on the
   BER data gathered so far.
3. Add adaptive noise-floor calibration: on startup, sample ~1 second of
   ambient noise and set the detection threshold relative to that baseline
   instead of a hardcoded constant.
4. Re-run the Phase 1-style test matrix (distance × background noise) on
   the real firmware and log before/after BER. Push the distance sweep
   further than Phase 0's baseline now that the speaker/amp chain is in
   place — this hardware should meaningfully outperform the earlier
   piezo-buzzer draft.

**Deliverable:** updated firmware + a before/after BER comparison table in
`docs/ber_tables/`.

**Acceptance criterion:** ≥95% successful message delivery across 20
consecutive trials in a normal room with ordinary background noise present
(not dead silent).

---

### Phase 5 — Demo UX Polish (0.5–1 day)

**Objective:** Make the live demo self-explanatory without narration.

**Tasks:**
1. (Optional, if OLED purchased) Add a small SSD1306 display on the RX node
   showing the decoded message live as it arrives.
2. Add a status LED on each node (transmitting / receiving / idle).
3. Build or 3D-print a minimal stand/enclosure for each node so they look
   as two independent standalone devices on a table, not loose breadboards.

**Deliverable:** final physical build, photographed from a few angles.

**Acceptance criterion:** someone unfamiliar with the project can watch the
demo and understand roughly what just happened without you narrating it.

---

### Phase 6 — Documentation & Portfolio Packaging (1 day)

**Objective:** Turn the working build into a polished, standalone GitHub
repo entry suitable for a resume/portfolio link.

**Tasks:**
1. Write `README.md` (separate from this roadmap) containing: motivation
   with the MOSQUITO and LISNR references as context (§2), an architecture
   diagram, a plain-language "how it works" section followed by a technical
   section, the BOM with costs, build instructions, measured results (BER
   table, range table), and an embedded demo GIF/video.
2. Record a 30–60 second demo video: two devices sitting apart on a table,
   a message typed on one, the message appearing on the other, no visible
   connection between them.
3. Clean up commit history, add an MIT `LICENSE`, and keep the
   `docs/spectrograms/` and `docs/ber_tables/` evidence in the repo — real
   measured data is more convincing than a polished claim.

**Deliverable:** public GitHub repo + demo video, linkable from a resume or
LinkedIn post.

**Acceptance criterion:** the README alone, with no verbal explanation from
you, is enough for a reader to understand what was built, why, and how well
it performs.

---

### Phase 7 — Stretch Goals (open-ended, time-permitting)

Not required for a complete project — attempt only if earlier phases went
smoothly and there's appetite for more:

- **Frequency-hopping / spread-spectrum encoding** to resist narrowband
  noise or intentional jamming.
- **Speaker-as-microphone trick** (closer to the real MOSQUITO paper):
  attempt to receive using a reversed speaker instead of the INMP441, to
  remove the dedicated mic entirely.
- **Payload encryption**: AES-encrypt the message before framing, to
  demonstrate the "covert *and* confidential" distinction explicitly in the
  writeup.
- **Two-stage attack narrative**: if the separate acoustic-keystroke-sound
  project gets built later, stage a combined demo where keystrokes
  recovered from that project are exfiltrated over this ultrasonic channel
  — same underlying acoustic-side-channel theme, staged as a 2-part story.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| INMP441's rated frequency response (60 Hz–15 kHz) may mean reduced sensitivity above 15 kHz despite the digital filter passing up to ~20 kHz | Phase 0 empirically measures real SNR before any band is finalized; LISNR's commercial use of a near-identical band on ordinary consumer mics is good supporting evidence this is workable; be ready to shift the band down to ~15–17 kHz if needed |
| Piezo-buzzer-and-PWM approach (earlier draft) risked weak, harmonic-distorted transmission | Resolved by switching to an I2S DAC/amp (MAX98357A) driving a real speaker with a clean synthesized sine wave — see §4/§6 |
| Two independent ESP32 boards have no shared clock, so symbol timing will drift over a long transmission | Keep messages short and self-contained per frame; resynchronize via preamble detection at the start of every frame rather than relying on long-term clock sync |
| Even a real speaker has some mechanical settling/ringing time after a tone stops | Measure actual decay time empirically in Phase 0 rather than assuming it's zero just because it's "a real speaker now"; budget the guard interval accordingly |
| Ambient noise (fans, conversation, music) masking the signal | Adaptive noise-floor calibration (Phase 4); Goertzel is inherently narrowband, which already helps significantly versus broadband noise |

---

## 9. Validation & Test Plan Summary

Run this same test matrix at the end of Phase 1 (software) and again at the
end of Phase 4 (hardened firmware), and keep both result sets in the repo
for a documented before/after comparison:

- Distance sweep: 0.5 m, 1 m, 2 m (further if Phase 0 data supports it —
  the upgraded speaker/amp chain should plausibly do better than the
  piezo-buzzer draft would have, but confirm rather than assume)
- Noise conditions: silent room, room with background music/talking
- Metric: bit error rate and/or full-frame success rate over ≥20 trials per
  condition

---

## 10. References

- Guri, M., Solewicz, Y., & Elovici, Y. (2018). *MOSQUITO: Covert
  Ultrasonic Transmissions between Two Air-Gapped Computers using
  Speaker-to-Speaker Communication.* IEEE DSC 2018.
  https://arxiv.org/abs/1803.03422
- LISNR — commercial data-over-sound platform, used as real-world evidence
  that ~14–19 kHz transmission over ordinary consumer speakers/microphones
  is a proven, workable approach, not just a lab curiosity.
  https://lisnr.com/data-over-sound/
- INMP441 datasheet (TDK InvenSense) — frequency response and I2S digital
  filter specs.
- MAX98357A datasheet (Analog Devices/Maxim) — I2S Class-D amplifier used
  for the TX signal chain.
- Espressif ESP-IDF I2S peripheral documentation.
- Goertzel algorithm — standard DSP technique for efficient single-frequency
  detection, widely used in DTMF (touch-tone) decoding, which is a close
  algorithmic cousin of this project's BFSK detector.
