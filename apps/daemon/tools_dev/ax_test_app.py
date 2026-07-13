"""THOTH AX test app (Phase 4 slice 3) — dev-only, never imported by the daemon.

A tiny Tkinter window with deterministically-labelled controls used to
LIVE-verify the Accessibility adapter once the daemon process has the
Accessibility (TCC) permission — pending live verification.

Run:
    uv run --project apps/daemon python apps/daemon/tools_dev/ax_test_app.py

Controls (role/label as exposed through macOS accessibility):
    text field  "thoth-input"   — type here / ax_set_value target
    button      "thoth-submit"  — ax_perform_action AXPress target
    static text "thoth-status"  — flips to "submitted:<text>" on press,
                                   read back via ax_read_value to verify
"""

import tkinter as tk


def main() -> None:
    root = tk.Tk()
    root.title("THOTH AX Test App")
    root.geometry("360x140")

    entry = tk.Entry(root, name="thoth-input", width=32)
    entry.pack(pady=8)

    status = tk.Label(root, name="thoth-status", text="idle")

    def submit() -> None:
        status.config(text=f"submitted:{entry.get()}")

    button = tk.Button(root, name="thoth-submit", text="Submit", command=submit)
    button.pack(pady=4)
    status.pack(pady=8)

    root.mainloop()


if __name__ == "__main__":
    main()
