# SystemStatus

A lightweight macOS menu bar app that displays live system stats at a glance — CPU, GPU, Memory, Network, Disk, Battery, and system health — no Dock icon, no clutter.

![macOS](https://img.shields.io/badge/macOS-15.0%2B-blue)
![Swift](https://img.shields.io/badge/Swift-5.9%2B-orange)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

### Monitoring

- **CPU** — User, System, Idle percentages + thread and process counts
- **GPU** — Device, Renderer, and Tiler utilization via IOKit (Apple Silicon & Intel/AMD)
- **Memory** — Used, App Memory, Wired, Compressed, Cached Files, Swap (matches Activity Monitor)
- **Network** — Live upload/download throughput + total bytes sent/received
- **Disk** — Boot-volume free/used space + read/write throughput
- **Battery** — Charge %, charging status, time remaining, cycle count, health *(hidden on desktop Macs)*
- **System** — Thermal state (colour-coded) + system uptime

### UI

- **Menu bar only** — lives in your status bar, never in the Dock
- **Three-tab layout** — Usage (CPU / GPU / Memory), I/O (Network / Disk), System (Battery / System Info)
- **Live arc gauges** — colour-coded rings that shift blue → orange → red as load rises (GPU uses purple → orange → red)
- **Sparkline history charts** — 60-sample line graphs on CPU, Memory, GPU, and Network sections
- **Top 5 processes** — sorted by memory usage, updated every 5 seconds
- **Copy to clipboard** — every section header has a 📋 button to copy all its metrics as text
- **About window** — version, build number, and copyright info, accessible from the popover footer

### Settings

- **Refresh interval** — 1 s / 2 s / 3 s (default) / 5 s / 10 s, persisted across launches
- **Menu bar label** — choose CPU %, Memory %, CPU & Memory, or icon only
- **Threshold alerts** — macOS notifications when CPU or Memory cross a configurable threshold (opt-in, 5-minute cooldown)
- **Visible sections** — show or hide individual sections (CPU, GPU, Memory, Network, Disk, Battery, System Info)
- **Launch at Login** — registers with `SMAppService` (requires app to be in `/Applications`)

## Screenshots

<table>
  <tr>
    <td><img src="/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/Usage.png" width="260" height="391" alt="Usage"></td>
    <td><img src="/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/IO.png" width="260" height="389" alt="I/O"></td>
    <td><img src="/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/System.png" width="260" height="391" alt="System"></td>
  </tr>
  <tr>
    <td><img src="/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/Settings_1.png" width="380" height="453" alt="Settings"></td>
    <td><img src="/mac-apps/SystemStatus/SystemStatus/assets/AppScreenshots/Settings_2.png" width="380" height="453" alt="Settings (cont'd)"></td>
  </tr>
</table>

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
SystemStatusApp.swift         — @main, MenuBarExtra (.window style), Settings scene, About window, menu bar label

Monitors/
  SystemMonitor.swift         — @Observable; timers, history arrays, alert dispatch
  CPUMonitor.swift            — host_processor_info tick-delta; proc_listallpids; top-process sampling
  MemoryMonitor.swift         — vm_statistics64 (HOST_VM_INFO64); sysctlbyname for swap
  NetworkMonitor.swift        — getifaddrs byte-counter delta across all active interfaces
  DiskMonitor.swift           — FileManager (space) + IOBlockStorageDriver (I/O rates)
  BatteryMonitor.swift        — IOKit PowerSources + AppleSmartBattery registry entry
  GPUMonitor.swift            — IOKit IOGPU (Apple Silicon) / IOAccelerator (Intel/AMD); graceful fallback
  SystemInfoMonitor.swift     — ProcessInfo.thermalState; kern.boottime sysctl for uptime

Models/
  CPUStats.swift / MemoryStats.swift / NetworkStats.swift / DiskStats.swift
  BatteryStats.swift / GPUStats.swift / SystemInfoStats.swift

Views/
  ContentView.swift           — 480×720 pt tabbed popup (Usage / I/O / System) + footer
  SettingsView.swift          — Refresh rate, menu bar label, alerts, section visibility, launch at login
  AboutView.swift             — Version, build number, copyright

  Sections/
    CPUSectionView.swift      — CPU gauge + sparkline + User/System/Idle rows + top processes
    MemorySectionView.swift   — Memory gauge + sparkline + 7 metric rows
    GPUSectionView.swift      — GPU gauge + sparkline + Device/Renderer/Tiler rows
    NetworkSectionView.swift  — Upload/download rates + sparklines + total sent/received
    DiskSectionView.swift     — Disk gauge + space + I/O rates
    BatterySectionView.swift  — Battery gauge + status + time + cycle count + health
    SystemInfoSectionView.swift — Thermal state (colour dot) + uptime

  Components/
    ArcGaugeView.swift        — Colour-coded arc ring gauge
    SparklineView.swift       — 60-sample Canvas sparkline
    SectionHeader.swift       — Title, SF Symbol icon, clipboard copy button
    MetricRow.swift           — Label/value row used across all sections

Utilities/
  Formatters.swift            — fmtBytes, fmtRate, and other shared formatters
```

## Notes

- **Thread count** is prefixed with `~` because ~40% of processes are root-owned system daemons that return `EPERM` for all public APIs. Activity Monitor uses a private Apple entitlement (`task_for_pid-allow`). The displayed count is a lower bound.
- **Memory Used** = App Memory + Wired + Compressed, matching Activity Monitor's definition.
- **App Memory** = `(internal_page_count − purgeable_count) × pageSize` (anonymous app-owned pages only).
- **Network** byte counters are 32-bit (`if_data.ifi_obytes/ibytes`); they wrap at 4 GB. Rate calculations remain accurate because only short-interval deltas are used.
- **Disk I/O** is read from `IOBlockStorageDriver` via IOKit; values reflect all block storage devices combined.
- **GPU** metrics require IOKit access to the `IOGPU` (Apple Silicon) or `IOAccelerator` (Intel/AMD) service. On systems where the service is unavailable, the section displays a "not available" message.
- **Thermal state** is read from `ProcessInfo.thermalState` and colour-coded: green (Normal), yellow (Elevated), orange (High — throttling), red (Critical — severe throttling).
- **Launch at Login** uses `SMAppService.mainApp` (macOS 13+) and only works when the app is installed in `/Applications` or `~/Applications`.

## License

MIT — see [LICENSE](LICENSE).
