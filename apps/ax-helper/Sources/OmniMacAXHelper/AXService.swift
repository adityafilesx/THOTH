import AppKit
import ApplicationServices
import Foundation

private let maximumWindows = 20
private let maximumElements = 500
private let maximumDepth = 12
private let maximumActions = 32
private let maximumStringBytes = 4_096

final class AXService {
    func handle(_ request: HelperRequest) -> Data {
        let trusted = AXIsProcessTrusted()
        if request.operation == .health {
            return responseData(requestID: request.requestID, ok: true, trusted: trusted)
        }
        guard trusted else {
            return responseData(
                requestID: request.requestID,
                ok: false,
                trusted: false,
                error: "Accessibility permission is not granted to me.adityalabs.omnimac.axhelper"
            )
        }
        do {
            let result: [String: Any]
            switch request.operation {
            case .health:
                result = [:]
            case .inspectApplication:
                let bundleID = request.payload["bundle_id"] as! String
                result = ["snapshot": try inspectApplication(bundleID: bundleID)]
            case .setValue:
                result = ["performed": try mutate(request.payload, kind: .setValue)]
            case .performAction:
                result = ["performed": try mutate(request.payload, kind: .performAction)]
            case .selectOption:
                result = ["performed": try mutate(request.payload, kind: .selectOption)]
            }
            return responseData(
                requestID: request.requestID, ok: true, trusted: true, result: result
            )
        } catch {
            return responseData(
                requestID: request.requestID,
                ok: false,
                trusted: trusted,
                error: String(describing: error).prefixString(maximumStringBytes)
            )
        }
    }

    private enum MutationKind { case setValue, performAction, selectOption }

    private func mutate(_ payload: [String: Any], kind: MutationKind) throws -> Bool {
        let target = payload["target"] as! [String: Any]
        let bundleID = target["application_bundle_id"] as! String
        let application = try applicationElement(bundleID: bundleID).element
        guard let element = resolveUnique(application: application, target: target) else {
            return false
        }
        // Re-check TCC immediately before the atomic AX mutation.
        guard AXIsProcessTrusted() else { return false }
        switch kind {
        case .setValue:
            return AXUIElementSetAttributeValue(
                element, kAXValueAttribute as CFString, payload["value"] as CFTypeRef
            ) == .success
        case .performAction:
            let action = payload["action_name"] as! String
            return AXUIElementPerformAction(element, action as CFString) == .success
        case .selectOption:
            let option = payload["option"] as! String
            if AXUIElementSetAttributeValue(
                element, kAXValueAttribute as CFString, option as CFString
            ) == .success { return true }
            for child in boundedDescendants(element, limit: 100) {
                if stringAttribute(child, kAXTitleAttribute) == option {
                    return AXUIElementPerformAction(child, kAXPressAction as CFString) == .success
                }
            }
            return false
        }
    }

    private func inspectApplication(bundleID: String) throws -> [String: Any] {
        let resolved = try applicationElement(bundleID: bundleID)
        let capturedAt = ISO8601DateFormatter().string(from: Date())
        let rawWindows = arrayAttribute(resolved.element, kAXWindowsAttribute)
        var windows: [[String: Any]] = []
        var total = 0
        var truncated = rawWindows.count > maximumWindows
        for (index, window) in rawWindows.prefix(maximumWindows).enumerated() {
            if total >= maximumElements { truncated = true; break }
            let remaining = maximumElements - total
            let built = snapshotWindow(
                window, bundleID: bundleID, index: index, capturedAt: capturedAt, limit: remaining
            )
            windows.append(built.snapshot)
            total += built.count
            truncated = truncated || built.truncated
        }
        return [
            "bundle_id": bundleID,
            "display_name": bounded(resolved.application.localizedName ?? bundleID),
            "process_identifier": Int(resolved.application.processIdentifier),
            "windows": windows,
            "captured_at": capturedAt,
            "truncated": truncated,
            "provenance": "TOOL_RESULT_UNTRUSTED",
        ]
    }

