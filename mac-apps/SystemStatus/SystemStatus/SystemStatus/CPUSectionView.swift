//
//  CPUSectionView.swift
//  SystemStatus
//
//  Displays CPU usage — arc gauge, user/system/idle breakdown,
//  a sparkline history chart, thread/process counts, and top-5 processes by memory.
//

import SwiftUI

struct CPUSectionView: View {
    let stats: CPUStats
    let history: [Double]
    let topProcesses: [TopProcess]

    // Gauge colour shifts from blue → orange → red as load rises.
    private var tint: Color {
        switch stats.totalUsedPercent {
        case ..<50:  return .blue
        case ..<80:  return .orange
        default:     return .red
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "CPU", systemImage: "cpu", copyText: copyText)

            // Sparkline
            if history.count >= 2 {
                SparklineView(values: history, color: tint)
                    .frame(height: 28)
            }

            HStack(alignment: .top, spacing: 16) {
                // Circular gauge
                ArcGaugeView(
                    fraction:   stats.totalUsedPercent / 100.0,
                    label:      "CPU",
                    centerText: String(format: "%.0f%%", stats.totalUsedPercent),
                    tint:       tint
                )

                // Metric detail column
                VStack(alignment: .leading, spacing: 5) {
                    MetricRow(label: "User",
                              value: String(format: "%.2f%%", stats.userPercent))
                    MetricRow(label: "System",
                              value: String(format: "%.2f%%", stats.systemPercent))
                    MetricRow(label: "Idle",
                              value: String(format: "%.2f%%", stats.idlePercent))

                    Divider().padding(.vertical, 1)

                    // Threads + Processes on one line.
                    // Thread count prefixed "~" — root-owned daemons return EPERM.
                    HStack(spacing: 4) {
                        Text("Threads")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                        Text("~\(stats.threadCount.formatted())")
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        Spacer()
                        Text("Processes")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                        Text(stats.processCount.formatted())
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    }
                }
            }

            // Top processes by memory
            if !topProcesses.isEmpty {
                Divider().padding(.top, 2)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Top Processes")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.tertiary)
                        .padding(.bottom, 1)
                    ForEach(topProcesses) { proc in
                        HStack(spacing: 4) {
                            Text(proc.name)
                                .font(.system(size: 11))
                                .foregroundStyle(.primary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                            Spacer(minLength: 4)
                            Text(fmtBytes(proc.memoryBytes))
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding(16)
    }

    private var copyText: String {
        var lines = [
            "CPU",
            "User:      \(String(format: "%.2f%%", stats.userPercent))",
            "System:    \(String(format: "%.2f%%", stats.systemPercent))",
            "Idle:      \(String(format: "%.2f%%", stats.idlePercent))",
            "Threads:   ~\(stats.threadCount)",
            "Processes: \(stats.processCount)",
        ]
        if !topProcesses.isEmpty {
            lines.append("Top Processes (by memory):")
            for p in topProcesses {
                lines.append("  \(p.name): \(fmtBytes(p.memoryBytes))")
            }
        }
        return lines.joined(separator: "\n")
    }
}
