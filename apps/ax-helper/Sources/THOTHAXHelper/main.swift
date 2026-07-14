import Foundation
import Darwin

func managedParentPID(environment: [String: String]) -> pid_t? {
    guard let raw = environment["THOTH_DESKTOP_PARENT_PID"],
          let value = Int32(raw), value > 1 else {
        return nil
    }
    return value
}

func startParentMonitor(parentPID: pid_t) -> DispatchSourceTimer {
    let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .utility))
    timer.schedule(deadline: .now() + .milliseconds(250), repeating: .milliseconds(250))
    timer.setEventHandler {
        if kill(parentPID, 0) == -1 && errno == ESRCH {
            exit(EXIT_SUCCESS)
        }
    }
    timer.resume()
    return timer
}

let support = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/THOTH", isDirectory: true)
let socketPath = support.appendingPathComponent("ax-helper.sock").path
let parentMonitor = managedParentPID(environment: ProcessInfo.processInfo.environment)
    .map(startParentMonitor)

do {
    try UnixSocketServer(socketPath: socketPath).run()
} catch {
    FileHandle.standardError.write(Data("THOTH AX helper failed: \(error)\n".utf8))
    exit(EXIT_FAILURE)
}
