// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "OmniMacAXHelper",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "OmniMacAXHelper", targets: ["OmniMacAXHelper"]),
    ],
    targets: [
        .executableTarget(name: "OmniMacAXHelper"),
    ]
)
