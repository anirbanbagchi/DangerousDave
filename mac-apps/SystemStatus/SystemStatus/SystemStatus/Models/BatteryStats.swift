//
//  BatteryStats.swift
//  SystemStatus
//
//  Battery state data model.
//

import Foundation

/// Battery state and health information.
/// `isPresent` is false on desktop Macs — the battery section is hidden in that case.
struct BatteryStats {
    var isPresent: Bool         = false
    var percentage: Int         = 0
    var isCharging: Bool        = false
    var isPluggedIn: Bool       = false
    /// Minutes remaining (to empty or to full); -1 = calculating / N/A.
    var timeRemaining: Int      = -1
    var cycleCount: Int         = 0
    var healthCondition: String = "Normal"
    /// Instantaneous power in watts (current × voltage). 0 when unavailable.
    var powerWatts: Double      = 0
}
