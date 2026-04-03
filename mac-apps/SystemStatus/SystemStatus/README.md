# SystemStatus

A lightweight macOS menu bar app that displays live system stats at a glance — CPU, Memory, Network, Disk, and Battery — no Dock icon, no clutter.

![macOS](https://img.shields.io/badge/macOS-15.0%2B-blue)
![Swift](https://img.shields.io/badge/Swift-5.9%2B-orange)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

### Monitoring
- **CPU** — User, System, Idle percentages + thread and process counts
- **GPU** — Device, Renderer, and Tiler utilization via IOKit (Apple Silicon + Intel/AMD)
- **Memory** — Used, App Memory, Wired, Compressed, Cached Files, Swap (matches Activity Monitor)
- **Network** — Live upload/download throughput, total bytes, and per-interface breakdown with IPv4 addresses
- **Disk** — Boot-volume free/used space + read/write throughput
- **Battery** — Charge %, charging status, time remaining, cycle count, health, and instantaneous wattage *(hidden on desktop Macs)*
- **System Info** — macOS thermal state (with colour indicator) and system uptime

### UI
- **Menu bar only** — lives in your status bar, never in the Dock
- **Colour-coded status dot** — green / orange / red indicator in the menu bar reflects overall system pressure
- **Tabbed layout** — three tabs (Usage · I/O · System) fit all sections without scrolling on a 480 × 720 pt window
- **Live arc gauges** — colour-coded rings that shift by load level
- **Sparkline history charts** — 60-sample line graphs on CPU, Memory, and GPU sections
- **Top 5 processes** — sorted by memory usage, updated every 5 seconds; right-click to force-quit
- **Copy to clipboard** — every section header has a copy button to export metrics as text
- **About panel** — version, build, and description in a dedicated window

### Settings
- **Refresh interval** — 1 s / 2 s / 3 s (default) / 5 s / 10 s, persisted across launches
- **Menu bar label** — choose CPU %, Memory %, CPU & Memory, or icon only
- **Threshold alerts** — macOS notifications when CPU or Memory cross a configurable threshold (opt-in, 5-minute cooldown)
- **Visible sections** — toggle individual sections on/off; empty-tab placeholder shown when all are hidden
- **Launch at Login** — registers with `SMAppService` (requires app to be in `/Applications`)

## Screenshot

> *(Add a screenshot here once the app is running)*

## Requirements

| | Minimum |
|---|---|
| macOS | 15.0 Sequoia |
| Xcode | 16.0 |
| Swift | 5.9 |

## Building & Running

1. Clone the repo:
   ```bash
   git clone https://github.com/anirbanbagchi/SystemStatus.git
   cd SystemStatus
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

The project follows a layered architecture with strict separation of concerns, organised into Xcode groups that mirror the filesystem layout.

```
SystemStatus/
├── SystemStatusApp.swift          @main entry, MenuBarExtra (.window), Settings + About scenes,
│                                  MenuBarLabel (colour-coded status dot + text)
│
├── Models/                        Pure value types — no logic, no imports beyond Foundation/Darwin
│   ├── CPUStats.swift             CPUStats + TopProcess structs
│   ├── MemoryStats.swift          MemoryStats struct
│   ├── NetworkStats.swift         NetworkStats + InterfaceStats structs
│   ├── DiskStats.swift            DiskStats struct
│   ├── BatteryStats.swift         BatteryStats struct (incl. powerWatts)
│   ├── GPUStats.swift             GPUStats struct
│   └── SystemInfoStats.swift      SystemInfoStats struct (thermalState + uptime)
│
├── Monitors/                      Data-collection layer — reads system APIs, returns model values
│   ├── SystemMonitor.swift        @Observable coordinator; timers, history arrays, alert dispatch
│   ├── CPUMonitor.swift           host_processor_info tick-delta; proc_listallpids; top-process sampling
│   ├── MemoryMonitor.swift        vm_statistics64 (HOST_VM_INFO64); sysctlbyname for swap
│   ├── NetworkMonitor.swift       getifaddrs per-interface byte deltas + IPv4 addresses
│   ├── DiskMonitor.swift          FileManager (space) + IOBlockStorageDriver (I/O rates)
│   ├── BatteryMonitor.swift       IOKit PowerSources + AppleSmartBattery (wattage via I×V)
│   ├── GPUMonitor.swift           IOKit IOGPU (Apple Silicon) / IOAccelerator (Intel/AMD)
│   └── SystemInfoMonitor.swift    ProcessInfo.thermalState + kern.boottime sysctl
│
├── Views/
│   ├── Components/                Reusable, stateless SwiftUI primitives
│   │   ├── ArcGaugeView.swift     Circular progress ring with tint + centre text
│   │   ├── SparklineView.swift    60-sample mini line-chart drawn with Canvas
│   │   ├── SectionHeader.swift    Icon + title row with copy-to-clipboard button
│   │   └── MetricRow.swift        Single label → value row
│   │
│   ├── Sections/                  One view per monitoring domain
│   │   ├── CPUSectionView.swift   Gauge + sparkline + rows + top processes (right-click to quit)
│   │   ├── MemorySectionView.swift  Gauge + sparkline + 7 metric rows
│   │   ├── NetworkSectionView.swift Rates + totals + per-interface breakdown with IPs
│   │   ├── DiskSectionView.swift  Gauge + space + I/O rates
│   │   ├── BatterySectionView.swift Gauge + status + time + cycles + health + watts
│   │   ├── GPUSectionView.swift   Gauge + sparkline + Device/Renderer/Tiler rows
│   │   └── SystemInfoSectionView.swift Thermal state (colour dot) + uptime
│   │
│   ├── ContentView.swift          480×720 pt tabbed popup (Usage · I/O · System) + footer
│   ├── SettingsView.swift         Refresh, label, alerts, visible-section toggles, login
│   └── AboutView.swift            App icon + version + description panel
│
└── Utilities/
    └── Formatters.swift           fmtBytes() and fmtRate() helpers
```

## Notes

- **Thread count** is prefixed with `~` because ~40% of processes are root-owned system daemons that return `EPERM` for all public APIs. Activity Monitor uses a private Apple entitlement (`task_for_pid-allow`). The displayed count is a lower bound.
- **Memory Used** = App Memory + Wired + Compressed, matching Activity Monitor's definition.
- **App Memory** = `(internal_page_count − purgeable_count) × pageSize` (anonymous app-owned pages only).
- **Network** byte counters are 32-bit (`if_data.ifi_obytes/ibytes`); they wrap at 4 GB. Rate calculations remain accurate because only short-interval deltas are used.
- **GPU** metrics are read from the `PerformanceStatistics` dictionary in the IOKit `IOGPU` service (Apple Silicon) or `IOAccelerator` service (Intel/AMD). If neither is accessible the section shows a "not available" message.
- **Battery wattage** is calculated as `|current (mA) × voltage (mV)| / 1 000 000`. Values come from `IOPSGetPowerSourceDescription` and are only shown when the hardware exposes them.
- **Thermal state** comes from `ProcessInfo.thermalState` (`.nominal` / `.fair` / `.serious` / `.critical`).
- **Force Quit** sends `SIGTERM` to the selected process. The system only permits terminating processes owned by the current user; root-owned daemons will silently ignore it.
- **Disk I/O** is read from `IOBlockStorageDriver` via IOKit; values reflect all block storage devices combined.
- **Launch at Login** uses `SMAppService.mainApp` (macOS 13+) and only works when the app is installed in `/Applications` or `~/Applications`.

## Planned / Future Features

- **Longer history & detail view** — tap a sparkline to expand it into a full per-session trend graph
- **WidgetKit extension** — Lock Screen / Desktop widget for at-a-glance stats
- **CPU/GPU power draw in watts** — requires `IOReport` (undocumented API); currently blocked on Apple Silicon without private entitlements

## License

MIT — see [LICENSE](LICENSE).
