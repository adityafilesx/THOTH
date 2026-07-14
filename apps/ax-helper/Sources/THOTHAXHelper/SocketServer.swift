import Darwin
import Foundation
import ApplicationServices

final class UnixSocketServer {
    private let socketPath: String
    private let service = AXService()

    init(socketPath: String) {
        self.socketPath = socketPath
    }

    func run() throws -> Never {
        try prepareDirectory()
        unlink(socketPath)
        let descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else { throw POSIXError(.ENOTSOCK) }
        defer { close(descriptor); unlink(socketPath) }

        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let pathBytes = Array(socketPath.utf8CString)
        guard pathBytes.count <= MemoryLayout.size(ofValue: address.sun_path) else {
            throw HelperProtocolError.invalid("socket path exceeds sockaddr_un ceiling")
        }
        withUnsafeMutablePointer(to: &address.sun_path) { pointer in
            pointer.withMemoryRebound(to: CChar.self, capacity: pathBytes.count) { target in
                _ = pathBytes.withUnsafeBufferPointer { source in
                    memcpy(target, source.baseAddress, pathBytes.count)
                }
            }
        }
        let bindResult = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(descriptor, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        guard bindResult == 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        guard chmod(socketPath, S_IRUSR | S_IWUSR) == 0 else { throw POSIXError(.EACCES) }
        guard listen(descriptor, 8) == 0 else { throw POSIXError(.EIO) }

        while true {
            let client = accept(descriptor, nil, nil)
            if client < 0 { continue }
            autoreleasepool {
                handle(client)
                close(client)
            }
        }
    }

    private func handle(_ client: Int32) {
        var peerUID: uid_t = 0
        var peerGID: gid_t = 0
        guard getpeereid(client, &peerUID, &peerGID) == 0, peerUID == geteuid() else {
            return
        }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 65_536)
        while data.count <= maximumMessageBytes {
            let count = recv(client, &buffer, buffer.count, 0)
            if count <= 0 { return }
            data.append(buffer, count: count)
            if let newline = data.firstIndex(of: 0x0A) {
                data = data.prefix(upTo: newline)
                break
            }
        }
        guard data.count <= maximumMessageBytes else { return }
        let response: Data
        do {
            response = service.handle(try HelperRequest.decode(data))
        } catch {
            response = responseData(
                requestID: "invalid", ok: false, trusted: AXIsProcessTrusted(),
                error: String(describing: error).prefixString(4_096)
            )
        }
        let bytes = response + Data([0x0A])
        bytes.withUnsafeBytes { pointer in
            guard let base = pointer.baseAddress else { return }
            var sent = 0
            while sent < bytes.count {
                let count = send(client, base.advanced(by: sent), bytes.count - sent, 0)
                if count <= 0 { return }
                sent += count
            }
        }
    }

    private func prepareDirectory() throws {
        let directory = URL(fileURLWithPath: socketPath).deletingLastPathComponent()
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
    }
}

private extension String {
    func prefixString(_ maximum: Int) -> String { String(prefix(maximum)) }
}
