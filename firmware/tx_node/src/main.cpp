// GnatSonic — Phase 0 TX test firmware (ROADMAP.md §7, Phase 0, tasks 2 & 6)
//
// Purpose: drive the MAX98357A + speaker chain with two test signals so the
// actual transducer response can be measured before any protocol parameter
// (f0, f1, symbol duration, guard interval) is chosen:
//
//   's'                 -> play a clean 15 kHz -> 22 kHz linear sine sweep
//                          over 5 seconds (Phase 0 task 2/4/5: feeds the
//                          spectrogram analysis script)
//   'b<freq_hz>'         -> play repeated bursts of a single tone at
//                          <freq_hz> with silence gaps, to measure the
//                          speaker's ring/settling time after tone-off
//                          (Phase 0 task 6: sets a real guard interval)
//                          e.g. "b18000" bursts at 18000 Hz
//
// This is Phase 0 test code only. It intentionally does NOT implement BFSK,
// framing, or any final frequency choice — those are placeholders in
// ROADMAP.md §5 until real measurements come back from this tool.
//
// Wiring (ROADMAP.md §4): MAX98357A -> ESP32
//   LRC  -> GPIO25
//   BCLK -> GPIO26
//   DIN  -> GPIO22
//   GND  -> GND
//   VIN  -> 5V (or 3.3V, check module's datasheet)
//   SD   -> 3.3V (enable) — or leave the default pull per module
//   GAIN -> floating (default gain) unless a specific gain is wanted
//   Speaker output -> the speaker terminals
//
// See docs/PHASE0_INSTRUCTIONS.md for the full step-by-step procedure.

#include <Arduino.h>
#include <driver/i2s.h>
#include <math.h>

namespace {

constexpr i2s_port_t kI2sPort = I2S_NUM_0;
constexpr int kSampleRate = 48000;
constexpr int kBclkPin = 26;
constexpr int kWsPin = 25;
constexpr int kDoutPin = 22;

// Peak amplitude out of int16 full scale (32767). Kept well under full
// scale to avoid clipping distortion, which would corrupt the spectrogram
// measurement this tool exists to produce.
constexpr float kAmplitude = 9000.0f;

constexpr float kSweepStartHz = 15000.0f;
constexpr float kSweepEndHz = 22000.0f;
constexpr float kSweepDurationS = 5.0f;

constexpr int kBurstToneMs = 200;
constexpr int kBurstGapMs = 800;
constexpr int kBurstRepeats = 6;

void i2sInit() {
  i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX),
      .sample_rate = kSampleRate,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
      .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = 0,
      .dma_buf_count = 8,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = true,
      .fixed_mclk = 0};

  i2s_pin_config_t pins = {.bck_io_num = kBclkPin,
                            .ws_io_num = kWsPin,
                            .data_out_num = kDoutPin,
                            .data_in_num = I2S_PIN_NO_CHANGE};

  i2s_driver_install(kI2sPort, &config, 0, nullptr);
  i2s_set_pin(kI2sPort, &pins);
  i2s_zero_dma_buffer(kI2sPort);
}

// Writes `count` mono samples to I2S, duplicated onto both stereo channels
// (MAX98357A modules select L, R, or L+R/2 depending on the SD pin strap —
// duplicating the sample onto both channels means the tone plays correctly
// regardless of that strap).
void writeMonoSamples(const int16_t* samples, size_t count) {
  static int16_t stereo[512]; // 256 frames max per call below
  size_t written = 0;
  while (written < count) {
    size_t chunk = min(count - written, sizeof(stereo) / sizeof(stereo[0]) / 2);
    for (size_t i = 0; i < chunk; ++i) {
      stereo[2 * i] = samples[written + i];
      stereo[2 * i + 1] = samples[written + i];
    }
    size_t bytesWritten = 0;
    i2s_write(kI2sPort, stereo, chunk * 2 * sizeof(int16_t), &bytesWritten,
               portMAX_DELAY);
    written += chunk;
  }
}

