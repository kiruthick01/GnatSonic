# GnatSonic — Engineer's Handbook (Plain-Language Edition)

This is a companion to `ROADMAP.md`, written for a human to actually
*understand* the project, not for an AI to build from. ROADMAP.md tells a
builder what to do and in what order. This handbook explains what's
actually going on underneath, in plain language, so you can follow along
as it gets built — and explain it confidently to someone else later.

---

## 1. The one-sentence idea

Two little gadgets sit on a table with no wires, no WiFi, and no Bluetooth
between them, and one of them "whispers" a message to the other using
sound pitched just above what most people can hear.

That's it. Everything else in this document is just "how do you actually
make that work reliably."

---

## 2. Why sound, and why *that* pitch specifically?

Human hearing generally tops out somewhere around 15–20 kHz depending on
age (kids hear higher than adults; this is also why "mosquito alarms" that
annoy teenagers but not adults are a real thing). If you play a tone up in
that range, most people in the room won't consciously notice it, even
though a microphone can still record it perfectly well.

So the trick is: pick a pitch high enough to be inaudible-ish to most
people, but low enough that ordinary cheap speakers and microphones can
still produce and pick it up cleanly. That sweet spot, based on both
published research and real commercial products (see §10), lands around
**17.5–19.5 kHz**. Go much higher and cheap hardware starts struggling to
reproduce it at all. Go much lower and people start actually hearing it as
an annoying whine.

---

## 3. How do you turn a message into sound? (FSK)

**FSK = Frequency-Shift Keying.** It's the simplest possible way to send
digital bits over sound: pick two different pitches, and let one mean "0"
and the other mean "1".

Say tone A (18,000 Hz) = bit `0`, and tone B (19,000 Hz) = bit `1`.

To send the letter "H" (which is `01001000` in binary — 8 bits, since a
byte is 8 bits), the transmitter just plays this sequence of tones, one
after another:

```
0 1 0 0 1 0 0 0
A B A A B A A A   <- which tone plays for each bit
```

Each tone plays for a short, fixed amount of time (a "symbol" — we're
starting with 20 milliseconds per symbol as a rough estimate, to be tuned
once real hardware is tested), with a tiny gap of silence between them so
one tone doesn't blur into the next.

That's genuinely the whole idea for turning bits into sound. The hard part
isn't sending it — it's the receiver reliably telling the two tones apart
in a noisy room. That's the next section.

---

## 4. How does the receiver tell the two tones apart? (Goertzel algorithm)