    private func snapshotWindow(
        _ window: AXUIElement,
        bundleID: String,
        index: Int,
        capturedAt: String,
        limit: Int
    ) -> (snapshot: [String: Any], count: Int, truncated: Bool) {
        let identifier = stringAttribute(window, kAXIdentifierAttribute) ?? "window-\(index)"
        let title = stringAttribute(window, kAXTitleAttribute)
        var elements: [[String: Any]] = []
        var visited = Set<CFHashCode>()
        var truncated = false
        for child in arrayAttribute(window, kAXChildrenAttribute) {
            flatten(
                child,
                bundleID: bundleID,
                windowID: identifier,
                windowTitle: title,
                capturedAt: capturedAt,
                parentPath: [],
                depth: 0,
                limit: limit,
                elements: &elements,
                visited: &visited,
                truncated: &truncated
            )
        }
        return ([
            "application_bundle_id": bundleID,
            "identifier": identifier,
            "title": title ?? NSNull(),
            "focused": optionalJSON(boolAttribute(window, kAXFocusedAttribute)),
            "element_count": elements.count,
            "elements": elements,
            "captured_at": capturedAt,
            "truncated": truncated,
            "provenance": "TOOL_RESULT_UNTRUSTED",
        ], elements.count, truncated)
    }

    private func flatten(
        _ element: AXUIElement,
        bundleID: String,
        windowID: String,
        windowTitle: String?,
        capturedAt: String,
        parentPath: [String],
        depth: Int,
        limit: Int,
        elements: inout [[String: Any]],
        visited: inout Set<CFHashCode>,
        truncated: inout Bool
    ) {
        let identity = CFHash(element)
        guard depth <= maximumDepth, elements.count < limit, !visited.contains(identity) else {
            truncated = true
            return
        }
        visited.insert(identity)
        guard let role = stringAttribute(element, kAXRoleAttribute) else { return }
        let identifier = stringAttribute(element, kAXIdentifierAttribute)
        let label = stringAttribute(element, kAXTitleAttribute)
        let description = stringAttribute(element, kAXDescriptionAttribute)
        let sensitive = isSensitive(role: role, identifier: identifier, label: label, description: description)
        let children = arrayAttribute(element, kAXChildrenAttribute)
        let valueMetadata = makeValueMetadata(element, sensitive: sensitive)
        let reference = "ax-\(CFHash(element))-\(elements.count)"
        elements.append([
            "reference_id": reference,
            "application_bundle_id": bundleID,
            "window_identifier": windowID,
            "window_title": windowTitle ?? NSNull(),
            "role": bounded(role),
            "subrole": optionalJSON(stringAttribute(element, kAXSubroleAttribute)),
            "identifier": optionalJSON(identifier),
            "label": optionalJSON(label),
            "description": optionalJSON(description),
            "value_metadata": valueMetadata,
            "enabled": optionalJSON(boolAttribute(element, kAXEnabledAttribute)),
            "focused": optionalJSON(boolAttribute(element, kAXFocusedAttribute)),
            "selected": optionalJSON(boolAttribute(element, kAXSelectedAttribute)),
            "visible": optionalJSON(boolAttribute(element, kAXHiddenAttribute).map { !$0 }),
            "child_count": children.count,
            "supported_actions": actionNames(element),
            "parent_path": Array(parentPath.suffix(maximumDepth)),
            "captured_at": capturedAt,
            "truncated": children.count > max(0, limit - elements.count),
            "provenance": "TOOL_RESULT_UNTRUSTED",
        ])
        let nextPath = Array((parentPath + [identifier ?? label ?? role]).suffix(maximumDepth))
        for child in children {
            flatten(
                child,
                bundleID: bundleID,
                windowID: windowID,
                windowTitle: windowTitle,
                capturedAt: capturedAt,
                parentPath: nextPath,
                depth: depth + 1,
                limit: limit,
                elements: &elements,
                visited: &visited,
                truncated: &truncated
            )
        }
    }

