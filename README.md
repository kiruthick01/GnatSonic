# GnatSonic

Two ESP32 boards exchange short text messages using near-ultrasonic sound —
no WiFi, no Bluetooth, no wires, nothing visibly connecting them.

**Built so far in this repo (Phase 0 tooling only — see Status below):**
- `firmware/tx_node/` — ESP32 + I2S firmware that plays a 15–22 kHz sine
  sweep and tone-burst tests through a MAX98357A amp + speaker.
- `prototype/phase0_analyze.py` — records from a mic, plots a spectrogram
  and burst-decay envelope, reports SNR per frequency band.
- `docs/PHASE0_INSTRUCTIONS.md` — step-by-step wiring and run instructions
  for the above.

---

## Status

**Phase 0 tooling is built and pushed. Physical hardware validation has not
happened yet.** Every phase after Phase 0 is blocked until real measured
data comes back from running this tooling on actual hardware.

This isn't a caveat buried in the fine print — it's the current state of
the project. No frequency band, symbol timing, or guard interval is fixed
anywhere in this repo. They're placeholders pending measurement, on
purpose.

**Why the gate matters:** an earlier draft of this design used a cheap
piezo alarm buzzer driven by a raw PWM square wave. That combination was a
real risk — piezo buzzers are usually mechanically resonant at one fixed
alarm tone, not broadband transducers, and a square wave is full of
harmonics that would have muddied the Goertzel detector. The design was
changed to a proper I2S DAC/amp (MAX98357A) into a real speaker instead —
but "should work better in theory" isn't good enough to build a protocol
on top of. Phase 0 exists to confirm it actually does, on the specific
parts purchased, before anything else gets written. See ROADMAP.md §2 and
§5.1 for the full reasoning.

---

## Motivation

This project is a hobbyist-scale demonstration of a real, published class
of attack: **air-gap covert channels** — moving data between computers with
no network connection at all, using a physical side channel instead.

- **MOSQUITO** (Guri, Solewicz, Elovici, IEEE DSC 2018) — demonstrated
  covert ultrasonic data transfer between air-gapped computers up to 9
  meters apart, using ordinary PC speakers/mics.
  [arXiv:1803.03422](https://arxiv.org/abs/1803.03422)
- **LISNR** — a real commercial data-over-sound company, encoding data into
  roughly the 14–19 kHz band using ordinary consumer speakers and
  microphones, e.g. for contactless payments.
  [lisnr.com/data-over-sound](https://lisnr.com/data-over-sound/)

Built and operated entirely on hardware the builder owns, between two
devices under the builder's own control — a demonstration of understanding
a real attack class, not a tool for exfiltrating data from systems the
builder doesn't own.

---

## Architecture

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

Both nodes are independent, self-clocked ESP32 boards — no shared wiring or
clock. Timing is recovered per-message from the preamble, not from a shared
clock. Full detail: ROADMAP.md §3, and "how do two independent gadgets stay
in sync" in ENGINEERS_HANDBOOK.md §7.

---

## Roadmap status

| Phase | Objective | Status |
|---|---|---|
| 0 | Feasibility & component validation (sweep + spectrogram) | Tooling built & pushed; hardware run pending |
| 1 | Desktop Python prototype (encode/decode over laptop speakers/mic) | Blocked on Phase 0 data |
| 2 | ESP32 firmware bring-up, raw I/O only | Blocked on Phase 0 data |
| 3 | Port modem (Goertzel + framing) to firmware | Blocked on Phase 0 data |
| 4 | Reliability & framing hardening, BER testing | Blocked on Phase 0 data |
| 5 | Demo UX polish (OLED, status LEDs, enclosure) | Blocked on Phase 0 data |
| 6 | Documentation & portfolio packaging | Blocked on Phase 0 data |
| 7 | Stretch goals (frequency hopping, speaker-as-mic, encryption) | Not started |

Full detail on each phase's tasks and acceptance criteria: ROADMAP.md §7.

---

## More detail

- [ROADMAP.md](ROADMAP.md) — full architecture, BOM, phased build plan, acceptance criteria
- [ENGINEERS_HANDBOOK.md](ENGINEERS_HANDBOOK.md) — plain-language explanation of how it works (FSK, Goertzel, I2S, framing)
- [docs/PHASE0_INSTRUCTIONS.md](docs/PHASE0_INSTRUCTIONS.md) — how to run the Phase 0 sweep/burst tools

## License

MIT — see [LICENSE](LICENSE).
