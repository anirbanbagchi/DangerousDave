//
//  DiskSectionView.swift
//  SystemStatus
//

import SwiftUI

struct DiskSectionView: View {
    let stats: DiskStats

    private var tint: Color {
        switch stats.usedFraction {
        case ..<0.7:  return .blue
        case ..<0.9:  return .orange
        default:      return .red
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Disk", systemImage: "internaldrive", copyText: copyText)

            HStack(alignment: .top, spacing: 16) {
                ArcGaugeView(
                    fraction:   stats.usedFraction,
                    label:      "Used",
                    centerText: String(format: "%.0f%%", stats.usedFraction * 100),
                    tint:       tint
                )

                VStack(alignment: .leading, spacing: 5) {
                    MetricRow(label: "Total",   value: fmtBytes(stats.totalSpace))
                    MetricRow(label: "Used",    value: fmtBytes(stats.usedSpace))
                    MetricRow(label: "Free",    value: fmtBytes(stats.freeSpace))
                    Divider().padding(.vertical, 1)
                    MetricRow(label: "Read",    value: fmtRate(stats.readBytesPerSec))
                    MetricRow(label: "Written", value: fmtRate(stats.writeBytesPerSec))
                }
            }
        }
        .padding(16)
    }

    private var copyText: String {
        """
        Disk
        Total:    \(fmtBytes(stats.totalSpace))
        Used:     \(fmtBytes(stats.usedSpace))
        Free:     \(fmtBytes(stats.freeSpace))
        Read:     \(fmtRate(stats.readBytesPerSec))
        Written:  \(fmtRate(stats.writeBytesPerSec))
        """
    }
}
