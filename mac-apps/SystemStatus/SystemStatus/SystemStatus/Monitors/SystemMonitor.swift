//
//  SystemMonitor.swift
//  SystemStatus
//
//  Central @Observable object that drives all UI updates.
//
//  Polling loops:
//   • usageTimer   (refreshInterval, main thread)  — CPU, memory, network, disk, battery, GPU, system info
//   • processTimer (max 5 s, background Task)      — thread / process counts, top processes
//
//  Also manages history arrays (last 60 samples) for sparklines and
//  sends UNUserNotifications when CPU / Memory cross user-configured thresholds.
//

import Foundation
import UserNotifications

@Observable
final class SystemMonitor {
    var cpuStats        = CPUStats()
    var memoryStats     = MemoryStats()
    var networkStats    = NetworkStats()
    var diskStats       = DiskStats()
    var batteryStats    = BatteryStats()
    var gpuStats        = GPUStats()
    var systemInfoStats = SystemInfoStats()
    var topProcesses: [TopProcess] = []

    // Reflects UserDefaults "menuBarLabel" — kept here so MenuBarExtra label
    // can observe it via @Observable rather than relying on @AppStorage.
    var menuBarLabelMode: String = UserDefaults.standard.string(forKey: "menuBarLabel") ?? "cpu"

    // Sparkline history — last 60 samples, values 0–100
    var cpuHistory:      [Double] = []
    var memoryHistory:   [Double] = []
    var uploadHistory:   [Double] = []
    var downloadHistory: [Double] = []
    var gpuHistory:      [Double] = []

    private let cpuMonitor        = CPUMonitor()
    private let memoryMonitor     = MemoryMonitor()
    private let networkMonitor    = NetworkMonitor()
    private let diskMonitor       = DiskMonitor()
    private let batteryMonitor    = BatteryMonitor()
    private let gpuMonitor        = GPUMonitor()
    private let systemInfoMonitor = SystemInfoMonitor()

    private var usageTimer:   Timer?
    private var processTimer: Timer?
    private var settingsObserver: NSObjectProtocol?

    // Alert cooldown — avoid spamming (5 minutes between same-category alerts)
    private var lastCPUAlertDate:    Date?
    private var lastMemoryAlertDate: Date?
    private let alertCooldown: TimeInterval = 5 * 60

    private var refreshInterval: TimeInterval {
        let v = UserDefaults.standard.double(forKey: "refreshInterval")
        return v > 0 ? v : 3.0
    }

    init() {
        // Prime delta baselines so the first readings are meaningful
        _ = cpuMonitor.sampleUsage()
        _ = networkMonitor.update()
        _ = diskMonitor.update()

        refreshUsage()
        refreshProcessInfo()
        startTimers()

        UNUserNotificationCenter.current()
            .requestAuthorization(options: [.alert, .sound]) { _, _ in }

        settingsObserver = NotificationCenter.default.addObserver(
            forName: UserDefaults.didChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.menuBarLabelMode = UserDefaults.standard.string(forKey: "menuBarLabel") ?? "cpu"
            self?.startTimers()
        }
    }

    deinit {
        usageTimer?.invalidate()
        processTimer?.invalidate()
        if let obs = settingsObserver { NotificationCenter.default.removeObserver(obs) }
    }

    // MARK: - Timers

    private func startTimers() {
        usageTimer?.invalidate()
        processTimer?.invalidate()
        let interval = refreshInterval
        usageTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            self?.refreshUsage()
        }
        processTimer = Timer.scheduledTimer(withTimeInterval: max(5.0, interval), repeats: true) { [weak self] _ in
            self?.refreshProcessInfo()
        }
    }

    // MARK: - Refresh

    private func refreshUsage() {
        let (user, system, idle) = cpuMonitor.sampleUsage()
        cpuStats.userPercent   = user
        cpuStats.systemPercent = system
        cpuStats.idlePercent   = idle

        memoryStats     = memoryMonitor.update()
        networkStats    = networkMonitor.update()
        diskStats       = diskMonitor.update()
        batteryStats    = batteryMonitor.update()
        gpuStats        = gpuMonitor.update()
        systemInfoStats = systemInfoMonitor.update()

        append(cpuStats.totalUsedPercent, to: &cpuHistory)

        let memPct = memoryStats.physicalMemory > 0
            ? Double(memoryStats.memoryUsed) / Double(memoryStats.physicalMemory) * 100 : 0
        append(memPct, to: &memoryHistory)

        append(min(networkStats.uploadBytesPerSec   / 1_048_576 / 100 * 100, 100), to: &uploadHistory)
        append(min(networkStats.downloadBytesPerSec / 1_048_576 / 100 * 100, 100), to: &downloadHistory)
        append(gpuStats.deviceUtilization, to: &gpuHistory)

        checkAlerts()
    }

    private func refreshProcessInfo() {
        Task.detached(priority: .utility) {
            let (threads, processes) = CPUMonitor.sampleProcessInfo()
            let topProcs             = CPUMonitor.sampleTopProcesses()
            await MainActor.run { [weak self] in
                self?.cpuStats.threadCount  = threads
                self?.cpuStats.processCount = processes
                self?.topProcesses          = topProcs
            }
        }
    }

    private func append(_ value: Double, to array: inout [Double], max: Int = 60) {
        array.append(value)
        if array.count > max { array.removeFirst(array.count - max) }
    }

    // MARK: - Alerts

    private func checkAlerts() {
        let now = Date()
        let ud  = UserDefaults.standard

        let cpuEnabled   = ud.bool(forKey: "alertCPUEnabled")
        let cpuThreshold = ud.double(forKey: "alertCPUThreshold").positive ?? 90

        if cpuEnabled && cpuStats.totalUsedPercent >= cpuThreshold {
            if lastCPUAlertDate.map({ now.timeIntervalSince($0) >= alertCooldown }) ?? true {
                sendNotification(title: "High CPU Usage",
                                 body: String(format: "CPU is at %.0f%%", cpuStats.totalUsedPercent))
                lastCPUAlertDate = now
            }
        }

        let memEnabled   = ud.bool(forKey: "alertMemoryEnabled")
        let memThreshold = ud.double(forKey: "alertMemoryThreshold").positive ?? 85
        let memPct       = memoryStats.physicalMemory > 0
            ? Double(memoryStats.memoryUsed) / Double(memoryStats.physicalMemory) * 100 : 0

        if memEnabled && memPct >= memThreshold {
            if lastMemoryAlertDate.map({ now.timeIntervalSince($0) >= alertCooldown }) ?? true {
                sendNotification(title: "High Memory Usage",
                                 body: String(format: "Memory is at %.0f%%", memPct))
                lastMemoryAlertDate = now
            }
        }
    }

    private func sendNotification(title: String, body: String) {
        let c = UNMutableNotificationContent()
        c.title = title; c.body = body; c.sound = .default
        UNUserNotificationCenter.current()
            .add(UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil))
    }
}

private extension Double {
    var positive: Double? { self > 0 ? self : nil }
}
