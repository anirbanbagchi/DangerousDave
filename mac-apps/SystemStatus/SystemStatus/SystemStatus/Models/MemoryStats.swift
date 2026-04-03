//
//  MemoryStats.swift
//  SystemStatus
//
//  Memory usage data model mirroring Activity Monitor's breakdown.
//

import Foundation

/// Memory usage statistics mirroring Activity Monitor's categories.
struct MemoryStats {
    var physicalMemory: UInt64 = 0   // hw.memsize
    var memoryUsed: UInt64     = 0   // appMemory + wired + compressed
    var appMemory: UInt64      = 0   // (internal_page_count − purgeable_count) × pageSize
    var wiredMemory: UInt64    = 0   // wire_count × pageSize — cannot be swapped or compressed
    var compressed: UInt64     = 0   // compressor_page_count × pageSize
    var cachedFiles: UInt64    = 0   // (external_page_count + purgeable_count) × pageSize
    var swapUsed: UInt64       = 0   // vm.swapusage.xsu_used
}
