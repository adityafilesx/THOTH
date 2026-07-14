import Foundation

let support = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/THOTH", isDirectory: true)
let socketPath = support.appendingPathComponent("ax-helper.sock").path

do {
    try UnixSocketServer(socketPath: socketPath).run()
} catch {
    FileHandle.standardError.write(Data("THOTH AX helper failed: \(error)\n".utf8))
    exit(EXIT_FAILURE)
}
