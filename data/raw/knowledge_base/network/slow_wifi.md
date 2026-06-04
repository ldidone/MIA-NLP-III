# Slow Wi-Fi / slow internet

## Symptom

The user reports that the internet feels slow ("mi internet está muy lento",
"slow network", "the connection is slow"). Pages load slowly, video buffers,
or downloads are far below the expected speed.

## Common causes

1. **Connected to a 2.4GHz band** when a faster 5GHz band is available.
   2.4GHz has longer range but much lower throughput and more interference.
2. Weak signal strength (very negative dBm, e.g. worse than -70 dBm).
3. Network congestion (many devices on the same access point).
4. ISP-level issues (out of scope for this tool).

## Diagnosis

1. Check the **current network**: SSID, band (2.4GHz vs 5GHz), signal strength
   (dBm), and estimated speed.
2. List **available networks** and compare estimated speeds and bands.
3. If a 5GHz network from the same router is available with acceptable signal,
   switching usually improves throughput significantly.

## Recommended fix

- If a faster band/network is available, recommend switching to it.
- Switching networks changes system configuration and therefore requires user
  approval before being performed.

See `wifi_band_selection.md` for how to choose between 2.4GHz and 5GHz.
