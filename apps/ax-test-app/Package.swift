// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "OmniMacAXTestApp",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "OmniMacAXTestApp", targets: ["OmniMacAXTestApp"]),
    ],
    targets: [
        .executableTarget(name: "OmniMacAXTestApp"),
    ]
)
