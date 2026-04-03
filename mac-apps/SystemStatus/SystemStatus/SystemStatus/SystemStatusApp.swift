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

        Window("About SystemStatus", id: "about") {
            AboutView()
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
    }
}

// MARK: - MenuBarLabel

// Reads UserDefaults directly inside body — no observers needed.
// Re-renders on every timer tick so the mode is always current.
private struct MenuBarLabel: View {
    let monitor: SystemMonitor

    private var memPct: Int {
        guard monitor.memoryStats.physicalMemory > 0 else { return 0 }
        return Int(Double(monitor.memoryStats.memoryUsed) /
                   Double(monitor.memoryStats.physicalMemory) * 100)
    }

    /// Colour reflects the highest load across CPU and memory.
    private var pressureColor: Color {
        let maxLoad = max(Int(monitor.cpuStats.totalUsedPercent), memPct)
        switch maxLoad {
        case ..<50: return .green
        case ..<80: return .orange
        default:    return .red
        }
    }

    var body: some View {
        let mode = UserDefaults.standard.string(forKey: "menuBarLabel") ?? "cpu"
        HStack(spacing: 4) {
            // Colour-coded status dot
            Circle()
                .fill(pressureColor)
                .frame(width: 6, height: 6)
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
