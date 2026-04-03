//
//  SystemInfoMonitor.swift
//  SystemStatus
//
//  Reads macOS thermal state and system uptime.
//

import Foundation
import Darwin

final class SystemInfoMonitor {
    func update() -> SystemInfoStats {
        var stats = SystemInfoStats()
        stats.thermalState = ProcessInfo.processInfo.thermalState

        // System uptime via kern.boottime sysctl
        var tv   = timeval()
        var size = MemoryLayout<timeval>.size
        if sysctlbyname("kern.boottime", &tv, &size, nil, 0) == 0 {
            let bootDate = Date(timeIntervalSince1970: TimeInterval(tv.tv_sec))
            stats.uptimeSeconds = Date().timeIntervalSince(bootDate)
        }
        return stats
    }
}
