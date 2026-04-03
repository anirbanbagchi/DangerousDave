//
//  MemorySectionView.swift
//  SystemStatus
//
//  Displays the full Activity Monitor–style memory breakdown:
//  sparkline, arc gauge (% used), and seven metric rows.
//

import SwiftUI

struct MemorySectionView: View {
    let stats: MemoryStats
    let history: [Double]

    private var fraction: Double {
        stats.physicalMemory > 0
            ? Double(stats.memoryUsed) / Double(stats.physicalMemory)
            : 0
    }

    // Gauge colour shifts from green → orange → red as pressure rises.
    private var tint: Color {
        switch fraction {
        case ..<0.7:  return .green
        case ..<0.9:  return .orange
        default:      return .red
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Memory", systemImage: "memorychip", copyText: copyText)

            // Sparkline
            if history.count >= 2 {
                SparklineView(values: history, color: tint)
                    .frame(height: 28)
            }

            HStack(alignment: .top, spacing: 16) {
                // Circular gauge
                ArcGaugeView(
                    fraction:   fraction,
                    label:      "Memory",
                    centerText: String(format: "%.0f%%", fraction * 100),
                    tint:       tint
                )

                // Metric detail column
                VStack(alignment: .leading, spacing: 5) {
                    MetricRow(label: "Physical Memory",
                              value: fmtBytes(stats.physicalMemory))
                    MetricRow(label: "Memory Used",
                              value: fmtBytes(stats.memoryUsed))
                    MetricRow(label: "App Memory",
                              value: fmtBytes(stats.appMemory))
                    MetricRow(label: "Wired Memory",
                              value: fmtBytes(stats.wiredMemory))
                    MetricRow(label: "Compressed",
                              value: fmtBytes(stats.compressed))
                    MetricRow(label: "Cached Files",
                              value: fmtBytes(stats.cachedFiles))
                    MetricRow(label: "Swap Used",
                              value: fmtBytes(stats.swapUsed))
                }
            }
        }
        .padding(16)
    }

    private var copyText: String {
        """
        Memory
        Physical Memory:  \(fmtBytes(stats.physicalMemory))
        Memory Used:      \(fmtBytes(stats.memoryUsed))
        App Memory:       \(fmtBytes(stats.appMemory))
        Wired Memory:     \(fmtBytes(stats.wiredMemory))
        Compressed:       \(fmtBytes(stats.compressed))
        Cached Files:     \(fmtBytes(stats.cachedFiles))
        Swap Used:        \(fmtBytes(stats.swapUsed))
        """
    }
}
