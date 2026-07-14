// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "THOTHAXHelper",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "THOTHAXHelper", targets: ["THOTHAXHelper"]),
    ],
    targets: [
        .executableTarget(name: "THOTHAXHelper"),
    ]
)
