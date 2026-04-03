//
//  NetworkSectionView.swift
//  SystemStatus
//

import SwiftUI

struct NetworkSectionView: View {
    let stats: NetworkStats
    let uploadHistory: [Double]
    let downloadHistory: [Double]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Network", systemImage: "network", copyText: copyText)

            // Sparklines
            HStack(spacing: 4) {
                SparklineView(values: uploadHistory,   color: .blue)
                SparklineView(values: downloadHistory, color: .green)
            }
            .frame(height: 30)

            HStack(alignment: .top, spacing: 16) {
                // Up / Down rate cards
                HStack(spacing: 8) {
                    VStack(spacing: 3) {
                        Image(systemName: "arrow.up.circle.fill")
                            .foregroundStyle(.blue)
                            .font(.system(size: 18))
                        Text(fmtRate(stats.uploadBytesPerSec))
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .minimumScaleFactor(0.7)
                            .lineLimit(1)
                        Text("Upload")
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)

                    VStack(spacing: 3) {
                        Image(systemName: "arrow.down.circle.fill")
                            .foregroundStyle(.green)
                            .font(.system(size: 18))
                        Text(fmtRate(stats.downloadBytesPerSec))
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .minimumScaleFactor(0.7)
                            .lineLimit(1)
                        Text("Download")
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                }
                .frame(width: 160)

                VStack(alignment: .leading, spacing: 5) {
                    MetricRow(label: "Total Sent",     value: fmtBytes(stats.totalBytesSent))
                    MetricRow(label: "Total Received", value: fmtBytes(stats.totalBytesReceived))
                }
            }

            // Per-interface breakdown
            if !stats.interfaces.isEmpty {
                Divider().padding(.top, 2)
                Text("Active Interfaces")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.tertiary)
                ForEach(stats.interfaces) { iface in
                    HStack(spacing: 4) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(iface.name)
                                .font(.system(size: 11, weight: .semibold))
                            if !iface.ipv4Address.isEmpty {
                                Text(iface.ipv4Address)
                                    .font(.system(size: 9))
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        Spacer(minLength: 4)
                        VStack(alignment: .trailing, spacing: 1) {
                            Text("↑ \(fmtRate(iface.uploadBytesPerSec))")
                            Text("↓ \(fmtRate(iface.downloadBytesPerSec))")
                        }
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(16)
    }

    private var copyText: String {
        var lines = [
            "Network",
            "Upload:          \(fmtRate(stats.uploadBytesPerSec))",
            "Download:        \(fmtRate(stats.downloadBytesPerSec))",
            "Total Sent:      \(fmtBytes(stats.totalBytesSent))",
            "Total Received:  \(fmtBytes(stats.totalBytesReceived))",
        ]
        if !stats.interfaces.isEmpty {
            lines.append("Active Interfaces:")
            for i in stats.interfaces {
                lines.append("  \(i.name)\(i.ipv4Address.isEmpty ? "" : " (\(i.ipv4Address))"): ↑\(fmtRate(i.uploadBytesPerSec)) ↓\(fmtRate(i.downloadBytesPerSec))")
            }
        }
        return lines.joined(separator: "\n")
    }
}
