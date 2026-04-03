//
//  NetworkMonitor.swift
//  SystemStatus
//
//  Measures upload/download throughput by diffing getifaddrs byte counters
//  across all active, non-loopback network interfaces.
//

import Foundation
import Darwin

struct NetworkStats {
    var uploadBytesPerSec: Double   = 0
    var downloadBytesPerSec: Double = 0
    var totalBytesSent: UInt64      = 0
    var totalBytesReceived: UInt64  = 0
}

final class NetworkMonitor {
    private var previousSent: UInt64 = 0
    private var previousRecv: UInt64 = 0
    private var previousTime: Date?

    func update() -> NetworkStats {
        let (sent, recv) = interfaceBytes()
        let now = Date()
        var stats = NetworkStats(totalBytesSent: sent, totalBytesReceived: recv)

        if let prev = previousTime {
            let dt = now.timeIntervalSince(prev)
            if dt > 0 {
                if sent >= previousSent { stats.uploadBytesPerSec   = Double(sent - previousSent) / dt }
                if recv >= previousRecv { stats.downloadBytesPerSec = Double(recv - previousRecv) / dt }
            }
        }
        previousSent = sent
        previousRecv = recv
        previousTime = now
        return stats
    }

    // Sums ibytes/obytes across every active, non-loopback AF_LINK entry.
    private func interfaceBytes() -> (sent: UInt64, recv: UInt64) {
        var totalSent: UInt64 = 0
        var totalRecv: UInt64 = 0
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0 else { return (0, 0) }
        defer { freeifaddrs(ifaddr) }
        var ptr = ifaddr
        while let cur = ptr {
            defer { ptr = cur.pointee.ifa_next }
            let flags = Int32(cur.pointee.ifa_flags)
            guard (flags & IFF_LOOPBACK) == 0, (flags & IFF_UP) != 0 else { continue }
            guard let sa = cur.pointee.ifa_addr, sa.pointee.sa_family == UInt8(AF_LINK) else { continue }
            guard let data = cur.pointee.ifa_data?.assumingMemoryBound(to: if_data.self) else { continue }
            totalSent += UInt64(data.pointee.ifi_obytes)
            totalRecv += UInt64(data.pointee.ifi_ibytes)
        }
        return (totalSent, totalRecv)
    }
}
