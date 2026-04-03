//
//  NetworkStats.swift
//  SystemStatus
//
//  Network throughput data model — aggregate totals plus per-interface breakdown.
//

import Foundation

/// Per-network-interface upload/download rates and IPv4 address.
struct InterfaceStats: Identifiable {
    var id: String { name }
    let name: String
    var uploadBytesPerSec: Double   = 0
    var downloadBytesPerSec: Double = 0
    var ipv4Address: String         = ""
}

/// Aggregate network throughput and cumulative byte counters.
struct NetworkStats {
    var uploadBytesPerSec: Double   = 0
    var downloadBytesPerSec: Double = 0
    var totalBytesSent: UInt64      = 0
    var totalBytesReceived: UInt64  = 0
    /// Active interfaces sorted by descending combined throughput, capped at 3.
    var interfaces: [InterfaceStats] = []
}