    private func resolveUnique(
        application: AXUIElement, target: [String: Any]
    ) -> AXUIElement? {
        let windows = arrayAttribute(application, kAXWindowsAttribute).prefix(maximumWindows)
        let requestedWindow = target["window_identifier"] as? String
        let focusedModal = windows.first {
            boolAttribute($0, kAXFocusedAttribute) == true && boolAttribute($0, kAXModalAttribute) == true
        }
        let eligible = focusedModal.map { [$0] } ?? windows.filter {
            requestedWindow == nil || stringAttribute($0, kAXIdentifierAttribute) == requestedWindow
        }
        var matches: [AXUIElement] = []
        for element in eligible.flatMap({ boundedDescendants($0, limit: maximumElements) }) {
            guard stringAttribute(element, kAXRoleAttribute) == target["role"] as? String else {
                continue
            }
            let identifier = target["identifier"] as? String
            let label = target["label"] as? String
            let description = target["description"] as? String
            let matched = identifier.map { stringAttribute(element, kAXIdentifierAttribute) == $0 }
                ?? label.map { stringAttribute(element, kAXTitleAttribute) == $0 }
                ?? description.map { stringAttribute(element, kAXDescriptionAttribute) == $0 }
                ?? false
            if matched { matches.append(element) }
            if matches.count > 1 { return nil }
        }
        return matches.count == 1 ? matches[0] : nil
    }

    private func applicationElement(
        bundleID: String
    ) throws -> (application: NSRunningApplication, element: AXUIElement) {
        guard let running = NSWorkspace.shared.runningApplications.first(where: {
            $0.bundleIdentifier == bundleID
        }) else {
            throw HelperProtocolError.invalid("requested application is not running")
        }
        return (running, AXUIElementCreateApplication(running.processIdentifier))
    }

    private func boundedDescendants(_ root: AXUIElement, limit: Int) -> [AXUIElement] {
        var output: [AXUIElement] = []
        var stack = [root]
        var visited = Set<CFHashCode>()
        while let current = stack.popLast(), output.count < limit {
            let identity = CFHash(current)
            if visited.contains(identity) { continue }
            visited.insert(identity)
            output.append(current)
            stack.append(contentsOf: arrayAttribute(current, kAXChildrenAttribute).reversed())
        }
        return output
    }

    private func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
        var value: CFTypeRef?
        return AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success
            ? value : nil
    }

    private func stringAttribute(_ element: AXUIElement, _ name: String) -> String? {
        (attribute(element, name) as? String).map(bounded)
    }

    private func boolAttribute(_ element: AXUIElement, _ name: String) -> Bool? {
        attribute(element, name) as? Bool
    }

    private func arrayAttribute(_ element: AXUIElement, _ name: String) -> [AXUIElement] {
        (attribute(element, name) as? [AXUIElement]) ?? []
    }

    private func actionNames(_ element: AXUIElement) -> [String] {
        var names: CFArray?
        guard AXUIElementCopyActionNames(element, &names) == .success,
              let values = names as? [String]
        else { return [] }
        return values.prefix(maximumActions).map(bounded)
    }

    private func makeValueMetadata(_ element: AXUIElement, sensitive: Bool) -> Any {
        if sensitive {
            return ["kind": "unsupported", "value": NSNull(), "redacted": true,
                    "length": NSNull(), "truncated": false]
        }
        guard let raw = attribute(element, kAXValueAttribute) else {
            return ["kind": "none", "value": NSNull(), "redacted": false,
                    "length": NSNull(), "truncated": false]
        }
        if let text = raw as? String {
            let value = bounded(text)
            return ["kind": "string", "value": value, "redacted": false,
                    "length": text.utf8.count, "truncated": value != text]
        }
        if let boolean = raw as? Bool {
            return ["kind": "boolean", "value": boolean, "redacted": false,
                    "length": NSNull(), "truncated": false]
        }
        if let number = raw as? NSNumber {
            return ["kind": "number", "value": number.doubleValue, "redacted": false,
                    "length": NSNull(), "truncated": false]
        }
        return ["kind": "unsupported", "value": NSNull(), "redacted": false,
                "length": NSNull(), "truncated": false]
    }

    private func isSensitive(
        role: String, identifier: String?, label: String?, description: String?
    ) -> Bool {
        let text = [role, identifier, label, description].compactMap { $0 }.joined(separator: " ").lowercased()
        return ["secure", "password", "passcode", "verification code", "one-time code", "token"]
            .contains { text.contains($0) }
    }

    private func bounded(_ text: String) -> String {
        guard text.utf8.count > maximumStringBytes else { return text }
        var output = ""
        for character in text {
            let candidate = String(character)
            if output.utf8.count + candidate.utf8.count > maximumStringBytes { break }
            output.append(character)
        }
        return output
    }

    private func optionalJSON(_ value: Any?) -> Any { value ?? NSNull() }
}

private extension String {
    func prefixString(_ maximum: Int) -> String { String(prefix(maximum)) }
}
