#!/usr/bin/env python3
"""GnatSonic — Phase 0 spectrogram / settling-time analysis tool.

Pairs with firmware/tx_node (the sine-sweep / tone-burst generator running
on the ESP32 + MAX98357A + speaker). This script does the *receive* side of
Phase 0 using the laptop's built-in microphone (ROADMAP.md §7 Phase 0, task
3, method (b) — the fast first-pass option).

Three things it does, selected via subcommand:

  list-devices   List audio input devices so you can pick the right mic.

  sweep          Record (or load) audio captured while the TX firmware runs
                 its 's' sweep command. Plots a spectrogram, estimates the
                 SNR of the 15-22 kHz band in 500 Hz slices above the
                 measured noise floor, and suggests candidate f0/f1 tone
                 pairs (ROADMAP.md §5.1, §7 Phase 0 tasks 4-5).

  burst          Record (or load) audio captured while the TX firmware runs
                 its 'b<freq>' tone-burst command. Measures how long the
                 tone takes to decay to the noise floor after each burst
                 ends, to inform a real guard interval (ROADMAP.md §5.2,
                 §7 Phase 0 task 6).

This tool only measures and reports. It does not choose or hardcode a final
f0/f1/guard interval anywhere else in the repo — that happens after you run
it on the real hardware and the results get reviewed.

Usage examples:
    python phase0_analyze.py list-devices
    python phase0_analyze.py sweep --record 8 --device 1
    python phase0_analyze.py sweep --file docs/spectrograms/sweep_raw.wav
    python phase0_analyze.py burst --freq 18000 --record 8 --device 1
"""

import argparse
import datetime
import os
import sys

import numpy as np
from scipy import signal
from scipy.io import wavfile

try:
    import sounddevice as sd
except (ImportError, OSError) as exc:  # not installed, or PortAudio missing
    sd = None
    _SD_IMPORT_ERROR = exc

import matplotlib

matplotlib.use("Agg")  # headless-safe; we save PNGs rather than show()
import matplotlib.pyplot as plt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECTROGRAM_DIR = os.path.join(REPO_ROOT, "docs", "spectrograms")

SWEEP_LOW_HZ = 15000.0
SWEEP_HIGH_HZ = 22000.0
BAND_STEP_HZ = 500.0


def _require_sounddevice():
    if sd is None:
        sys.exit(
            "sounddevice/PortAudio is not available on this system "
            f"({_SD_IMPORT_ERROR}). Use --file with a pre-recorded WAV "
            "instead, or fix the PortAudio install."
        )


def _timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def list_devices(_args):
    _require_sounddevice()
    print(sd.query_devices())
    print()
    print("Pick an input device's index number for --device below.")
    print("Default input device is marked with '>' in the listing above.")


def record_audio(seconds, samplerate, device, channels=1):
    _require_sounddevice()
    print(f"Recording {seconds:.1f}s at {samplerate} Hz "
          f"(device={device if device is not None else 'default'})...")
    print("Start the TX firmware command NOW (in the Serial Monitor).")
    audio = sd.rec(
        int(seconds * samplerate),
        samplerate=samplerate,
        channels=channels,
        device=device,
        dtype="float32",
    )
    sd.wait()
    print("Recording finished.")
    return audio[:, 0]


def save_wav(path, samplerate, data_float):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scaled = np.clip(data_float, -1.0, 1.0)
    int16_data = (scaled * 32767).astype(np.int16)
    wavfile.write(path, samplerate, int16_data)
    print(f"Saved raw recording: {path}")


def load_wav(path):
    samplerate, data = wavfile.read(path)
    if data.ndim > 1:
        data = data[:, 0]
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    else:
        data = data.astype(np.float32)
    return samplerate, data


def get_signal(args, default_seconds):
    if args.file:
        samplerate, data = load_wav(args.file)
        print(f"Loaded {args.file}: {len(data)/samplerate:.2f}s @ {samplerate} Hz")
        return samplerate, data, args.file

    seconds = args.record if args.record else default_seconds
    samplerate = args.samplerate
    data = record_audio(seconds, samplerate, args.device)
    out_path = os.path.join(
        SPECTROGRAM_DIR, f"{args.mode_name}_raw_{_timestamp()}.wav"
    )
    save_wav(out_path, samplerate, data)
    return samplerate, data, out_path


# ---------------------------------------------------------------------------
# sweep analysis
# ---------------------------------------------------------------------------

