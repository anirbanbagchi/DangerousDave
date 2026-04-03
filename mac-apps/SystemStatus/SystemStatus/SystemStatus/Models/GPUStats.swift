//
//  GPUStats.swift
//  SystemStatus
//
//  GPU utilization data model.
//  Populated on Apple Silicon via IOKit IOGPU; falls back to IOAccelerator on Intel.
//  isAvailable is false when the IOKit service is unreachable.
//

import Foundation

struct GPUStats {
    var isAvailable: Bool         = false
    /// Overall device utilization (0–100).
    var deviceUtilization: Double   = 0
    /// 3-D renderer pipeline utilization (0–100).
    var rendererUtilization: Double = 0
    /// Tile-based rendering utilization (0–100).
    var tilerUtilization: Double    = 0
}
