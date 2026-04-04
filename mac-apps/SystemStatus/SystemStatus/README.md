# SystemStatus

A lightweight macOS menu bar app that displays live system stats at a glance — CPU, Memory, Network, Disk, and Battery — no Dock icon, no clutter.

![macOS](https://img.shields.io/badge/macOS-15.0%2B-blue)
![Swift](https://img.shields.io/badge/Swift-5.9%2B-orange)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

### Monitoring
- **CPU** — User, System, Idle percentages + thread and process counts
- **Memory** — Used, App Memory, Wired, Compressed, Cached Files, Swap (matches Activity Monitor)
- **Network** — Live upload/download throughput + total bytes sent/received
- **Disk** — Boot-volume free/used space + read/write throughput
- **Battery** — Charge %, charging status, time remaining, cycle count, health *(hidden on desktop Macs)*

### UI
- **Menu bar only** — lives in your status bar, never in the Dock
- **Live arc gauges** — colour-coded rings that shift blue → orange → red as load rises
- **Sparkline history charts** — 60-sample line graphs on CPU and Memory sections
- **Top 5 processes** — sorted by memory usage, updated every 5 seconds
- **Copy to clipboard** — every section header has a 📋 button to copy all its metrics as text

### Settings
- **Refresh interval** — 1 s / 2 s / 3 s (default) / 5 s / 10 s, persisted across launches
- **Menu bar label** — choose CPU %, Memory %, CPU & Memory, or icon only
- **Threshold alerts** — macOS notifications when CPU or Memory cross a configurable threshold (opt-in, 5-minute cooldown)
- **Launch at Login** — registers with `SMAppService` (requires app to be in `/Applications`)

## Screenshot

![Usage](/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/Usage.png)
---
![I/O](/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/IO.png)
---
![System](/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/System.png)
---
![Settings](/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/Settings_1.png)
---
![Settings_Contd](/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/Settings_2.png)

## Requirements

| | Minimum |
|---|---|
| macOS | 15.0 Sequoia |
| Xcode | 16.0 |
| Swift | 5.9 |

## Building & Running

1. Clone the repo:
   ```bash
   git clone https://github.com/anirbanbagchi/DangerousDave.git
   cd mac-apps/SystemStatus/SystemStatus
   ```
2. Open the project in Xcode:
   ```bash
   open SystemStatus.xcodeproj
   ```
3. Select **My Mac** as the run destination.
4. Press **⌘R** to build and run.

The app icon appears in the menu bar immediately. Click it to open the stats popup. Open **Settings…** from the popup footer to configure preferences.

## Exporting a .dmg

1. **Product → Archive** in Xcode.
2. In the Organizer: **Distribute App → Custom → Copy App → Export**.
3. Wrap the exported `.app` in a disk image:
   ```bash
   hdiutil create \
     -volname "SystemStatus" \
     -srcfolder "/path/to/SystemStatus.app" \
     -ov -format UDZO \
     ~/Desktop/SystemStatus.dmg
   ```

> **First launch on an unsigned build:** macOS Gatekeeper will block it. Go to **System Settings → Privacy & Security → Open Anyway**, or right-click the `.app` → **Open**.

## Architecture

```
SystemStatusApp.swift    — @main, MenuBarExtra (.window style), Settings scene, menu bar label
SystemMonitor.swift      — @Observable; timers, history arrays, alert dispatch
CPUMonitor.swift         — host_processor_info tick-delta; proc_listallpids; top-process sampling
MemoryMonitor.swift      — vm_statistics64 (HOST_VM_INFO64); sysctlbyname for swap
NetworkMonitor.swift     — getifaddrs byte-counter delta across all active interfaces
DiskMonitor.swift        — FileManager (space) + IOBlockStorageDriver (I/O rates)
BatteryMonitor.swift     — IOKit PowerSources + AppleSmartBattery registry entry
SharedViews.swift        — ArcGaugeView, SparklineView (Canvas), SectionHeader, MetricRow, fmtBytes/fmtRate
CPUSectionView.swift     — CPU gauge + sparkline + User/System/Idle rows + top processes
MemorySectionView.swift  — Memory gauge + sparkline + 7 metric rows
NetworkSectionView.swift — Upload/download rates + total sent/received
DiskSectionView.swift    — Disk gauge + space + I/O rates
BatterySectionView.swift — Battery gauge + status + time + cycle count + health
ContentView.swift        — 440×520 pt scrollable popup; all sections + Settings·Quit footer
SettingsView.swift       — Refresh rate, menu bar label, alerts, launch at login
```

## Notes

- **Thread count** is prefixed with `~` because ~40% of processes are root-owned system daemons that return `EPERM` for all public APIs. Activity Monitor uses a private Apple entitlement (`task_for_pid-allow`). The displayed count is a lower bound.
- **Memory Used** = App Memory + Wired + Compressed, matching Activity Monitor's definition.
- **App Memory** = `(internal_page_count − purgeable_count) × pageSize` (anonymous app-owned pages only).
- **Network** byte counters are 32-bit (`if_data.ifi_obytes/ibytes`); they wrap at 4 GB. Rate calculations remain accurate because only short-interval deltas are used.
- **Disk I/O** is read from `IOBlockStorageDriver` via IOKit; values reflect all block storage devices combined.
- **Launch at Login** uses `SMAppService.mainApp` (macOS 13+) and only works when the app is installed in `/Applications` or `~/Applications`.

## License

MIT — see [LICENSE](LICENSE).
