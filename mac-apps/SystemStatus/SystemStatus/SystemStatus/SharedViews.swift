//
//  SharedViews.swift
//  SystemStatus
//
//  Reusable UI components and formatting helpers used across section views.
//

import SwiftUI

// MARK: - ArcGaugeView

/// A circular progress ring with a label and centre text.
struct ArcGaugeView: View {
    let fraction: Double    // 0.0 – 1.0
    let label: String
    let centerText: String
    let tint: Color

    var body: some View {
        ZStack {
            // Track ring
            Circle()
                .stroke(tint.opacity(0.15),
                        style: StrokeStyle(lineWidth: 8, lineCap: .round))

            // Progress ring
            Circle()
                .trim(from: 0, to: min(max(fraction, 0), 1))
                .stroke(tint, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeInOut(duration: 0.35), value: fraction)

            // Centre text
            VStack(spacing: 1) {
                Text(centerText)
                    .font(.system(size: 15, weight: .semibold, design: .monospaced))
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
                Text(label)
                    .font(.system(size: 8, weight: .regular))
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 80, height: 80)
    }
}

// MARK: - SparklineView

/// A mini line-chart of the last N percentage samples (0–100), drawn with Canvas.
struct SparklineView: View {
    let values: [Double]
    let color: Color
    var lineWidth: CGFloat = 1.5

    var body: some View {
        Canvas { ctx, size in
            guard values.count >= 2 else { return }
            let pts: [CGPoint] = values.enumerated().map { i, v in
                CGPoint(
                    x: size.width  * CGFloat(i) / CGFloat(values.count - 1),
                    y: size.height * (1.0 - CGFloat(max(0, min(v, 100))) / 100.0)
                )
            }
            // Gradient fill
            var fill = Path()
            fill.move(to: CGPoint(x: pts[0].x, y: size.height))
            fill.addLine(to: pts[0])
            for pt in pts.dropFirst() { fill.addLine(to: pt) }
            fill.addLine(to: CGPoint(x: pts.last!.x, y: size.height))
            fill.closeSubpath()
            ctx.fill(fill, with: .color(color.opacity(0.12)))
            // Line
            var line = Path()
            line.move(to: pts[0])
            for pt in pts.dropFirst() { line.addLine(to: pt) }
            ctx.stroke(line, with: .color(color.opacity(0.85)), lineWidth: lineWidth)
        }
        .animation(.easeInOut(duration: 0.3), value: values.last ?? 0)
    }
}

// MARK: - SectionHeader

/// Standard section header row: icon + title on the left, copy-to-clipboard on the right.
struct SectionHeader: View {
    let title: String
    let systemImage: String
    let copyText: String
    @State private var copied = false

    var body: some View {
        HStack {
            Label(title, systemImage: systemImage)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(copyText, forType: .string)
                withAnimation { copied = true }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                    withAnimation { copied = false }
                }
            } label: {
                Image(systemName: copied ? "checkmark" : "doc.on.clipboard")
                    .font(.system(size: 10))
                    .foregroundStyle(copied ? .green : .secondary)
            }
            .buttonStyle(.plain)
            .help("Copy to clipboard")
        }
    }
}

// MARK: - MetricRow

/// A single-line label → spacer → value row used in all section views.
struct MetricRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer(minLength: 4)
            Text(value)
                .font(.system(size: 12, weight: .medium, design: .monospaced))
                .lineLimit(1)
        }
    }
}

// MARK: - Formatting helpers

/// Human-readable byte size (B / KB / MB / GB).
func fmtBytes(_ bytes: UInt64) -> String {
    let gb = Double(bytes) / 1_073_741_824.0
    if gb >= 1  { return String(format: "%.2f GB", gb) }
    let mb = Double(bytes) / 1_048_576.0
    if mb >= 1  { return String(format: "%.0f MB", mb) }
    let kb = Double(bytes) / 1_024.0
    if kb >= 1  { return String(format: "%.0f KB", kb) }
    return "\(bytes) B"
}

/// Human-readable bytes-per-second rate.
func fmtRate(_ bps: Double) -> String {
    if bps >= 1_073_741_824 { return String(format: "%.1f GB/s", bps / 1_073_741_824) }
    if bps >= 1_048_576     { return String(format: "%.1f MB/s", bps / 1_048_576) }
    if bps >= 1_024         { return String(format: "%.0f KB/s", bps / 1_024) }
    return String(format: "%.0f B/s", bps)
}