void writeSilence(int ms) {
  static const int16_t zeros[512] = {0};
  size_t totalFrames = static_cast<size_t>(kSampleRate) * ms / 1000;
  size_t written = 0;
  while (written < totalFrames) {
    size_t chunk = min(totalFrames - written, sizeof(zeros) / sizeof(zeros[0]) / 2);
    size_t bytesWritten = 0;
    i2s_write(kI2sPort, zeros, chunk * 2 * sizeof(int16_t), &bytesWritten,
               portMAX_DELAY);
    written += chunk;
  }
}

// Linear chirp from kSweepStartHz to kSweepEndHz over kSweepDurationS,
// generated in small blocks with a continuous phase accumulator so there's
// no discontinuity (and hence no spurious broadband click) between blocks.
void runSweep() {
  Serial.println("SWEEP_START");
  const size_t totalSamples =
      static_cast<size_t>(kSampleRate * kSweepDurationS);
  const float k = (kSweepEndHz - kSweepStartHz) / kSweepDurationS; // Hz/s

  constexpr size_t kBlock = 256;
  int16_t buf[kBlock];
  double phase = 0.0; // radians

  for (size_t n = 0; n < totalSamples; n += kBlock) {
    size_t blockLen = min(kBlock, totalSamples - n);
    for (size_t i = 0; i < blockLen; ++i) {
      double t = static_cast<double>(n + i) / kSampleRate;
      double instFreq = kSweepStartHz + k * t;
      double dt = 1.0 / kSampleRate;
      phase += 2.0 * PI * instFreq * dt;
      if (phase > 2.0 * PI) phase -= 2.0 * PI;
      buf[i] = static_cast<int16_t>(kAmplitude * sin(phase));
    }
    writeMonoSamples(buf, blockLen);
  }
  Serial.println("SWEEP_END");
}

void runBurst(float freqHz) {
  Serial.printf("BURST_START freq=%.1f tone_ms=%d gap_ms=%d repeats=%d\n",
                freqHz, kBurstToneMs, kBurstGapMs, kBurstRepeats);

  const size_t toneSamples =
      static_cast<size_t>(kSampleRate) * kBurstToneMs / 1000;
  constexpr size_t kBlock = 256;
  int16_t buf[kBlock];

  for (int rep = 0; rep < kBurstRepeats; ++rep) {
    Serial.printf("BURST_TONE_ON %d\n", rep);
    double phase = 0.0;
    for (size_t n = 0; n < toneSamples; n += kBlock) {
      size_t blockLen = min(kBlock, toneSamples - n);
      for (size_t i = 0; i < blockLen; ++i) {
        phase += 2.0 * PI * freqHz / kSampleRate;
        if (phase > 2.0 * PI) phase -= 2.0 * PI;
        buf[i] = static_cast<int16_t>(kAmplitude * sin(phase));
      }
      writeMonoSamples(buf, blockLen);
    }
    Serial.printf("BURST_TONE_OFF %d\n", rep);
    writeSilence(kBurstGapMs);
  }
  Serial.println("BURST_END");
}

void printMenu() {
  Serial.println();
  Serial.println("GnatSonic Phase 0 TX test firmware");
  Serial.println("Commands (type into Serial Monitor, newline-terminated):");
  Serial.println("  s          - run 15kHz-22kHz, 5s sine sweep");
  Serial.println("  b<freqHz>  - run tone-burst test at freqHz, e.g. b18000");
  Serial.println();
}

} // namespace

void setup() {
  Serial.begin(115200);
  delay(300);
  i2sInit();
  printMenu();
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) return;

    if (line == "s") {
      runSweep();
    } else if (line.startsWith("b")) {
      float freq = line.substring(1).toFloat();
      if (freq >= 1000.0f && freq <= 24000.0f) {
        runBurst(freq);
      } else {
        Serial.println("Invalid frequency. Use e.g. b18000 (1000-24000 Hz).");
      }
    } else {
      Serial.println("Unrecognized command.");
      printMenu();
    }
  }
}
