//
//  Formatters.swift
//  SystemStatus
//
//  Human-readable formatting helpers for byte sizes and data rates.
//

import Foundation

// MARK: - Byte Size

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

// MARK: - Data Rate

/// Human-readable bytes-per-second rate.
func fmtRate(_ bps: Double) -> String {
    if bps >= 1_073_741_824 { return String(format: "%.1f GB/s", bps / 1_073_741_824) }
    if bps >= 1_048_576     { return String(format: "%.1f MB/s", bps / 1_048_576) }
    if bps >= 1_024         { return String(format: "%.0f KB/s", bps / 1_024) }
    return String(format: "%.0f B/s", bps)
}
