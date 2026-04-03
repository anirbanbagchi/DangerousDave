//
//  SparklineView.swift
//  SystemStatus
//
//  A mini line-chart of the last N percentage samples (0–100), drawn with Canvas.
//

import SwiftUI

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
            // Gradient fill under the line
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
