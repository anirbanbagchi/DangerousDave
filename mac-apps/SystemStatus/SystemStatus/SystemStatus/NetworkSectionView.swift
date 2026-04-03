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
        }
        .padding(16)
    }

    private var copyText: String {
        """
        Network
        Upload:          \(fmtRate(stats.uploadBytesPerSec))
        Download:        \(fmtRate(stats.downloadBytesPerSec))
        Total Sent:      \(fmtBytes(stats.totalBytesSent))
        Total Received:  \(fmtBytes(stats.totalBytesReceived))
        """
    }
}