Imagine trying to figure out "is a piano playing middle-C right now?" You
could analyze *every single note* the piano could possibly be playing
(that's what a full frequency analysis, an FFT, does) — or, if you only
care about one specific note, you could build a much simpler detector that
just answers "how much middle-C is in this sound right now?" and ignore
everything else entirely.

That's the **Goertzel algorithm**. Since we only ever care about two
specific frequencies (tone A and tone B), we don't need to analyze the
entire sound spectrum — we just run two cheap, focused checks: "how much
energy is at 18kHz right now?" and "how much energy is at 19kHz right
now?" Whichever one is louder tells you the bit.

This matters a lot for a microcontroller, which doesn't have much
computing power to spare — Goertzel is dramatically cheaper to run in real
time than a full spectrum analysis would be. It's not an exotic or
unproven technique either — it's the same algorithm real landline phones
have used for decades to recognize touch-tone (DTMF) button presses.

---

## 5. Why not just use a cheap piezo buzzer and a square wave? (I2S)

Early in planning this project, the plan was: drive a cheap piezo alarm
buzzer directly from a microcontroller pin using a simple on/off square
wave at the target frequency. This got upgraded, and it's worth
understanding why.

**Problem 1 — the buzzer itself.** Cheap piezo buzzers (the disc-shaped
alarm elements) are usually *resonant* — physically tuned to vibrate
strongly at one specific frequency (often a shrill low-kHz alarm tone),
and weakly at everything else. Asking one to cleanly produce 18–19 kHz is
like asking a bell tuned to ring at middle-C to instead ring cleanly at a
totally different note — it might do it a little, but weakly and messily.

**Problem 2 — the square wave.** A square wave (just switching a pin on
and off) isn't a pure tone — it's actually a mix of the target frequency
*plus* a bunch of unwanted extra frequencies (harmonics), mathematically
guaranteed by how square waves work. That's bad news for the Goertzel
detector, which is trying to cleanly measure energy at *just* 18kHz and
19kHz — extra harmonic noise nearby makes that measurement muddier and
less reliable.

**The fix: I2S.** I2S is a proper digital audio interface — the same kind
of thing your phone uses internally to move real digital sound data around
cleanly. Using an actual audio amplifier chip (the MAX98357A) fed by I2S
lets the microcontroller generate a genuinely clean sine wave — a pure
single tone with none of the harmonic mess — and play it through a real
speaker rather than a resonant alarm buzzer. Cleaner signal in, cleaner
detection out.

---

## 6. How does raw beeping turn into an actual readable message? (Framing)

Even once the receiver can correctly tell tone A from tone B, that's just
a raw stream of 0s and 1s. You still need rules for: "where does the
message start?", "how long is it?", and "did it arrive correctly, or did
noise corrupt part of it?" That's what **framing** solves — think of it
as the envelope format for a message, not the message itself.

```
[ PREAMBLE ][ SYNC BYTE ][ LENGTH ][ PAYLOAD ][ CRC-8 ][ END MARKER ]
```

- **Preamble** — a fixed, recognizable pattern of beeps sent first, purely
  so the receiver knows "a message is about to start" and can lock onto
  the timing (see §7 for why this matters).
- **Sync byte** — one more fixed check value, a second confirmation this
  is a real message and not random noise that happened to look
  preamble-shaped.
- **Length** — how many bytes of actual content follow.
- **Payload** — your actual message.
- **CRC-8** — a checksum, basically a mathematical fingerprint of the
  message. The receiver recalculates it from what it received and checks
  it matches — if not, the message got corrupted somewhere and gets
  thrown out instead of silently showing garbled text.
- **End marker** — signals "message complete."

---

## 7. How do two independent gadgets with no shared clock stay in sync?

Good question, and it's a real design constraint, not an oversight. The
two ESP32 boards each run on their own internal clock, with no wire or
signal connecting them to keep those clocks aligned. Over a long enough
stretch of time, their sense of "how long is 20 milliseconds" will drift
apart slightly.

The fix is that we don't rely on long-term synchronization at all. The
**preamble** (§6) exists specifically so the receiver re-synchronizes at
the *start of every single message*, from scratch, rather than trying to
stay perfectly aligned with the transmitter over a long period. Keep
messages short, resync every time — problem avoided rather than solved
the hard way.

---

## 8. The physical hardware, and why each piece was chosen

**Transmitter side:** ESP32 → I2S → MAX98357A (a small audio amplifier
chip) → a real small speaker. The ESP32 generates the sine wave digitally
and clean; the MAX98357A amplifies it enough to actually drive a speaker.

**Receiver side:** ESP32 → I2S ← INMP441 (a digital MEMS microphone). This
mic outputs already-digitized sound directly over I2S — no messy analog
signal to clean up, just a clean digital stream the Goertzel algorithm can
process directly.

Both sides use the *same kind* of interface (I2S) for a reason: it means
both the transmit and receive paths are "real" digital audio engineering,
not one clean side paired with one hacky side.

---

## 9. Quick glossary

| Term | Plain-language meaning |
|---|---|
| **FSK** | Encoding bits as one of two different tones |
| **Symbol** | One "beep" — the smallest unit of transmitted sound, representing one bit |
| **Baud rate** | How many symbols (beeps) get sent per second — the "speed" of the link |
| **Guard interval** | A tiny silent gap between symbols so tones don't blur together |
| **Goertzel algorithm** | Fast method to measure energy at one specific frequency |
| **I2S** | A digital audio interface for moving clean digital sound data between chips |
| **Preamble** | A fixed pattern sent first so the receiver knows a message is starting |
| **CRC** | A checksum that lets the receiver detect a corrupted message |
| **Near-ultrasonic** | Sound pitched just above typical adult human hearing (~17–20 kHz) |

---

## 10. Why this isn't just a toy idea

Two pieces of real-world grounding worth knowing, so you can explain why
this project is credible and not just a fun hack:

- **MOSQUITO** (Guri, Solewicz, Elovici, 2018) — real published security
  research demonstrating covert ultrasonic data transfer between air-gapped
  computers, up to 9 meters apart, at a real IEEE security conference.
- **LISNR** — a real company doing this commercially today, encoding data
  into roughly the 14–19 kHz band using ordinary consumer speakers and
  microphones, used for things like contactless payments.

This project is a smaller-scale, hobbyist version of a real, proven
technique — not a purely theoretical exercise.

---

## 11. What "good" looks like at each stage (so you can sanity-check the build)

- **Phase 0 done well:** you should be able to look at a spectrogram
  image and see two clean, narrow spikes at the chosen frequencies — not
  a smeared, noisy mess.
- **Phase 1 done well:** a Python script on your laptop can send a short
  text message from one program to another, purely through your laptop's
  speaker and mic, most of the time.
- **Phase 3 done well:** you type a message into one ESP32's serial
  monitor, and it correctly appears on the other ESP32's serial monitor,
  reliably, not just "sometimes if you're lucky."
- **Phase 4 done well:** it keeps working with normal background noise in
  the room (talking, music) — not just in dead silence.

If any of these feel unconvincing when you check them, that's the signal
to slow down and dig in rather than trust that the code "should" work.
