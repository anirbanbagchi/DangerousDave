//
//  DiskMonitor.swift
//  SystemStatus
//
//  Reports boot-volume free/used space and read/write throughput.
//  Space comes from FileManager; I/O rates from IOBlockStorageDriver via IOKit.
//

import Foundation
import IOKit

struct DiskStats {
    var totalSpace: UInt64         = 0
    var usedSpace: UInt64          = 0
    var freeSpace: UInt64          = 0
    var readBytesPerSec: Double    = 0
    var writeBytesPerSec: Double   = 0

    var usedFraction: Double { totalSpace > 0 ? Double(usedSpace) / Double(totalSpace) : 0 }
}

final class DiskMonitor {
    private var previousRead: UInt64 = 0
    private var previousWrite: UInt64 = 0
    private var previousTime: Date?

    func update() -> DiskStats {
        var stats = DiskStats()

        // Boot-volume space via FileManager
        if let attrs = try? FileManager.default.attributesOfFileSystem(forPath: "/"),
           let total = (attrs[.systemSize] as? NSNumber)?.uint64Value,
           let free  = (attrs[.systemFreeSize] as? NSNumber)?.uint64Value {
            stats.totalSpace = total
            stats.freeSpace  = free
            stats.usedSpace  = total > free ? total - free : 0
        }

        // I/O throughput from IOBlockStorageDriver
        let (read, write) = blockStorageIO()
        let now = Date()
        if let prev = previousTime {
            let dt = now.timeIntervalSince(prev)
            if dt > 0 {
                if read  >= previousRead  { stats.readBytesPerSec  = Double(read  - previousRead)  / dt }
                if write >= previousWrite { stats.writeBytesPerSec = Double(write - previousWrite) / dt }
            }
        }
        previousRead  = read
        previousWrite = write
        previousTime  = now
        return stats
    }

    private func blockStorageIO() -> (read: UInt64, write: UInt64) {
        var totalRead: UInt64 = 0, totalWrite: UInt64 = 0
        var iter: io_iterator_t = 0
        guard IOServiceGetMatchingServices(kIOMainPortDefault,
                                           IOServiceMatching("IOBlockStorageDriver"),
                                           &iter) == KERN_SUCCESS else { return (0, 0) }
        defer { IOObjectRelease(iter) }
        var svc = IOIteratorNext(iter)
        while svc != IO_OBJECT_NULL {
            defer { IOObjectRelease(svc); svc = IOIteratorNext(iter) }
            var cfProps: Unmanaged<CFMutableDictionary>?
            guard IORegistryEntryCreateCFProperties(svc, &cfProps,
                                                    kCFAllocatorDefault, 0) == KERN_SUCCESS,
                  let dict    = cfProps?.takeRetainedValue() as? [String: Any],
                  let ioStats = dict["Statistics"] as? [String: Any] else { continue }
            if let r = ioStats["Bytes (Read)"]    as? UInt64 { totalRead  += r }
            if let w = ioStats["Bytes (Written)"] as? UInt64 { totalWrite += w }
        }
        return (totalRead, totalWrite)
    }
}