def analyze_sweep(args):
    samplerate, data, src_path = get_signal(args, default_seconds=8.0)

    nperseg = 1024
    noverlap = 768
    f, t, Sxx = signal.spectrogram(
        data, fs=samplerate, nperseg=nperseg, noverlap=noverlap, window="hann"
    )
    eps = 1e-12
    Sxx_db = 10 * np.log10(Sxx + eps)

    # --- plot: full-range spectrogram for visual inspection ---
    fig, ax = plt.subplots(figsize=(10, 5))
    display_max_hz = min(samplerate / 2, 24000)
    mask = f <= display_max_hz
    pcm = ax.pcolormesh(t, f[mask], Sxx_db[mask, :], shading="auto", cmap="magma")
    ax.axhline(SWEEP_LOW_HZ, color="cyan", linestyle="--", linewidth=0.8)
    ax.axhline(SWEEP_HIGH_HZ, color="cyan", linestyle="--", linewidth=0.8)
    ax.set_ylabel("Frequency (Hz)")
    ax.set_xlabel("Time (s)")
    ax.set_title(f"GnatSonic Phase 0 — sweep spectrogram ({os.path.basename(src_path)})")
    fig.colorbar(pcm, ax=ax, label="Power (dB, arbitrary ref)")
    fig.tight_layout()

    os.makedirs(SPECTROGRAM_DIR, exist_ok=True)
    png_path = os.path.join(SPECTROGRAM_DIR, f"sweep_spectrogram_{_timestamp()}.png")
    fig.savefig(png_path, dpi=150)
    print(f"Saved spectrogram image: {png_path}")

    # --- quantitative band analysis ---
    # Noise floor per frequency bin: median power across the whole
    # recording (robust to the sweep only briefly visiting each bin).
    noise_floor_db = np.median(Sxx_db, axis=1)
    # Peak power per frequency bin across time (captures the moment the
    # sweep passed through that frequency).
    peak_db = np.max(Sxx_db, axis=1)
    snr_db = peak_db - noise_floor_db

    band_edges = np.arange(SWEEP_LOW_HZ, SWEEP_HIGH_HZ + BAND_STEP_HZ, BAND_STEP_HZ)
    report_lines = []
    report_lines.append("GnatSonic Phase 0 — sweep band SNR report")
    report_lines.append(f"Source: {src_path}")
    report_lines.append(f"Sample rate: {samplerate} Hz, nperseg={nperseg}, "
                         f"freq resolution ~{samplerate/nperseg:.1f} Hz")
    report_lines.append("")
    report_lines.append(f"{'Band (Hz)':>18} | {'Peak SNR (dB)':>14}")
    report_lines.append("-" * 36)

    band_scores = []
    for lo in band_edges[:-1]:
        hi = lo + BAND_STEP_HZ
        bin_mask = (f >= lo) & (f < hi)
        if not np.any(bin_mask):
            continue
        band_snr = float(np.mean(snr_db[bin_mask]))
        band_scores.append((lo, hi, band_snr))
        report_lines.append(f"{lo:8.0f}-{hi:8.0f} | {band_snr:14.1f}")

    # Suggest a tone pair: two bands ~1kHz apart, maximizing the weaker of
    # the two SNRs (so both tones are individually reliable, not just the
    # average).
    best_pair = None
    best_score = -1e9
    for i, (lo_i, hi_i, snr_i) in enumerate(band_scores):
        f_i = (lo_i + hi_i) / 2
        for lo_j, hi_j, snr_j in band_scores[i + 1:]:
            f_j = (lo_j + hi_j) / 2
            if abs(f_j - f_i) < 800 or abs(f_j - f_i) > 1500:
                continue
            score = min(snr_i, snr_j)
            if score > best_score:
                best_score = score
                best_pair = (f_i, f_j, snr_i, snr_j)

    report_lines.append("")
    if best_pair:
        f0, f1, snr0, snr1 = best_pair
        report_lines.append(
            f"Suggested candidate pair (data-driven, NOT final): "
            f"f0~{f0:.0f} Hz (SNR {snr0:.1f} dB), "
            f"f1~{f1:.0f} Hz (SNR {snr1:.1f} dB)"
        )
    else:
        report_lines.append(
            "No candidate pair with 800-1500 Hz separation found — "
            "inspect the spectrogram/table manually."
        )
    report_lines.append("")
    report_lines.append(
        "Rule of thumb: SNR below ~6-10 dB in a band is risky for reliable "
        "detection; if everything above ~18 kHz looks weak, shift the "
        "whole band down toward 15-17 kHz per ROADMAP.md §5.1/§8."
    )

    report = "\n".join(report_lines)
    print()
    print(report)

    txt_path = os.path.join(SPECTROGRAM_DIR, f"sweep_report_{_timestamp()}.txt")
    with open(txt_path, "w") as fh:
        fh.write(report + "\n")
    print(f"\nSaved report: {txt_path}")


# ---------------------------------------------------------------------------
# burst / settling-time analysis
# ---------------------------------------------------------------------------

