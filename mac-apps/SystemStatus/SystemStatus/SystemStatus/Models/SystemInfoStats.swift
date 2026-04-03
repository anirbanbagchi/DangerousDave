//
//  SystemInfoStats.swift
//  SystemStatus
//
//  System-wide information: thermal state and uptime.
//

import Foundation

struct SystemInfoStats {
    var uptimeSeconds: TimeInterval              = 0
    var thermalState: ProcessInfo.ThermalState   = .nominal

    /// Human-readable uptime string, e.g. "3d 4h 12m".
    var formattedUptime: String {
        let s = Int(uptimeSeconds)
        let days    = s / 86_400
        let hours   = (s % 86_400) / 3_600
        let minutes = (s % 3_600)  / 60
        if days  > 0 { return "\(days)d \(hours)h \(minutes)m" }
        if hours > 0 { return "\(hours)h \(minutes)m" }
        return "\(minutes)m"
    }

    var thermalLabel: String {
        switch thermalState {
        case .nominal:   return "Normal"
        case .fair:      return "Elevated"
        case .serious:   return "High — throttling"
        case .critical:  return "Critical — severe throttling"
        @unknown default: return "Unknown"
        }
    }
}
