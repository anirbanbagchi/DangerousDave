//
//  BatterySectionView.swift
//  SystemStatus
//
//  Only rendered when batteryStats.isPresent == true.
//

import SwiftUI

struct BatterySectionView: View {
    let stats: BatteryStats

    private var tint: Color {
        switch stats.percentage {
        case 21...: return stats.isCharging ? .green : .blue
        case 11...20: return .orange
        default:      return .red
        }
    }

    private var statusLabel: String {
        if stats.isCharging { return "Charging ⚡" }
        if stats.isPluggedIn { return "Plugged In" }
        return "On Battery"
    }

    private var timeLabel: String {
        guard stats.timeRemaining > 0 else { return "Calculating…" }
        let h = stats.timeRemaining / 60
        let m = stats.timeRemaining % 60
        if h > 0 { return "\(h)h \(m)m" }
        return "\(m)m"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Battery", systemImage: "battery.100percent", copyText: copyText)

            HStack(alignment: .top, spacing: 16) {
                ArcGaugeView(
                    fraction:   Double(stats.percentage) / 100.0,
                    label:      "Battery",
                    centerText: "\(stats.percentage)%",
                    tint:       tint
                )

                VStack(alignment: .leading, spacing: 5) {
                    MetricRow(label: "Status",  value: statusLabel)
                    MetricRow(label: stats.isCharging ? "Until Full" : "Time Left",
                              value: timeLabel)
                    MetricRow(label: "Cycles",  value: "\(stats.cycleCount)")
                    MetricRow(label: "Health",  value: stats.healthCondition)
                    if stats.powerWatts > 0 {
                        MetricRow(label: "Power",
                                  value: String(format: "%.1f W", stats.powerWatts))
                    }
                }
            }
        }
        .padding(16)
    }

    private var copyText: String {
        var text = """
        Battery
        Charge:    \(stats.percentage)%
        Status:    \(statusLabel)
        Time:      \(timeLabel)
        Cycles:    \(stats.cycleCount)
        Health:    \(stats.healthCondition)
        """
        if stats.powerWatts > 0 {
            text += "\nPower:     \(String(format: "%.1f W", stats.powerWatts))"
        }
        return text
    }
}
