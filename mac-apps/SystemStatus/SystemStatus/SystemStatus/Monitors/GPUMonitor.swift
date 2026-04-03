//
//  GPUMonitor.swift
//  SystemStatus
//
//  Reads GPU utilization from the IOKit IOGPU service (Apple Silicon) or
//  IOAccelerator (Intel/AMD). Falls back gracefully when neither is available.
//

import IOKit

final class GPUMonitor {
    // Known key variants across chip generations and macOS releases.
    private static let deviceKeys   = ["Device Utilization (%)", "GPU Activity(%)"]
    private static let rendererKeys = ["Renderer Utilization (%)", "Renderer Utilization(%)"]
    private static let tilerKeys    = ["Tiler Utilization (%)", "Tiler Utilization(%)"]

    func update() -> GPUStats {
        for service in ["IOGPU", "IOAccelerator"] {
            if let stats = readStats(serviceName: service), stats.isAvailable {
                return stats
            }
        }
        return GPUStats()
    }

    private func readStats(serviceName: String) -> GPUStats? {
        var iter: io_iterator_t = 0
        guard IOServiceGetMatchingServices(kIOMainPortDefault,
              IOServiceMatching(serviceName), &iter) == KERN_SUCCESS else { return nil }
        defer { IOObjectRelease(iter) }

        let svc = IOIteratorNext(iter)
        guard svc != IO_OBJECT_NULL else { return nil }
        defer { IOObjectRelease(svc) }

        var cfProps: Unmanaged<CFMutableDictionary>?
        guard IORegistryEntryCreateCFProperties(svc, &cfProps,
              kCFAllocatorDefault, 0) == KERN_SUCCESS,
              let dict = cfProps?.takeRetainedValue() as? [String: Any],
              let perf = dict["PerformanceStatistics"] as? [String: Any] else { return nil }

        var stats = GPUStats(isAvailable: true)
        stats.deviceUtilization   = numericValue(from: perf, keys: Self.deviceKeys)
        stats.rendererUtilization = numericValue(from: perf, keys: Self.rendererKeys)
        stats.tilerUtilization    = numericValue(from: perf, keys: Self.tilerKeys)
        return stats
    }

    private func numericValue(from dict: [String: Any], keys: [String]) -> Double {
        for key in keys {
            if let v = dict[key] as? Double { return v }
            if let v = dict[key] as? Int    { return Double(v) }
        }
        return 0
    }
}
