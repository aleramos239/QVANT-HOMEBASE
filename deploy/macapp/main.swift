// Homebase.app — a native window onto the dashboard. This is a VIEWER:
// the trading process is the launchd service; closing this window changes
// nothing about execution.
import Cocoa
import WebKit

class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!

    func applicationDidFinishLaunching(_ n: Notification) {
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1120, height: 840),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        win.title = "Homebase"
        win.center()
        win.setFrameAutosaveName("HomebaseMain")

        let wv = WKWebView(frame: win.contentView!.bounds)
        wv.autoresizingMask = [.width, .height]
        wv.navigationDelegate = self
        win.contentView!.addSubview(wv)
        wv.load(URLRequest(url: URL(string: "http://localhost:8850")!))

        win.makeKeyAndOrderFront(nil)
        window = win
        webView = wv
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    // service mid-restart? retry until the dashboard answers
    func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { retry() }
    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!,
                 withError e: Error) { retry() }
    private func retry() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.webView.load(URLRequest(url: URL(string: "http://localhost:8850")!))
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
