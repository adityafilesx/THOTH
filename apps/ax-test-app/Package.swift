// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "THOTHAXTestApp",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "THOTHAXTestApp", targets: ["THOTHAXTestApp"]),
    ],
    targets: [
        .executableTarget(name: "THOTHAXTestApp"),
    ]
)
