//
//  ContentView.swift
//  SystemStatus
//
//  Root view rendered inside the MenuBarExtra popover.
//  Three tabs — Usage / I/O / System — so all sections fit without scrolling.
//  Section visibility is driven by @AppStorage toggles set in SettingsView.
//

import SwiftUI

// MARK: - Tab definition

enum MonitorTab: String, CaseIterable {
    case usage  = "Usage"
    case io     = "I/O"
    case system = "System"
}

// MARK: - ContentView

struct ContentView: View {
    let monitor: SystemMonitor
    @State private var selectedTab: MonitorTab = .usage

    @Environment(\.openSettings) private var openSettings
    @Environment(\.openWindow)   private var openWindow

    // Section visibility — mirrors keys in SettingsView
    @AppStorage("sectionShowCPU")        private var showCPU        = true
    @AppStorage("sectionShowMemory")     private var showMemory     = true
    @AppStorage("sectionShowGPU")        private var showGPU        = true
    @AppStorage("sectionShowNetwork")    private var showNetwork    = true
    @AppStorage("sectionShowDisk")       private var showDisk       = true
    @AppStorage("sectionShowBattery")    private var showBattery    = true
    @AppStorage("sectionShowSystemInfo") private var showSystemInfo = true

    var body: some View {
        VStack(spacing: 0) {
            // Tab picker
            Picker("", selection: $selectedTab) {
                ForEach(MonitorTab.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            Divider()

            ScrollView(.vertical, showsIndicators: false) {
                switch selectedTab {
                case .usage:  usageTab
                case .io:     ioTab
                case .system: systemTab
                }
            }

            Divider()

            // Footer
            HStack {
                Text("SystemStatus")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Spacer()
                Button("About") {
                    NSApp.activate(ignoringOtherApps: true)
                    openWindow(id: "about")
                }
                .font(.caption).buttonStyle(.plain).foregroundStyle(.secondary)
                Text("|").font(.caption2).foregroundStyle(.tertiary)
                Button("Settings") { openSettings() }
                    .font(.caption).buttonStyle(.plain).foregroundStyle(.secondary)
                Text("|").font(.caption2).foregroundStyle(.tertiary)
                Button("Quit") { NSApplication.shared.terminate(nil) }
                    .font(.caption).buttonStyle(.plain).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .frame(width: 480, height: 720)
    }

    // MARK: - Tabs

    @ViewBuilder
    private var usageTab: some View {
        VStack(spacing: 0) {
            if showCPU {
                CPUSectionView(
                    stats:        monitor.cpuStats,
                    history:      monitor.cpuHistory,
                    topProcesses: monitor.topProcesses
                )
                Divider()
            }
            if showMemory {
                MemorySectionView(stats: monitor.memoryStats, history: monitor.memoryHistory)
                Divider()
            }
            if showGPU {
                GPUSectionView(stats: monitor.gpuStats, history: monitor.gpuHistory)
            }
            if !showCPU && !showMemory && !showGPU { emptyTab }
        }
    }

    @ViewBuilder
    private var ioTab: some View {
        VStack(spacing: 0) {
            if showNetwork {
                NetworkSectionView(
                    stats:           monitor.networkStats,
                    uploadHistory:   monitor.uploadHistory,
                    downloadHistory: monitor.downloadHistory
                )
                Divider()
            }
            if showDisk {
                DiskSectionView(stats: monitor.diskStats)
            }
            if !showNetwork && !showDisk { emptyTab }
        }
    }

    @ViewBuilder
    private var systemTab: some View {
        VStack(spacing: 0) {
            if showBattery && monitor.batteryStats.isPresent {
                BatterySectionView(stats: monitor.batteryStats)
                Divider()
            }
            if showSystemInfo {
                SystemInfoSectionView(stats: monitor.systemInfoStats)
            }
            if !showSystemInfo && !(showBattery && monitor.batteryStats.isPresent) { emptyTab }
        }
    }

    private var emptyTab: some View {
        Text("All sections hidden — re-enable them in Settings.")
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(24)
    }
}

#Preview {
    ContentView(monitor: SystemMonitor())
}
