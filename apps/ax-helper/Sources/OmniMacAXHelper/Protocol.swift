import Foundation

let protocolVersion = 1
let maximumMessageBytes = 4 * 1_024 * 1_024

enum HelperProtocolError: Error, CustomStringConvertible {
    case invalid(String)

    var description: String {
        switch self {
        case let .invalid(message): message
        }
    }
}

enum HelperOperation: String, CaseIterable {
    case health
    case inspectApplication = "inspect_application"
    case setValue = "set_value"
    case performAction = "perform_action"
    case selectOption = "select_option"
}

struct HelperRequest {
    let requestID: String
    let operation: HelperOperation
    let payload: [String: Any]

    static func decode(_ data: Data) throws -> HelperRequest {
        guard data.count <= maximumMessageBytes else {
            throw HelperProtocolError.invalid("request exceeds message ceiling")
        }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw HelperProtocolError.invalid("request must be a JSON object")
        }
        let allowedRoot = Set(["version", "request_id", "operation", "payload"])
        guard Set(object.keys) == allowedRoot else {
            throw HelperProtocolError.invalid("request contains missing or extra fields")
        }
        guard let version = object["version"] as? Int, version == protocolVersion else {
            throw HelperProtocolError.invalid("unsupported protocol version")
        }
        guard let requestID = object["request_id"] as? String,
              !requestID.isEmpty, requestID.utf8.count <= 64
        else {
            throw HelperProtocolError.invalid("invalid request id")
        }
        guard let operationText = object["operation"] as? String,
              let operation = HelperOperation(rawValue: operationText),
              let payload = object["payload"] as? [String: Any]
        else {
            throw HelperProtocolError.invalid("unknown operation or invalid payload")
        }
        try validatePayload(payload, for: operation)
        return HelperRequest(requestID: requestID, operation: operation, payload: payload)
    }

    private static func validatePayload(
        _ payload: [String: Any],
        for operation: HelperOperation
    ) throws {
        switch operation {
        case .health:
            guard payload.isEmpty else {
                throw HelperProtocolError.invalid("health accepts no payload")
            }
        case .inspectApplication:
            try exactKeys(payload, ["bundle_id"])
            _ = try boundedString(payload["bundle_id"], name: "bundle_id", maximum: 255)
        case .setValue:
            try exactKeys(payload, ["target", "value"])
            try validateTarget(payload["target"])
            try validatePrimitive(payload["value"], name: "value")
        case .performAction:
            try exactKeys(payload, ["target", "action_name"])
            try validateTarget(payload["target"])
            _ = try boundedString(payload["action_name"], name: "action_name", maximum: 255)
        case .selectOption:
            try exactKeys(payload, ["target", "option"])
            try validateTarget(payload["target"])
            _ = try boundedString(payload["option"], name: "option", maximum: 4_096)
        }
    }

    private static func validateTarget(_ value: Any?) throws {
        guard let target = value as? [String: Any] else {
            throw HelperProtocolError.invalid("target must be an object")
        }
        try exactKeys(target, [
            "application_bundle_id", "window_identifier", "role", "identifier",
            "label", "description", "parent_path",
        ])
        _ = try boundedString(
            target["application_bundle_id"], name: "application_bundle_id", maximum: 255
        )
        _ = try boundedString(target["role"], name: "role", maximum: 4_096)
        for name in ["window_identifier", "identifier", "label", "description"] {
            if !(target[name] is NSNull) {
                _ = try boundedString(target[name], name: name, maximum: 4_096)
            }
        }
        guard let path = target["parent_path"] as? [String], path.count <= 12 else {
            throw HelperProtocolError.invalid("parent_path must contain at most 12 strings")
        }
        guard target["identifier"] is String || target["label"] is String
                || target["description"] is String || !path.isEmpty
        else {
            throw HelperProtocolError.invalid("target requires a semantic selector")
        }
    }

    private static func exactKeys(_ object: [String: Any], _ expected: Set<String>) throws {
        guard Set(object.keys) == expected else {
            throw HelperProtocolError.invalid("payload contains missing or extra fields")
        }
    }

    private static func validatePrimitive(_ value: Any?, name: String) throws {
        guard value is String || value is Bool || value is Int || value is Double else {
            throw HelperProtocolError.invalid("\(name) must be a JSON primitive")
        }
        if value is String {
            _ = try boundedString(value, name: name, maximum: 4_096)
        }
    }

    private static func boundedString(
        _ value: Any?, name: String, maximum: Int
    ) throws -> String {
        guard let text = value as? String, !text.isEmpty, text.utf8.count <= maximum else {
            throw HelperProtocolError.invalid("\(name) is empty or exceeds its ceiling")
        }
        return text
    }
}

func responseData(
    requestID: String,
    ok: Bool,
    trusted: Bool,
    result: [String: Any] = [:],
    error: String? = nil
) -> Data {
    let response: [String: Any] = [
        "version": protocolVersion,
        "request_id": requestID,
        "ok": ok,
        "trusted": trusted,
        "result": result,
        "error": error ?? NSNull(),
    ]
    // The response is composed only from JSON-compatible bounded values.
    return (try? JSONSerialization.data(withJSONObject: response)) ?? Data()
}
