//
//  CPUStats.swift
//  SystemStatus
//
//  CPU usage and process data models.
//

import Darwin

// MARK: - CPUStats

/// Per-sample CPU usage statistics.
struct CPUStats {
    var userPercent: Double   = 0
    var systemPercent: Double = 0
    var idlePercent: Double   = 100
    /// Visible threads only — root-owned daemons return EPERM so this is a lower bound.
    var threadCount: Int      = 0
    var processCount: Int     = 0
    /// Always true; drives the "~" prefix in the UI.
    var threadsAreApproximate = true

    /// Combined user + system load (0–100).
    var totalUsedPercent: Double { userPercent + systemPercent }
}

// MARK: - TopProcess

/// A process entry used for the top-5 memory consumers list.
struct TopProcess: Identifiable {
    let id: pid_t
    let name: String
    let memoryBytes: UInt64
}