def analyze_burst(args):
    samplerate, data, src_path = get_signal(args, default_seconds=8.0)
    freq = args.freq

    # Narrowband envelope at the target frequency: bandpass filter around
    # freq, then Hilbert-transform envelope. This tracks how the tone's
    # amplitude rises/falls over time, including the post-tone decay.
    nyq = samplerate / 2
    half_bw = 300.0  # Hz
    low = max(50.0, freq - half_bw) / nyq
    high = min(nyq - 50.0, freq + half_bw) / nyq
    if not (0 < low < high < 1):
        sys.exit(f"--freq {freq} is not compatible with sample rate {samplerate}")

    sos = signal.butter(4, [low, high], btype="bandpass", output="sos")
    filtered = signal.sosfiltfilt(sos, data)
    envelope = np.abs(signal.hilbert(filtered))

    # Smooth envelope slightly to reduce ripple.
    win = max(1, int(0.002 * samplerate))  # ~2ms smoothing window
    kernel = np.ones(win) / win
    envelope_smooth = np.convolve(envelope, kernel, mode="same")

    t = np.arange(len(data)) / samplerate

    # Estimate noise floor from the envelope's low percentile (covers the
    # gaps between bursts, which dominate a burst-test recording).
    noise_floor = np.percentile(envelope_smooth, 10)
    peak_level = np.percentile(envelope_smooth, 95)
    on_threshold = noise_floor + 0.5 * (peak_level - noise_floor)
    # "Settled" = within a small margin of the noise floor.
    settle_threshold = noise_floor + 0.1 * (peak_level - noise_floor)

    above = envelope_smooth > on_threshold
    # Find falling edges: sample i where above[i] True, above[i+1] False.
    falling_edges = np.where(above[:-1] & ~above[1:])[0]

    settle_times_ms = []
    for edge_idx in falling_edges:
        # Search forward up to 200ms for the envelope to drop to the
        # settle threshold.
        search_len = int(0.2 * samplerate)
        end_idx = min(len(envelope_smooth), edge_idx + search_len)
        segment = envelope_smooth[edge_idx:end_idx]
        below = np.where(segment <= settle_threshold)[0]
        if len(below) == 0:
            continue  # didn't settle within window; skip this edge
        settle_samples = below[0]
        settle_times_ms.append(1000.0 * settle_samples / samplerate)

    # --- plot ---
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(t, envelope_smooth, label="envelope", linewidth=0.8)
    ax.axhline(on_threshold, color="green", linestyle="--", linewidth=0.7, label="on threshold")
    ax.axhline(settle_threshold, color="red", linestyle="--", linewidth=0.7, label="settle threshold")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Envelope amplitude (a.u.)")
    ax.set_title(f"GnatSonic Phase 0 — burst envelope @ {freq:.0f} Hz ({os.path.basename(src_path)})")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()

    os.makedirs(SPECTROGRAM_DIR, exist_ok=True)
    png_path = os.path.join(SPECTROGRAM_DIR, f"burst_envelope_{_timestamp()}.png")
    fig.savefig(png_path, dpi=150)
    print(f"Saved envelope plot: {png_path}")

    report_lines = []
    report_lines.append("GnatSonic Phase 0 — tone-burst settling-time report")
    report_lines.append(f"Source: {src_path}")
    report_lines.append(f"Target frequency: {freq:.0f} Hz")
    report_lines.append(f"Detected falling edges (tone-off events): {len(falling_edges)}")
    if settle_times_ms:
        arr = np.array(settle_times_ms)
        report_lines.append(f"Settling times (ms) per edge: "
                             f"{', '.join(f'{v:.1f}' for v in arr)}")
        report_lines.append(f"Median settling time: {np.median(arr):.1f} ms")
        report_lines.append(f"Max settling time: {np.max(arr):.1f} ms")
        suggested_guard = float(np.max(arr)) * 1.5
        report_lines.append("")
        report_lines.append(
            f"Suggested guard interval (max settling * 1.5 safety margin, "
            f"NOT final): {suggested_guard:.1f} ms"
        )
    else:
        report_lines.append(
            "Could not measure settling time — no falling edge settled "
            "within the 200ms search window, or no bursts were detected. "
            "Check the envelope plot and --freq value."
        )

    report = "\n".join(report_lines)
    print()
    print(report)

    txt_path = os.path.join(SPECTROGRAM_DIR, f"burst_report_{_timestamp()}.txt")
    with open(txt_path, "w") as fh:
        fh.write(report + "\n")
    print(f"\nSaved report: {txt_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-devices", help="List audio input devices")
    p_list.set_defaults(func=list_devices)

    common_parent = argparse.ArgumentParser(add_help=False)
    common_parent.add_argument("--file", help="Analyze an existing WAV file instead of recording")
    common_parent.add_argument("--record", type=float, default=None,
                                help="Seconds to record (ignored if --file given)")
    common_parent.add_argument("--device", type=int, default=None,
                                help="Input device index (see list-devices)")
    common_parent.add_argument("--samplerate", type=int, default=48000,
                                help="Recording sample rate (default 48000)")

    p_sweep = sub.add_parser("sweep", parents=[common_parent],
                              help="Analyze a sweep recording")
    p_sweep.set_defaults(func=analyze_sweep, mode_name="sweep")

    p_burst = sub.add_parser("burst", parents=[common_parent],
                              help="Analyze a tone-burst recording")
    p_burst.add_argument("--freq", type=float, required=True,
                          help="Target tone frequency used in the TX 'b<freq>' command")
    p_burst.set_defaults(func=analyze_burst, mode_name="burst")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
