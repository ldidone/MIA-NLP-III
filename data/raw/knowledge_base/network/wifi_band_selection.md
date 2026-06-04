# Choosing between 2.4GHz and 5GHz Wi-Fi

## Quick comparison

| Property       | 2.4GHz                         | 5GHz                              |
| -------------- | ------------------------------ | --------------------------------- |
| Throughput     | Lower (often 40–70 Mbps)       | Higher (often 200+ Mbps)          |
| Range          | Longer, passes walls better    | Shorter, weaker through walls     |
| Interference   | High (many devices, microwaves)| Lower                             |
| Best for       | Distance, IoT devices          | Speed, streaming, downloads       |

## Decision rule used by CompuFix

1. Prefer a **5GHz** network when:
   - It is available, AND
   - Its estimated speed is meaningfully higher than the current network, AND
   - Its signal is usable (typically stronger than about -70 dBm).
2. Stay on **2.4GHz** when:
   - No 5GHz network is in range, OR
   - The 5GHz signal is too weak to be reliable.

## Signal strength reference (dBm)

```text
-30 to -50 dBm : excellent
-51 to -60 dBm : good
-61 to -70 dBm : usable
worse than -70 : weak / unreliable
```

## Action

If a better 5GHz network is available, recommend switching to its SSID.
Switching requires user approval. In this MVP the switch is **simulated**.
