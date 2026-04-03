//
//  SettingsView.swift
//  SystemStatus
//
//  Preferences window: refresh rate, menu bar label style, alerts, launch at login.
//

import SwiftUI
import ServiceManagement

struct SettingsView: View {
    // Refresh interval
    @AppStorage("refreshInterval") private var refreshInterval: Double = 3.0

    // Menu bar label
    @AppStorage("menuBarLabel") private var menuBarLabel: String = "cpu"

    // Alerts
    @AppStorage("alertCPUEnabled")     private var alertCPUEnabled: Bool     = false
    @AppStorage("alertCPUThreshold")   private var alertCPUThreshold: Double = 90
    @AppStorage("alertMemoryEnabled")  private var alertMemEnabled: Bool     = false
    @AppStorage("alertMemThreshold")   private var alertMemThreshold: Double = 85

    @State private var launchAtLogin  = false
    @State private var loginItemError: String?

    private let intervals: [(String, Double)] = [
        ("1 second", 1), ("2 seconds", 2), ("3 seconds", 3),
        ("5 seconds", 5), ("10 seconds", 10),
    ]
    private let labelOptions: [(String, String)] = [
        ("CPU %",       "cpu"),
        ("Memory %",    "memory"),
        ("CPU & Memory","both"),
        ("Icon only",   "icon"),
    ]

    var body: some View {
        Form {
            // MARK: General
            Section {
                Toggle("Launch at Login", isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { _, enabled in
                        do {
                            if enabled { try SMAppService.mainApp.register()   }
                            else       { try SMAppService.mainApp.unregister() }
                            loginItemError = nil
                        } catch {
                            loginItemError = error.localizedDescription
                            // Revert toggle on failure
                            launchAtLogin = !enabled
                        }
                    }
                if let err = loginItemError {
                    Text(err)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            } header: { Text("General") }

            // MARK: Menu Bar
            Section {
                Picker("Show in menu bar", selection: $menuBarLabel) {
                    ForEach(labelOptions, id: \.1) { label, value in
                        Text(label).tag(value)
                    }
                }
            } header: { Text("Menu Bar") }

            // MARK: Refresh Rate
            Section {
                Picker("Refresh interval", selection: $refreshInterval) {
                    ForEach(intervals, id: \.1) { label, value in
                        Text(label).tag(value)
                    }
                }
                .pickerStyle(.radioGroup)
            } header: { Text("Update Frequency") }
              footer: { Text("How often CPU, memory, network and disk stats are refreshed.") }

            // MARK: Alerts
            Section {
                Toggle("Alert when CPU usage exceeds", isOn: $alertCPUEnabled)
                if alertCPUEnabled {
                    HStack {
                        Slider(value: $alertCPUThreshold, in: 50...99, step: 5)
                        Text("\(Int(alertCPUThreshold))%")
                            .font(.system(.body, design: .monospaced))
                            .frame(width: 40, alignment: .trailing)
                    }
                }
                Toggle("Alert when memory usage exceeds", isOn: $alertMemEnabled)
                if alertMemEnabled {
                    HStack {
                        Slider(value: $alertMemThreshold, in: 50...99, step: 5)
                        Text("\(Int(alertMemThreshold))%")
                            .font(.system(.body, design: .monospaced))
                            .frame(width: 40, alignment: .trailing)
                    }
                }
            } header: { Text("Alerts") }
              footer: { Text("Notifications are sent at most once every 5 minutes per category.") }
        }
        .formStyle(.grouped)
        .frame(width: 360)
        .padding(.vertical, 8)
        .onAppear {
            launchAtLogin = SMAppService.mainApp.status == .enabled
        }
    }
}

#Preview { SettingsView() }
