//
//  DiskStats.swift
//  SystemStatus
//
//  Disk space and I/O throughput data model.
//

import Foundation

/// Boot-volume disk space and I/O throughput statistics.
struct DiskStats {
    var totalSpace: UInt64       = 0
    var usedSpace: UInt64        = 0
    var freeSpace: UInt64        = 0
    var readBytesPerSec: Double  = 0
    var writeBytesPerSec: Double = 0

    var usedFraction: Double { totalSpace > 0 ? Double(usedSpace) / Double(totalSpace) : 0 }
}
