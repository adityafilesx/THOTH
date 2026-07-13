import SwiftUI

@main
struct THOTHAXTestApp: App {
    var body: some Scene {
        WindowGroup("THOTH AX Test App") {
            TestFixtureView()
                .frame(minWidth: 760, minHeight: 720)
        }
        .windowResizability(.contentSize)
    }
}

private struct TestFixtureView: View {
    private let choices = ["Alpha", "Beta", "Gamma"]
    private let items = ["Mercury", "Venus", "Earth"]

    @State private var singleLine = ""
    @State private var multiline = ""
    @State private var checked = false
    @State private var toggled = false
    @State private var selectedChoice = "Alpha"
    @State private var count = 0
    @State private var searchText = ""
    @State private var status = "idle"
    @State private var progress = 0.25
    @State private var selectedSegment = "Overview"
    @State private var moveControlRight = false
    @State private var delayedVisible = false
    @State private var disappearingVisible = true
    @State private var validationVisible = false
    @State private var modalVisible = false
    @State private var confirmationVisible = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("THOTH Accessibility Test App")
                    .font(.title2)
                    .accessibilityAddTraits(.isHeader)

                GroupBox("Text") {
                    VStack(alignment: .leading, spacing: 8) {
                        TextField("Single-line input", text: $singleLine)
                            .accessibilityLabel("Single-line input")
                            .accessibilityIdentifier("ax-single-line-input")

                        TextEditor(text: $multiline)
                            .frame(height: 72)
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(.secondary))
                            .accessibilityLabel("Multiline text area")
                            .accessibilityIdentifier("ax-multiline-input")

                        TextField("Search items", text: $searchText)
                            .accessibilityLabel("Search field")
                            .accessibilityIdentifier("ax-search-field")
                    }
                }

                GroupBox("Choices") {
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("Include archived items", isOn: $checked)
                            .toggleStyle(.checkbox)
                            .accessibilityIdentifier("ax-checkbox")

                        Toggle("Enable notifications", isOn: $toggled)
                            .accessibilityIdentifier("ax-toggle")

                        Picker("Category", selection: $selectedChoice) {
                            ForEach(choices, id: \.self) { Text($0).tag($0) }
                        }
                        .accessibilityIdentifier("ax-picker")

                        Stepper("Count: \(count)", value: $count, in: 0...10)
                            .accessibilityIdentifier("ax-stepper")

                        Picker("Section", selection: $selectedSegment) {
                            Text("Overview").tag("Overview")
                            Text("Details").tag("Details")
                        }
                        .pickerStyle(.segmented)
                        .accessibilityIdentifier("ax-segmented-control")
                    }
                }

                GroupBox("Items") {
                    List(items.filter { searchText.isEmpty || $0.localizedCaseInsensitiveContains(searchText) }, id: \.self) { item in
                        Text(item)
                    }
                    .frame(height: 100)
                    .accessibilityLabel("Item list")
                    .accessibilityIdentifier("ax-item-list")
                }

                GroupBox("Dynamic state") {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            if moveControlRight { Spacer() }
                            Button("Move control") { moveControlRight.toggle() }
                                .accessibilityIdentifier("ax-moving-control")
                            if !moveControlRight { Spacer() }
                        }

                        if delayedVisible {
                            Text("Delayed element ready")
                                .accessibilityLabel("Delayed control")
                                .accessibilityIdentifier("ax-delayed-control")
                        }

                        if disappearingVisible {
                            Button("Remove this control") { disappearingVisible = false }
                                .accessibilityIdentifier("ax-disappearing-control")
                        }

                        ProgressView(value: progress)
                            .accessibilityLabel("Progress")
                            .accessibilityValue("\(Int(progress * 100)) percent")
                            .accessibilityIdentifier("ax-progress")

                        Text(status)
                            .accessibilityLabel("Status")
                            .accessibilityValue(status)
                            .accessibilityIdentifier("ax-status-label")

                        if validationVisible {
                            Text("Single-line input is required")
                                .foregroundStyle(.red)
                                .accessibilityLabel("Validation error")
                                .accessibilityIdentifier("ax-validation-error")
                        }
                    }
                }

                HStack {
                    Button("Disabled") {}
                        .disabled(true)
                        .accessibilityIdentifier("ax-disabled-button")

                    Button("Save") { save() }
                        .keyboardShortcut("s", modifiers: .command)
                        .accessibilityIdentifier("ax-save-button")

                    Button("Open modal") { modalVisible = true }
                        .accessibilityIdentifier("ax-modal-button")

                    Button("Request confirmation") { confirmationVisible = true }
                        .accessibilityIdentifier("ax-confirm-alert-button")

                    Spacer()

                    Button("Reset") { resetState() }
                        .accessibilityIdentifier("ax-reset-button")
                }
            }
            .padding(20)
        }
        .sheet(isPresented: $modalVisible) {
            VStack(spacing: 16) {
                Text("Fixture modal")
                    .accessibilityIdentifier("ax-modal-content")
                Button("Close") { modalVisible = false }
                    .accessibilityIdentifier("ax-modal-close-button")
            }
            .padding(32)
        }
        .alert("Confirm fixture action", isPresented: $confirmationVisible) {
            Button("Cancel", role: .cancel) { status = "confirmation-cancelled" }
            Button("Confirm") { status = "confirmed" }
        } message: {
            Text("This changes only deterministic fixture state.")
        }
        .task {
            if ProcessInfo.processInfo.arguments.contains("--reset") {
                resetState()
            }
            try? await Task.sleep(for: .milliseconds(750))
            guard !Task.isCancelled else { return }
            delayedVisible = true
        }
    }

    private func save() {
        validationVisible = singleLine.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        if validationVisible {
            status = "validation-error"
            progress = 0.25
        } else {
            status = "saved:\(singleLine)"
            progress = 1.0
        }
    }

    private func resetState() {
        singleLine = ""
        multiline = ""
        checked = false
        toggled = false
        selectedChoice = "Alpha"
        count = 0
        searchText = ""
        status = "idle"
        progress = 0.25
        selectedSegment = "Overview"
        moveControlRight = false
        delayedVisible = false
        disappearingVisible = true
        validationVisible = false
        modalVisible = false
        confirmationVisible = false
    }
}
