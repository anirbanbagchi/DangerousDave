//
//  MetricRow.swift
//  SystemStatus
//
//  A single-line label → value row used across all section views.
//

import SwiftUI

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
