//
//  CPUMonitor.swift
//  SystemStatus
//
//  Collects per-core CPU tick deltas via host_processor_info and
//  enumerates processes/threads via sysctl + libproc.
//
//  NOTE — Thread count accuracy:
//  ~40 % of running processes are root-owned system daemons.  Every public
//  API (proc_pidinfo, PROC_PIDLISTTHREADS, processor_set_tasks) returns
//  EPERM for those without Apple's private task_for_pid entitlement.
//  The count we report is therefore a lower-bound and will be lower than
//  Activity Monitor, which holds that private entitlement.
//

import Darwin

final class CPUMonitor {
    /// Cumulative ticks from the previous sample — must only be touched on the main actor.
    private var previousTicks: [Int32] = []

    // MARK: CPU usage (fast — called every N s on main actor)

    func sampleUsage() -> (user: Double, system: Double, idle: Double) {
        var numCPU: natural_t = 0
        var infoPtr: processor_info_array_t?
        var infoCount: mach_msg_type_number_t = 0

        guard host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO,
                                   &numCPU, &infoPtr, &infoCount) == KERN_SUCCESS,
              let info = infoPtr else {
            return (0, 0, 100)
        }

        defer {
            vm_deallocate(mach_task_self_,
                          vm_address_t(UInt(bitPattern: info)),
                          vm_size_t(infoCount) * vm_size_t(MemoryLayout<integer_t>.size))
        }

        let cpuCount = Int(numCPU)
        let stride   = Int(CPU_STATE_MAX)
        let current  = Array(UnsafeBufferPointer(start: info, count: cpuCount * stride))

        var dUser: Int64 = 0, dSys: Int64 = 0, dIdle: Int64 = 0, dNice: Int64 = 0

        for i in 0..<cpuCount {
            let b = i * stride
            guard previousTicks.count >= b + stride else { continue }
            dUser += Int64(current[b + Int(CPU_STATE_USER)])   - Int64(previousTicks[b + Int(CPU_STATE_USER)])
            dSys  += Int64(current[b + Int(CPU_STATE_SYSTEM)]) - Int64(previousTicks[b + Int(CPU_STATE_SYSTEM)])
            dIdle += Int64(current[b + Int(CPU_STATE_IDLE)])   - Int64(previousTicks[b + Int(CPU_STATE_IDLE)])
            dNice += Int64(current[b + Int(CPU_STATE_NICE)])   - Int64(previousTicks[b + Int(CPU_STATE_NICE)])
        }

        previousTicks = current

        let total = dUser + dSys + dIdle + dNice
        guard total > 0 else { return (0, 0, 100) }

        let t = Double(total)
        return (
            user:   Double(dUser + dNice) / t * 100,
            system: Double(dSys)          / t * 100,
            idle:   Double(dIdle)         / t * 100
        )
    }

    // MARK: Process & thread counts (slow — called every 5 s on a background task)

    /// Stateless: safe to call from any concurrency context.
    nonisolated static func sampleProcessInfo() -> (threads: Int, processes: Int) {
        // Process count via KERN_PROC_ALL
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_ALL, 0]
        var size: size_t = 0
        sysctl(&mib, 4, nil, &size, nil, 0)
        let approxCount = size > 0 ? size / MemoryLayout<kinfo_proc>.stride : 128

        // Enumerate all PIDs
        var pids = [pid_t](repeating: 0, count: approxCount + 64)
        let pidCount = proc_listallpids(&pids, Int32(pids.count * MemoryLayout<pid_t>.size))
        guard pidCount > 0 else { return (0, Int(approxCount)) }

        // Sum thread counts for every process we're allowed to inspect.
        // Root-owned daemons (~40 % of all PIDs) return EPERM — silently skipped.
        var totalThreads = 0
        for i in 0..<Int(pidCount) {
            var taskInfo = proc_taskinfo()
            if proc_pidinfo(pids[i], PROC_PIDTASKINFO, 0,
                            &taskInfo, Int32(MemoryLayout<proc_taskinfo>.size)) > 0 {
                totalThreads += Int(taskInfo.pti_threadnum)
            }
        }

        return (totalThreads, Int(pidCount))
    }

    // MARK: Top processes by memory (slow — called together with sampleProcessInfo)

    /// Returns up to 5 processes sorted by resident memory, descending.
    /// Stateless: safe to call from any concurrency context.
    nonisolated static func sampleTopProcesses() -> [TopProcess] {
        var pids = [pid_t](repeating: 0, count: 2048)
        let count = proc_listallpids(&pids, Int32(pids.count * MemoryLayout<pid_t>.size))
        guard count > 0 else { return [] }

        var results: [TopProcess] = []
        results.reserveCapacity(Int(count))

        for i in 0..<Int(count) {
            let pid = pids[i]
            guard pid > 0 else { continue }
            var info = proc_taskinfo()
            guard proc_pidinfo(pid, PROC_PIDTASKINFO, 0,
                               &info, Int32(MemoryLayout<proc_taskinfo>.size)) > 0 else { continue }
            var nameBuf = [CChar](repeating: 0, count: 256)
            proc_name(pid, &nameBuf, UInt32(nameBuf.count))
            let name = String(cString: nameBuf)
            results.append(TopProcess(id: pid,
                                      name: name.isEmpty ? "(pid \(pid))" : name,
                                      memoryBytes: info.pti_resident_size))
        }

        return Array(results.sorted { $0.memoryBytes > $1.memoryBytes }.prefix(5))
    }
}
