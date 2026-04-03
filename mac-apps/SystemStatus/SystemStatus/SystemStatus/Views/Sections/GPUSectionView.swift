//
//  GPUSectionView.swift
//  SystemStatus
//
//  Displays GPU utilization — arc gauge, sparkline, and pipeline breakdown.
//  Shows a "not available" message on systems where IOKit IOGPU is inaccessible.
//

import SwiftUI

struct GPUSectionView: View {
    let stats: GPUStats
    let history: [Double]

    private var tint: Color {
        switch stats.deviceUtilization {
        case ..<50:  return .purple
        case ..<80:  return .orange
        default:     return .red
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "GPU", systemImage: "display", copyText: copyText)

            if stats.isAvailable {
                if history.count >= 2 {
                    SparklineView(values: history, color: tint)
                        .frame(height: 28)
                }
                HStack(alignment: .top, spacing: 16) {
                    ArcGaugeView(
                        fraction:   stats.deviceUtilization / 100.0,
                        label:      "GPU",
                        centerText: String(format: "%.0f%%", stats.deviceUtilization),
                        tint:       tint
                    )
                    VStack(alignment: .leading, spacing: 5) {
                        MetricRow(label: "Device",   value: String(format: "%.0f%%", stats.deviceUtilization))
                        MetricRow(label: "Renderer", value: String(format: "%.0f%%", stats.rendererUtilization))
                        MetricRow(label: "Tiler",    value: String(format: "%.0f%%", stats.tilerUtilization))
                    }
                }
            } else {
                HStack(spacing: 8) {
                    Image(systemName: "display.slash")
                        .foregroundStyle(.secondary)
                    Text("GPU metrics are not available on this system.")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(16)
    }

    private var copyText: String {
        guard stats.isAvailable else { return "GPU: Not available" }
        return """
        GPU
        Device:    \(String(format: "%.0f%%", stats.deviceUtilization))
        Renderer:  \(String(format: "%.0f%%", stats.rendererUtilization))
        Tiler:     \(String(format: "%.0f%%", stats.tilerUtilization))
        """
    }
}
