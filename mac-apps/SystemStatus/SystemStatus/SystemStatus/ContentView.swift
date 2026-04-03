//
//  ContentView.swift
//  SystemStatus
//
//  Root view rendered inside the MenuBarExtra popover.
//  Scrollable, 440 pt wide, up to 520 pt tall.
//

import SwiftUI

struct ContentView: View {
    let monitor: SystemMonitor
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(spacing: 0) {
                CPUSectionView(
                    stats:        monitor.cpuStats,
                    history:      monitor.cpuHistory,
                    topProcesses: monitor.topProcesses
                )

                Divider()

                MemorySectionView(
                    stats:   monitor.memoryStats,
                    history: monitor.memoryHistory
                )

                Divider()

                NetworkSectionView(
                    stats:           monitor.networkStats,
                    uploadHistory:   monitor.uploadHistory,
                    downloadHistory: monitor.downloadHistory
                )

                Divider()

                DiskSectionView(stats: monitor.diskStats)

                if monitor.batteryStats.isPresent {
                    Divider()
                    BatterySectionView(stats: monitor.batteryStats)
                }

                Divider()

                // Footer
                HStack {
                    Text("SystemStatus")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Spacer()
                    Button("Settings…") { openSettings() }
                        .font(.caption)
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                    Text("·")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Button("Quit") { NSApplication.shared.terminate(nil) }
                        .font(.caption)
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
        }
        .frame(width: 440, height: 520)
    }
}

#Preview {
    ContentView(monitor: SystemMonitor())
}
