//
//  SystemStatusApp.swift
//  SystemStatus
//

import SwiftUI

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationWillFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
    }
}

@main
struct SystemStatusApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var monitor = SystemMonitor()

    var body: some Scene {
        MenuBarExtra {
            ContentView(monitor: monitor)
        } label: {
            MenuBarLabel(monitor: monitor)
        }
        .menuBarExtraStyle(.window)

        Settings {
            SettingsView()
        }
    }
}

// Private label view for the menu bar status item.
// Reads UserDefaults directly inside body — no observers needed.
// The view re-renders on every timer tick (as cpuStats / memoryStats change),
// so the mode is always current within one refresh cycle.
private struct MenuBarLabel: View {
    let monitor: SystemMonitor

    private var memPct: Int {
        guard monitor.memoryStats.physicalMemory > 0 else { return 0 }
        return Int(Double(monitor.memoryStats.memoryUsed) / Double(monitor.memoryStats.physicalMemory) * 100)
    }

    var body: some View {
        // Read fresh on every render — no stale cached value possible.
        let mode = UserDefaults.standard.string(forKey: "menuBarLabel") ?? "cpu"
        HStack(spacing: 3) {
            Image(systemName: "cpu")
            if mode == "cpu" || mode == "both" {
                Text(String(format: "%d%%", Int(monitor.cpuStats.totalUsedPercent)))
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
            }
            if mode == "memory" || mode == "both" {
                Text(String(format: "%d%%", memPct))
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(mode == "both" ? .secondary : .primary)
            }
        }
    }
}
