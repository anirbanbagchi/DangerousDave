//
//  NetworkMonitor.swift
//  SystemStatus
//
//  Measures upload/download throughput by diffing getifaddrs byte counters
//  across all active, non-loopback network interfaces.
//  Also reports per-interface rates and IPv4 addresses.
//

import Foundation
import Darwin

final class NetworkMonitor {
    private var previousSent: UInt64 = 0
    private var previousRecv: UInt64 = 0
    private var previousIfBytes: [String: (sent: UInt64, recv: UInt64)] = [:]
    private var previousTime: Date?

    func update() -> NetworkStats {
        let (total, ifData) = interfaceData()
        let now = Date()
        var stats = NetworkStats(totalBytesSent: total.sent, totalBytesReceived: total.recv)

        if let prev = previousTime {
            let dt = now.timeIntervalSince(prev)
            if dt > 0 {
                if total.sent >= previousSent {
                    stats.uploadBytesPerSec   = Double(total.sent - previousSent) / dt
                }
                if total.recv >= previousRecv {
                    stats.downloadBytesPerSec = Double(total.recv - previousRecv) / dt
                }
                var interfaces: [InterfaceStats] = []
                for (name, current) in ifData {
                    let prev = previousIfBytes[name] ?? (0, 0)
                    var iface = InterfaceStats(name: name, ipv4Address: current.ip)
                    if current.sent >= prev.sent {
                        iface.uploadBytesPerSec   = Double(current.sent - prev.sent) / dt
                    }
                    if current.recv >= prev.recv {
                        iface.downloadBytesPerSec = Double(current.recv - prev.recv) / dt
                    }
                    if iface.uploadBytesPerSec + iface.downloadBytesPerSec > 0 {
                        interfaces.append(iface)
                    }
                }
                stats.interfaces = Array(
                    interfaces
                        .sorted { ($0.uploadBytesPerSec + $0.downloadBytesPerSec) >
                                  ($1.uploadBytesPerSec + $1.downloadBytesPerSec) }
                        .prefix(3)
                )
            }
        }
        previousSent     = total.sent
        previousRecv     = total.recv
        previousIfBytes  = ifData.mapValues { ($0.sent, $0.recv) }
        previousTime     = now
        return stats
    }

    // MARK: - Private

    private struct RawIfData {
        var sent: UInt64 = 0
        var recv: UInt64 = 0
        var ip:   String = ""
    }

    private func interfaceData() -> (total: (sent: UInt64, recv: UInt64),
                                     perIf: [String: RawIfData]) {
        var totalSent: UInt64 = 0, totalRecv: UInt64 = 0
        var perIf: [String: RawIfData] = [:]

        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0 else { return ((0, 0), [:]) }
        defer { freeifaddrs(ifaddr) }

        var ptr = ifaddr
        while let cur = ptr {
            defer { ptr = cur.pointee.ifa_next }
            let name  = String(cString: cur.pointee.ifa_name)
            let flags = Int32(cur.pointee.ifa_flags)
            guard (flags & IFF_LOOPBACK) == 0, (flags & IFF_UP) != 0 else { continue }
            guard let sa = cur.pointee.ifa_addr else { continue }

            if sa.pointee.sa_family == UInt8(AF_LINK),
               let data = cur.pointee.ifa_data?.assumingMemoryBound(to: if_data.self) {
                let sent = UInt64(data.pointee.ifi_obytes)
                let recv = UInt64(data.pointee.ifi_ibytes)
                totalSent += sent
                totalRecv += recv
                if perIf[name] == nil { perIf[name] = RawIfData() }
                perIf[name]?.sent = sent
                perIf[name]?.recv = recv
            }

            if sa.pointee.sa_family == UInt8(AF_INET) {
                var buf = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                if getnameinfo(sa, socklen_t(MemoryLayout<sockaddr_in>.size),
                               &buf, socklen_t(buf.count), nil, 0, NI_NUMERICHOST) == 0 {
                    if perIf[name] == nil { perIf[name] = RawIfData() }
                    perIf[name]?.ip = String(cString: buf)
                }
            }
        }
        return ((totalSent, totalRecv), perIf)
    }
}
