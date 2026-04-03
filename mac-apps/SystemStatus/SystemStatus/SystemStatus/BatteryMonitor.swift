//
//  BatteryMonitor.swift
//  SystemStatus
//
//  Reads battery state via IOKit PowerSources and the AppleSmartBattery service.
//  On desktop Macs, isPresent will be false and the section is hidden.
//

import Foundation
import IOKit
import IOKit.ps

struct BatteryStats {
    var isPresent: Bool        = false
    var percentage: Int        = 0
    var isCharging: Bool       = false
    var isPluggedIn: Bool      = false
    /// Minutes remaining (to empty or to full); -1 = calculating / N/A
    var timeRemaining: Int     = -1
    var cycleCount: Int        = 0
    var healthCondition: String = "Normal"
}

final class BatteryMonitor {
    func update() -> BatteryStats {
        var stats = BatteryStats()
        let snapshot   = IOPSCopyPowerSourcesInfo().takeRetainedValue()
        let sourceList = IOPSCopyPowerSourcesList(snapshot).takeRetainedValue() as [CFTypeRef]

        for source in sourceList {
            guard let desc = IOPSGetPowerSourceDescription(snapshot, source)?
                    .takeUnretainedValue() as? [String: Any] else { continue }
            guard (desc[kIOPSTypeKey] as? String) == kIOPSInternalBatteryType else { continue }

            stats.isPresent   = true
            stats.percentage  = desc[kIOPSCurrentCapacityKey] as? Int ?? 0
            stats.isCharging  = (desc[kIOPSIsChargingKey] as? Bool) ?? false
            stats.isPluggedIn = (desc[kIOPSPowerSourceStateKey] as? String) == kIOPSACPowerValue

            if stats.isCharging, let ttf = desc[kIOPSTimeToFullChargeKey] as? Int, ttf > 0 {
                stats.timeRemaining = ttf
            } else if let tte = desc[kIOPSTimeToEmptyKey] as? Int, tte > 0 {
                stats.timeRemaining = tte
            }

            // Cycle count + health from AppleSmartBattery IORegistry entry
            let svc = IOServiceGetMatchingService(kIOMainPortDefault,
                                                  IOServiceMatching("AppleSmartBattery"))
            if svc != IO_OBJECT_NULL {
                defer { IOObjectRelease(svc) }
                var cfProps: Unmanaged<CFMutableDictionary>?
                if IORegistryEntryCreateCFProperties(svc, &cfProps,
                                                     kCFAllocatorDefault, 0) == KERN_SUCCESS,
                   let d = cfProps?.takeRetainedValue() as? [String: Any] {
                    stats.cycleCount      = d["CycleCount"] as? Int ?? 0
                    stats.healthCondition = d["BatteryHealthCondition"] as? String ?? "Normal"
                }
            }
            break  // only read first internal battery
        }
        return stats
    }
}
