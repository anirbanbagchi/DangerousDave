//
//  SystemInfoSectionView.swift
//  SystemStatus
//
//  Displays thermal state (with colour-coded indicator) and system uptime.
//

import SwiftUI

struct SystemInfoSectionView: View {
    let stats: SystemInfoStats

    private var thermalTint: Color {
        switch stats.thermalState {
        case .nominal:   return .green
        case .fair:      return .yellow
        case .serious:   return .orange
        case .critical:  return .red
        @unknown default: return .secondary
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "System", systemImage: "info.circle", copyText: copyText)

            VStack(alignment: .leading, spacing: 5) {
                // Thermal state with colour dot
                HStack(spacing: 4) {
                    Text("Thermal")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    Circle()
                        .fill(thermalTint)
                        .frame(width: 8, height: 8)
                    Text(stats.thermalLabel)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .lineLimit(1)
                }
                MetricRow(label: "Uptime", value: stats.formattedUptime)
            }
        }
        .padding(16)
    }

    private var copyText: String {
        "System\nThermal: \(stats.thermalLabel)\nUptime:  \(stats.formattedUptime)"
    }
}
