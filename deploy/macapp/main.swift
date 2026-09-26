// Homebase.app — a native window onto the dashboard. This is a VIEWER:
// the trading process is the launchd service; closing this window changes
// nothing about execution.
import Cocoa
import WebKit

class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()   // without this, ⌘V/⌘C/⌘A do nothing on macOS
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
        // Start from the servers' current pages. The dashboard sends no cache
        // headers, and WebKit's heuristic cache otherwise keeps serving a page
        // (and its scripts) from before an upgrade (2026-09-26: the old chart
        // page kept showing after the charts redesign went live). Cookies and
        // localStorage (theme, chart layout) are kept.
        let caches: Set<String> = [WKWebsiteDataTypeDiskCache, WKWebsiteDataTypeMemoryCache]
        WKWebsiteDataStore.default().removeData(ofTypes: caches,
                                                modifiedSince: Date(timeIntervalSince1970: 0)) {
            wv.load(URLRequest(url: URL(string: "http://localhost:8850")!))
        }

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

    // ⌘R reloads what is on screen (the desk or the charts) from the server,
    // never from the cache
    @objc func reloadPage() {
        if webView.url != nil {
            webView.reloadFromOrigin()
        } else {
            webView.load(URLRequest(url: URL(string: "http://localhost:8850")!))
        }
    }

    private func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu()
        let reload = NSMenuItem(title: "Reload", action: #selector(reloadPage),
                                keyEquivalent: "r")
        reload.target = self
        appMenu.addItem(reload)
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit Homebase",
                        action: #selector(NSApplication.terminate(_:)),
                        keyEquivalent: "q")
        appItem.submenu = appMenu

        let editItem = NSMenuItem()
        main.addItem(editItem)
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(NSMenuItem.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)),
                     keyEquivalent: "a")
        editItem.submenu = edit

        let winItem = NSMenuItem()
        main.addItem(winItem)
        let winMenu = NSMenu(title: "Window")
        winMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)),
                        keyEquivalent: "w")
        winMenu.addItem(withTitle: "Minimize",
                        action: #selector(NSWindow.performMiniaturize(_:)),
                        keyEquivalent: "m")
        winItem.submenu = winMenu

        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
