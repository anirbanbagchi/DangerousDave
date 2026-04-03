//
//  ArcGaugeView.swift
//  SystemStatus
//
//  A circular progress ring with a label and centre text.
//

import SwiftUI

/// A circular progress ring with a label and centre text.
struct ArcGaugeView: View {
    /// Progress value in the range 0.0–1.0.
    let fraction: Double
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
