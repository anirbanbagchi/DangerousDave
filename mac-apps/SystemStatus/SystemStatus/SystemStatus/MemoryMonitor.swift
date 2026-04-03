//
//  MemoryMonitor.swift
//  SystemStatus
//
//  Reads vm_statistics64 + sysctlbyname to mirror Activity Monitor's
//  memory breakdown categories.
//

import Darwin

// MARK: - Data model

struct MemoryStats {
    var physicalMemory: UInt64 = 0   // hw.memsize
    var memoryUsed: UInt64     = 0   // appMemory + wired + compressed
    var appMemory: UInt64      = 0   // (internal_page_count − purgeable_count) × pageSize
    var wiredMemory: UInt64    = 0   // wire_count × pageSize – cannot be swapped or compressed
    var compressed: UInt64     = 0   // compressor_page_count × pageSize
    var cachedFiles: UInt64    = 0   // (external_page_count + purgeable_count) × pageSize
    var swapUsed: UInt64       = 0   // vm.swapusage.xsu_used
}

// MARK: - Monitor

final class MemoryMonitor {
    func update() -> MemoryStats {
        // --- Page size ---
        var pageSize: vm_size_t = 0
        host_page_size(mach_host_self(), &pageSize)
        let ps = UInt64(pageSize)

        // --- vm_statistics64 ---
        var vmStat = vm_statistics64()
        var count  = mach_msg_type_number_t(
            MemoryLayout<vm_statistics64>.stride / MemoryLayout<integer_t>.stride
        )
        let kr = withUnsafeMutablePointer(to: &vmStat) { ptr in
            ptr.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count)
            }
        }
        guard kr == KERN_SUCCESS else { return MemoryStats() }

        // --- Physical RAM total ---
        var physMem: UInt64 = 0
        var physMemSize = MemoryLayout<UInt64>.size
        sysctlbyname("hw.memsize", &physMem, &physMemSize, nil, 0)

        // --- Compute categories matching Activity Monitor ---
        //
        // Activity Monitor uses internal_page_count (anonymous, app-owned pages) for
        // "App Memory", NOT active_count (which also includes file-backed pages).
        // Likewise, external_page_count is the file cache shown as "Cached Files".
        //
        // App Memory   = (internal_page_count - purgeable_count) * pageSize
        // Cached Files = (external_page_count + purgeable_count) * pageSize
        // Memory Used  = App Memory + Wired + Compressed
        let internalPages  = UInt64(vmStat.internal_page_count)
        let externalPages  = UInt64(vmStat.external_page_count)
        let purgeablePages = UInt64(vmStat.purgeable_count)
        let wiredPages     = UInt64(vmStat.wire_count)
        let compPages      = UInt64(vmStat.compressor_page_count)

        let wired      = wiredPages * ps
        let compressor = compPages  * ps
        let appMem  = (internalPages > purgeablePages ? internalPages - purgeablePages : 0) * ps
        let cached  = (externalPages + purgeablePages) * ps
        let memUsed = appMem + wired + compressor

        // --- Swap usage ---
        var swapInfo = xsw_usage()
        var swapSize = MemoryLayout<xsw_usage>.size
        sysctlbyname("vm.swapusage", &swapInfo, &swapSize, nil, 0)

        return MemoryStats(
            physicalMemory: physMem,
            memoryUsed:     memUsed,
            appMemory:      appMem,
            wiredMemory:    wired,
            compressed:     compressor,
            cachedFiles:    cached,
            swapUsed:       swapInfo.xsu_used
        )
    }
}
