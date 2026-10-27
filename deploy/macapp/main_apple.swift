// Homebase.app (built by build_app_apple.sh --mac) — a VIEWER: the trading process is the launchd service; closing this
// window changes nothing about execution. An Apple-style window, with the new design delivered as a SKIN.
//
//  * The window has no title bar of its own: the page's toolbar IS the window's toolbar, and the traffic lights
//    sit inside it (full-size content view). The window carries an EMPTY unified NSToolbar, which is what gives
//    it macOS 26's toolbar-window shape (26 pt corners) and makes the system place the traffic lights itself.
//    The toolbar's height and the lights' position are READ FROM THE SYSTEM at launch, never hard-coded.
//  * The page follows the window's appearance (View > Appearance: Match System / Light / Dark).
//  * The new design is a skin: /static/apple/manifest.json on the desk names, per tab, an optional start page
//    and the stylesheets / scripts to inject at document start. The plain pages are served unchanged. No
//    manifest, a broken one, or a file that does not load = this app shows the plain pages (its own title bar,
//    no injection): all of the skin or none of it.
//  * A mousedown on the page's toolbar asks for a window drag through a message handler (a web view swallows
//    the mouse, so the page has to ask); a double-click there does what the system setting says.
//  * View menu: Desk / Charts / Lab (⌘1/⌘2/⌘3).
//
// Link handling (opus review, three-tabs): a navigation to one of the three tabs' own
// origins switches to that tab; anything else opens in the default browser. A tab never leaves its own origin.
//
// Debug (never set in the installed app): HB_DEBUG_DIR=<dir> makes the app load the tabs named in
// HB_DEBUG_TABS (default "desk"), wait HB_DEBUG_WAIT seconds each, optionally run the JS in the file
// HB_DEBUG_JS, write <dir>/<tab>.png (the web view's own snapshot) and <dir>/<tab>.json (diagnostics), then
// quit. HB_DEBUG_OFFSCREEN=1 keeps the window off every display; HB_DEBUG_SIZE=WxH sets its size.
//
// HOMEBASE VPS (build_app_apple.sh --vps, compiled with -D VPS; the owner, 2026-10-18): the same viewer, seeing the
// SERVER's Homebase. The pages build their links and API calls as <same host>:8850 / :8852, so a port tunnel cannot
// do it: this app starts an SSH SOCKS proxy to the server (Info.plist HomebaseVPSHost) and sends every page and its own
// fetches through it, so localhost:8850 / :8852 in this app are the server's. Every page gets window.HB_MACHINE = 'server'
// (the Mac app: 'mac'); the page's toolbar chip shows it. While the proxy comes up a small window says "Connecting to the
// Chicago server…"; a page that does not load is covered by a plain "not reachable" line until a retry gets through.
import Cocoa
import WebKit
#if VPS
import Network
#endif

enum Tab: Int, CaseIterable {
    case desk = 0
    case charts = 1
    case lab = 2

    var title: String { ["Desk", "Charts", "Lab"][rawValue] }
    var key: String { ["desk", "charts", "lab"][rawValue] }
    private var envVar: String { ["HOMEBASE_DESK_URL", "HOMEBASE_CHARTS_URL", "HOMEBASE_BACKTEST_URL"][rawValue] }
    private var defaultURLString: String {
        #if VPS
        // not localhost: WebKit never proxies loopback. Only the server resolves this name (its /etc/hosts, through the
        // SOCKS proxy), so this app can never land on the Mac's own Desk; the server's nginx hands it on as 127.0.0.1.
        ["http://homebase-vps:8850/", "http://homebase-vps:8852/", "http://homebase-vps:8852/backtest"][rawValue]
        #else
        ["http://localhost:8850/", "http://localhost:8852/", "http://localhost:8852/backtest"][rawValue]
        #endif
    }
    /// The tab's classic page. Overridable by environment so a test build points at dev servers.
    var baseURL: URL {
        let raw = ProcessInfo.processInfo.environment[envVar] ?? defaultURLString
        return URL(string: raw) ?? URL(string: defaultURLString)!
    }
}

/// What the skin gives one tab: where it starts (nil = the classic page) and what is injected.
struct TabSkin {
    var startPath: String?
    var css: String
    var js: String
}

struct Skin {
    var tabs: [Tab: TabSkin]
}

/// Where this macOS puts the traffic lights in a window with a unified toolbar, and how tall that toolbar is.
struct Chrome {
    var toolbarHeight: CGFloat      // title bar + toolbar, in points
    var buttonX: [CGFloat]          // left edge of close / minimize / zoom, from the window's left edge
    var buttonSize: NSSize
    var measured: Bool
    var cornerRadius: CGFloat = 26  // the window's own corner radius (26 with a unified toolbar, 16 without)
    /// The width the page must keep clear at the left of its toolbar.
    var reserved: CGFloat { (buttonX.last ?? 60) + buttonSize.width + 12 }
}

func env(_ k: String) -> String? {
    let v = ProcessInfo.processInfo.environment[k]
    return (v == nil || v!.isEmpty) ? nil : v
}

/// A small synchronous GET (launch and ⌘R only): the body of a 200, else nil.
func fetch(_ url: URL, timeout: TimeInterval = 3) -> Data? {
    var req = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalAndRemoteCacheData, timeoutInterval: timeout)
    req.httpMethod = "GET"
    let sem = DispatchSemaphore(value: 0)
    var out: Data?
    let conf = URLSessionConfiguration.ephemeral
    #if VPS
    conf.proxyConfigurations = [vpsProxy]
    #endif
    let task = URLSession(configuration: conf).dataTask(with: req) { data, resp, _ in
        if let http = resp as? HTTPURLResponse, http.statusCode == 200 { out = data }
        sem.signal()
    }
    task.resume()
    _ = sem.wait(timeout: .now() + timeout + 1)
    return out
}

/// Many small GETs (launch and ⌘R only): one chain per server (origin), the chains side by side, each chain one fetch()
/// after another in the given order. Every server still gets its GETs one at a time, each with fetch()'s own budget,
/// so launch waits for the slowest server, not for the sum. Each distinct URL is fetched once; every chain stops at the
/// first miss (the caller then drops the whole skin anyway). The bodies that answered 200, keyed by absolute URL.
func fetchAll(_ urls: [URL]) -> [URL: Data] {
    var chains: [URL: [URL]] = [:]
    for u in urls.map({ $0.absoluteURL }) where !(chains[origin(of: u)]?.contains(u) ?? false) {
        chains[origin(of: u), default: []].append(u)
    }
    let list = Array(chains.values), lock = NSLock()
    var out: [URL: Data] = [:], missed = false
    DispatchQueue.concurrentPerform(iterations: list.count) { i in
        for u in list[i] {
            lock.lock(); let stop = missed; lock.unlock()
            if stop { return }
            let d = fetch(u)
            lock.lock(); if let d = d { out[u] = d } else { missed = true }; lock.unlock()
            if d == nil { return }
        }
    }
    return out
}

func jsString(_ s: String) -> String {
    guard let d = try? JSONSerialization.data(withJSONObject: [s]), let t = String(data: d, encoding: .utf8) else { return "\"\"" }
    return String(t.dropFirst().dropLast())     // ["..."] -> "..."
}

/// Which machine's Homebase this app shows: window.HB_MACHINE on every page ('server' = the Chicago VPS, 'mac' = this Mac).
#if VPS
let machine = "server"
#else
let machine = "mac"
#endif

func origin(of url: URL) -> URL {
    var c = URLComponents()
    c.scheme = url.scheme; c.host = url.host; c.port = url.port
    return c.url ?? url
}

#if VPS
let vpsHost = (Bundle.main.object(forInfoDictionaryKey: "HomebaseVPSHost") as? String) ?? "root@144.202.51.163"
let vpsPort: UInt16 = 1081            // not server-window.sh's 1080: this app owns its proxy
let vpsProxy = ProxyConfiguration(socksv5Proxy: .hostPort(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: vpsPort)!))
var vpsTunnel: Process?
// Desk only on the VPS (owner, 2026-10-26): no page switcher, no "Open in the Lab" / "Show on chart" buttons. No pill: the
// machine is the page's own toolbar chip (window.HB_MACHINE = 'server'); with no skin, the title bar says the app's name.
let vpsDeskOnlyJS = """
(() => { const st = document.createElement('style'); st.textContent = '#pgSw,button[onclick*="InLab("]{display:none!important}';
document.documentElement.appendChild(st); })();
"""

func vpsProxyUp() -> Bool {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    var a = sockaddr_in()
    a.sin_family = sa_family_t(AF_INET); a.sin_port = vpsPort.bigEndian; a.sin_addr.s_addr = inet_addr("127.0.0.1")
    return withUnsafePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 } }
}

/// The SSH SOCKS proxy to the server: started when it is not already up, and waited for (up to 10 s).
func vpsEnsureTunnel() {
    if vpsProxyUp() { return }
    if let t = vpsTunnel, t.isRunning { t.terminate() }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/ssh")
    p.arguments = ["-N", "-D", "127.0.0.1:\(vpsPort)", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                   "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=8", vpsHost]
    do { try p.run() } catch { return }
    vpsTunnel = p
    for _ in 0..<50 where !vpsProxyUp() { usleep(200_000) }
}
#endif

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler,
                   NSMenuItemValidation {
    var window: NSWindow!
    var webViews: [Tab: WKWebView] = [:]
    var currentTab: Tab = .desk
    var skin: Skin?
    var chrome = Chrome(toolbarHeight: 52, buttonX: [20, 40, 60], buttonSize: NSSize(width: 14, height: 16), measured: false)
    var lastMouseDown: NSEvent?
    var notice: (box: NSBox, label: NSTextField)?     // over the tabs while the current tab's page does not load
    var down: Set<Tab> = []                            // the tabs whose last load failed (retrying)
    var connecting: NSWindow?                          // VPS: "Connecting to the Chicago server…" until the window opens

    private let lastTabKey = "HomebaseLastTab"
    private let appName = (Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String) ?? "Homebase"
    private let debugDir = env("HB_DEBUG_DIR")
    private var debugQueue: [Tab] = []
    private var debugDragRequests = 0
    private var debugLog: [String] = []

    var skinned: Bool { skin != nil }

    // ---------------------------------------------------------------- launch
    func applicationDidFinishLaunching(_ n: Notification) {
        #if VPS
        // macOS 26 dark icon style darkens the bundle icon; a set image is shown as drawn (white, black house)
        if let p = Bundle.main.path(forResource: "HomebaseVPS", ofType: "icns") { NSApp.applicationIconImage = NSImage(contentsOfFile: p) }
        WKWebsiteDataStore.default().proxyConfigurations = [vpsProxy]     // before any web view exists
        // the proxy comes up (up to 10 s) and the skin loads through it off the main thread; a small window says so meanwhile
        buildMenu()     // ⌘Q works while it waits (built again, skinned or not, when the window opens)
        let wait = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 420, height: 140), styleMask: [.titled, .closable],
                            backing: .buffered, defer: false)
        wait.title = appName
        wait.isReleasedWhenClosed = false
        _ = addNotice(to: wait.contentView!, "Connecting to the Chicago server…")
        wait.center()
        wait.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        connecting = wait
        DispatchQueue.global().async {
            vpsEnsureTunnel()
            let s = self.loadSkin()
            DispatchQueue.main.async {
                Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { _ in   // a dropped link comes back by itself
                    DispatchQueue.global().async { vpsEnsureTunnel() }
                }
                self.skin = s
                self.openWindow()
            }
        }
        #else
        skin = loadSkin()
        openWindow()
        #endif
    }

    private func openWindow() {
        if skinned { chrome = measureChrome() }
        if env("HB_DEBUG_APPEARANCE") == "dark" { NSApp.appearance = NSAppearance(named: .darkAqua) }
        else if env("HB_DEBUG_APPEARANCE") == "light" { NSApp.appearance = NSAppearance(named: .aqua) }
        else if debugDir == nil { applyAppearance() }
        buildMenu()   // without this, ⌘V/⌘C/⌘A do nothing on macOS

        var size = NSSize(width: 1440, height: 900)
        if let s = env("HB_DEBUG_SIZE"), let x = s.firstIndex(of: "x"),
           let w = Double(s[s.startIndex..<x]), let h = Double(s[s.index(after: x)...]) { size = NSSize(width: w, height: h) }
        var style: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable]
        if skinned { style.insert(.fullSizeContentView) }
        let win = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: style, backing: .buffered, defer: false)
        win.title = appName
        win.delegate = self
        win.minSize = NSSize(width: 980, height: 620)
        if skinned {
            win.titlebarAppearsTransparent = true
            win.titleVisibility = .hidden
            win.isMovableByWindowBackground = false
            // an empty unified toolbar: macOS 26's toolbar-window shape (26 pt corners), lights placed by the system
            let tb = NSToolbar(identifier: "hb.main")
            tb.displayMode = .iconOnly
            win.toolbar = tb
            win.toolbarStyle = .unified
            win.titlebarSeparatorStyle = .none
        }
        if debugDir != nil {
            if env("HB_DEBUG_OFFSCREEN") != nil { win.setFrameOrigin(NSPoint(x: -30000, y: -30000)) } else { win.center() }
        } else {
            win.center()
            win.setFrameAutosaveName(skinned ? "HomebaseNextMain" : "HomebaseNextClassic")
        }
        window = win
        notice = addNotice(to: win.contentView!, "")
        notice?.box.isHidden = true

        NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown]) { [weak self] e in self?.lastMouseDown = e; return e }
        let nc = NotificationCenter.default
        for name in [NSWindow.didResizeNotification, NSWindow.didEndLiveResizeNotification, NSWindow.didExitFullScreenNotification,
                     NSWindow.didEnterFullScreenNotification, NSWindow.didBecomeKeyNotification, NSWindow.didResignKeyNotification,
                     NSWindow.didChangeBackingPropertiesNotification] {
            nc.addObserver(self, selector: #selector(windowChanged(_:)), name: name, object: win)
        }

        let saved = UserDefaults.standard.object(forKey: lastTabKey) as? Int
        var startTab = saved.flatMap { Tab(rawValue: $0) } ?? .desk
        #if VPS
        startTab = .desk
        #endif
        if debugDir != nil {
            let names = (env("HB_DEBUG_TABS") ?? "desk").split(separator: ",").map { String($0) }
            debugQueue = Tab.allCases.filter { names.contains($0.key) }
            startTab = debugQueue.first ?? .desk
        }

        // The dashboard sends no cache headers, and WebKit's heuristic cache otherwise keeps serving a page (and
        // its scripts) from before an upgrade. Cleared ONCE at launch, for the shared default data store every
        // tab's WKWebView uses -- before any tab loads. Cookies and localStorage are kept.
        let caches: Set<String> = [WKWebsiteDataTypeDiskCache, WKWebsiteDataTypeMemoryCache]
        WKWebsiteDataStore.default().removeData(ofTypes: caches, modifiedSince: Date(timeIntervalSince1970: 0)) { [weak self] in
            guard let self = self else { return }
            self.showTab(startTab)
            self.window.makeKeyAndOrderFront(nil)
            self.connecting?.close()      // after the window is up: closing the last window quits
            self.connecting = nil
        }

        NSApp.setActivationPolicy(.regular)
        if debugDir == nil || env("HB_DEBUG_OFFSCREEN") == nil { NSApp.activate(ignoringOtherApps: true) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    /// A plain sentence in the middle of a filled view: what the window shows instead of a blank page.
    private func addNotice(to view: NSView, _ text: String) -> (box: NSBox, label: NSTextField) {
        let box = NSBox(frame: view.bounds)
        box.boxType = .custom
        box.titlePosition = .noTitle
        box.borderWidth = 0
        box.fillColor = .windowBackgroundColor
        box.autoresizingMask = [.width, .height]
        let label = NSTextField(wrappingLabelWithString: text)
        label.alignment = .center
        label.font = .systemFont(ofSize: 15)
        label.textColor = .secondaryLabelColor
        label.translatesAutoresizingMaskIntoConstraints = false
        box.contentView!.addSubview(label)
        NSLayoutConstraint.activate([label.centerXAnchor.constraint(equalTo: box.centerXAnchor),
                                     label.centerYAnchor.constraint(equalTo: box.centerYAnchor),
                                     label.widthAnchor.constraint(lessThanOrEqualToConstant: 480)])
        view.addSubview(box)
        return (box, label)
    }

    /// The current tab's page did not load: say so over it, plainly, until a retry gets through.
    private func showNotice() {
        guard let n = notice else { return }
        n.box.isHidden = !down.contains(currentTab)
        if n.box.isHidden { return }
        #if VPS
        n.label.stringValue = "The Chicago server is not reachable.\nTrying again…"
        #else
        n.label.stringValue = (currentTab == .desk ? "The Desk is not running on this Mac." : "Charts and the Lab are not running on this Mac.") + "\nTrying again…"
        #endif
        window.contentView!.addSubview(n.box, positioned: .above, relativeTo: nil)    // over the web views (added later)
    }

    // ---------------------------------------------------------------- unsaved Lab code: ⌘R, ⌘W, ⌘Q ask first
    // A web view shows no beforeunload prompt, so the Lab's own guard never fires in the app: the app asks the Lab page
    // (its window.hbHasUnsaved) and, when a script is edited and not saved, asks the owner natively.
    private var leaving = false     // yes was said once: the quit that follows ⌘W does not ask again

    private func askIfLabUnsaved(_ verb: String, _ go: @escaping (Bool) -> Void) {
        guard !leaving, let lab = webViews[.lab] else { go(true); return }
        var answered = false
        let answer: (Bool?) -> Void = { dirty in      // nil: the page did not answer in time
            if answered { return }
            answered = true
            if dirty == false { go(true); return }
            let a = NSAlert()
            a.messageText = dirty == true ? "A Lab script is not saved" : "The Lab did not answer"
            a.informativeText = dirty == true ? "\(verb) anyway and lose the changes?" : "A Lab script may not be saved. \(verb) anyway?"
            a.addButton(withTitle: "Cancel")
            a.addButton(withTitle: verb).hasDestructiveAction = true
            go(a.runModal() == .alertSecondButtonReturn)
        }
        lab.evaluateJavaScript("window.hbHasUnsaved?.() === true") { r, _ in answer((r as? Bool) == true) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { answer(nil) }    // a busy page never holds the app
    }

    func applicationShouldTerminate(_ s: NSApplication) -> NSApplication.TerminateReply {
        if leaving || webViews[.lab] == nil { return .terminateNow }
        askIfLabUnsaved("Quit") { [weak self] ok in
            self?.leaving = ok
            NSApp.reply(toApplicationShouldTerminate: ok)
        }
        return .terminateLater
    }

    // ⌘W and the close button: closing the window quits the app
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if leaving || webViews[.lab] == nil { return true }
        askIfLabUnsaved("Close") { [weak self] ok in
            if ok { self?.leaving = true; sender.close() }
        }
        return false
    }

    #if VPS
    func applicationWillTerminate(_ n: Notification) { vpsTunnel?.terminate() }
    #endif

    // ---------------------------------------------------------------- the skin
    /// All of the skin or none of it: a manifest naming every tab, and every file it lists loading.
    private func loadSkin() -> Skin? {
        if env("HB_NO_SKIN") != nil { return nil }
        let desk = origin(of: Tab.desk.baseURL)
        guard let murl = URL(string: "/static/apple/manifest.json", relativeTo: desk),
              let data = fetch(murl),
              let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let tabs = root["tabs"] as? [String: Any] else { return nil }
        let shared = root["shared"] as? [String: Any] ?? [:]
        #if VPS
        let shown: [Tab] = [.desk]      // the VPS app is the Desk only: a Charts/Lab file that fails cannot unskin it
        #else
        let shown = Tab.allCases
        #endif
        // every file of every tab fetched first (one chain per server, the servers side by side), then read below in order
        var urls: [URL] = []
        for tab in shown {
            guard let t = tabs[tab.key] as? [String: Any] else { return nil }
            let base = origin(of: tab.baseURL)
            var paths: [String] = (shared["css"] as? [String] ?? []) + (t["css"] as? [String] ?? [])
            paths += (shared["js"] as? [String] ?? []) + (t["js"] as? [String] ?? [])
            if let s = t["url"] as? String { paths.append(s) }
            urls += paths.compactMap { URL(string: $0, relativeTo: base) }
        }
        let bodies = fetchAll(urls)
        func got(_ u: URL) -> Data? { bodies[u.absoluteURL] }
        func text(_ paths: [String], _ base: URL) -> String? {
            var out: [String] = []
            for p in paths {
                guard let u = URL(string: p, relativeTo: base), let d = got(u), let t = String(data: d, encoding: .utf8) else { return nil }
                out.append("/* \(p) */\n" + t)
            }
            return out.joined(separator: "\n")
        }
        var result: [Tab: TabSkin] = [:]
        for tab in shown {
            guard let t = tabs[tab.key] as? [String: Any] else { return nil }
            let base = origin(of: tab.baseURL)
            let cssPaths = (shared["css"] as? [String] ?? []) + (t["css"] as? [String] ?? [])
            let jsPaths = (shared["js"] as? [String] ?? []) + (t["js"] as? [String] ?? [])
            guard let css = text(cssPaths, base), let js = text(jsPaths, base) else { return nil }
            var start = t["url"] as? String
            if let s = start, let u = URL(string: s, relativeTo: base), got(u) == nil { start = nil; return nil }
            result[tab] = TabSkin(startPath: start, css: css, js: js)
        }
        return Skin(tabs: result)
    }

    /// Ask the system, not a constant: a hidden window with a unified toolbar tells us the toolbar's height and
    /// where the traffic lights go on this macOS.
    private func measureChrome() -> Chrome {
        var c = chrome
        let ref = NSWindow(contentRect: NSRect(x: -30000, y: -30000, width: 900, height: 600),
                           styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                           backing: .buffered, defer: false)
        ref.isReleasedWhenClosed = false
        ref.titleVisibility = .hidden
        let tb = NSToolbar(identifier: "hb.reference")
        tb.displayMode = .iconOnly
        ref.toolbar = tb
        ref.toolbarStyle = .unified
        ref.layoutIfNeeded()
        let h = ref.frame.height - ref.contentLayoutRect.height
        var xs: [CGFloat] = []
        var size = c.buttonSize
        for kind in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] {
            if let b = ref.standardWindowButton(kind) {
                let r = b.convert(b.bounds, to: nil)
                xs.append(r.minX)
                size = r.size
            }
        }
        // the corner radius AppKit gives a toolbar window (a private, read-only getter: asked, never set)
        var radius: CGFloat = 26
        if ref.responds(to: Selector(("_cornerRadius"))),
           let r = (ref.value(forKey: "_cornerRadius") as? NSNumber)?.doubleValue, r >= 6, r <= 40 { radius = CGFloat(r) }
        ref.toolbar = nil
        ref.close()
        if h >= 28, h <= 90, xs.count == 3, xs[0] >= 4, xs[2] < 140 {
            c = Chrome(toolbarHeight: h.rounded(), buttonX: xs, buttonSize: size, measured: true)
        }
        c.cornerRadius = radius
        return c
    }

    /// Full screen has no traffic lights, and the (empty, native) toolbar would sit opaque over the page's own toolbar:
    /// the tabs and buttons were hidden under it. The page draws that band itself, so the native one steps aside
    /// while the window is full screen and comes back when it leaves.
    func windowWillEnterFullScreen(_ n: Notification) { if skinned { window.toolbar?.isVisible = false } }
    func windowDidExitFullScreen(_ n: Notification) { if skinned { window.toolbar?.isVisible = true } }

    @objc private func windowChanged(_ n: Notification) {
        guard skinned else { return }
        let full = window.styleMask.contains(.fullScreen)
        let key = window.isKeyWindow
        let js = "(function(){var d=document.documentElement;d.classList.toggle('hb-fullscreen',\(full));d.classList.toggle('hb-inactive',\(!key));})();"
        for (_, v) in webViews { v.evaluateJavaScript(js, completionHandler: nil) }
    }

    /// What is injected before the page's own scripts run.
    private func startScript(for tab: Tab) -> String {
        guard let s = skin?.tabs[tab] else { return "" }
        let debug = debugDir != nil
        return """
        (function(){
          var d=document.documentElement;
          d.classList.add('hb-apple','hb-native');
          window.HB_NATIVE={v:3,tab:'\(tab.key)',toolbar:\(Int(chrome.toolbarHeight)),trafficLights:\(Int(chrome.reserved.rounded())),radius:\(Int(chrome.cornerRadius.rounded()))};
          d.style.setProperty('--hb-native-toolbar','\(Int(chrome.toolbarHeight))px');
          d.style.setProperty('--hb-native-tl','\(Int(chrome.reserved.rounded()))px');
          d.style.setProperty('--hb-native-radius','\(Int(chrome.cornerRadius.rounded()))px');
          var css=\(jsString(s.css));
          if(css){var st=document.createElement('style');st.id='hb-apple-skin';st.textContent=css;d.appendChild(st);
            document.addEventListener('DOMContentLoaded',function(){(document.head||d).appendChild(st);});}
          var NO='button,a,input,select,textarea,summary,label,[role="button"],[role="switch"],[role="tab"],[contenteditable],.hb-nodrag';
          document.addEventListener('mousedown',function(e){
            if(e.button!==0||!e.target.closest)return;
            if(!e.target.closest('[data-hb-drag],.hb-drag'))return;
            if(e.target.closest(NO))return;
            window.webkit.messageHandlers.hb.postMessage({op:e.detail===2?'zoom':'drag'});
          },true);
          \(debug ? "window.__hbErrors=[];window.addEventListener('error',function(e){window.__hbErrors.push(String(e.message)+' @'+(e.filename||'')+':'+(e.lineno||''));});window.addEventListener('unhandledrejection',function(e){window.__hbErrors.push('rejection: '+String(e.reason));});window.__hbDown=[];document.addEventListener('mousedown',function(e){window.__hbDown.push([e.clientX,e.clientY,e.target.tagName,String(e.target.className).slice(0,60)]);},true);" : "")
        })();
        """
    }

    /// Every load and every ⌘R (removeAllUserScripts wipes them all): the machine first, skinned or not -- the page's
    /// machine chip and its words read window.HB_MACHINE -- and the VPS app's Desk-only style.
    private func installScripts(_ controller: WKUserContentController, tab: Tab) {
        controller.removeAllUserScripts()
        controller.addUserScript(WKUserScript(source: "window.HB_MACHINE='\(machine)';", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        #if VPS
        controller.addUserScript(WKUserScript(source: vpsDeskOnlyJS, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        #endif
        guard let s = skin?.tabs[tab] else { return }
        controller.addUserScript(WKUserScript(source: startScript(for: tab), injectionTime: .atDocumentStart, forMainFrameOnly: true))
        if !s.js.isEmpty {
            controller.addUserScript(WKUserScript(source: s.js, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        }
    }

    /// Where a tab starts: the skin's own page for it, else the classic page.
    private func startURL(for tab: Tab) -> URL {
        if let p = skin?.tabs[tab]?.startPath, let u = URL(string: p, relativeTo: origin(of: tab.baseURL)) { return u.absoluteURL }
        return tab.baseURL
    }

    // ---------------------------------------------------------------- tabs: lazy web views on one content view
    /// `fragment`: a link's #part (the Lab's "On the Desk" is <desk>/#lab=<name>): set on an open tab, kept on a new one.
    private func webView(for tab: Tab, fragment: String? = nil) -> WKWebView {
        if let existing = webViews[tab] {
            if let f = fragment { existing.evaluateJavaScript("location.hash=\(jsString("#" + f))", completionHandler: nil) }
            return existing
        }
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "hb")
        installScripts(config.userContentController, tab: tab)
        let wv = WKWebView(frame: window.contentView!.bounds, configuration: config)
        wv.autoresizingMask = [.width, .height]
        wv.navigationDelegate = self
        wv.uiDelegate = self
        wv.allowsBackForwardNavigationGestures = false
        if skinned {
            wv.setValue(false, forKey: "drawsBackground")       // the window's background shows until the page paints
            wv.underPageBackgroundColor = .windowBackgroundColor
        }
        wv.isHidden = true
        window.contentView!.addSubview(wv)
        webViews[tab] = wv
        var start = URLComponents(url: startURL(for: tab), resolvingAgainstBaseURL: true)
        if let f = fragment { start?.fragment = f }
        wv.load(URLRequest(url: start?.url ?? startURL(for: tab)))
        return wv
    }

    private func tab(for webView: WKWebView) -> Tab? {
        webViews.first(where: { $0.value === webView })?.key
    }

    func showTab(_ tab: Tab, fragment: String? = nil) {
        #if VPS
        if tab != .desk { return }      // the VPS app is the Desk only (owner, 2026-10-26); Charts and Lab live on the Mac
        #endif
        let target = webView(for: tab, fragment: fragment)   // creates + starts loading on first visit
        for (t, v) in webViews { v.isHidden = (t != tab) }
        currentTab = tab
        if debugDir == nil { UserDefaults.standard.set(tab.rawValue, forKey: lastTabKey) }
        window.makeFirstResponder(target)
        showNotice()
    }

    // ---------------------------------------------------------------- the page asks for the window
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        guard let body = m.body as? [String: Any], let op = body["op"] as? String else { return }
        switch op {
        case "drag":
            if debugDir != nil { debugDragRequests += 1; return }
            if let e = lastMouseDown, e.window === window, ProcessInfo.processInfo.systemUptime - e.timestamp < 0.6 {
                window.performDrag(with: e)
            }
        case "zoom":
            if debugDir != nil { return }
            switch UserDefaults.standard.string(forKey: "AppleActionOnDoubleClick") ?? "Maximize" {
            case "Minimize": window.performMiniaturize(nil)
            case "None": break
            default: window.performZoom(nil)
            }
        default: break
        }
    }

    // ---------------------------------------------------------------- appearance (View > Appearance)
    private let appearanceKey = "HomebaseNextAppearance"      // "system" | "light" | "dark"
    private func applyAppearance() {
        switch UserDefaults.standard.string(forKey: appearanceKey) ?? "system" {
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        case "dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        default: NSApp.appearance = nil
        }
    }
    @objc private func pickAppearance(_ sender: NSMenuItem) {
        UserDefaults.standard.set(["system", "light", "dark"][max(0, min(2, sender.tag))], forKey: appearanceKey)
        applyAppearance()
        for item in sender.menu?.items ?? [] { item.state = item === sender ? .on : .off }
    }

    /// Charts has no sidebar: its Toggle Sidebar is greyed out there. Before the window opens (VPS: "Connecting…")
    /// every item of ours is greyed out (Reload, Desk): they need the window. Quit and Hide are the app's own.
    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        window != nil
            && !(item.action == #selector(pageCommand(_:)) && item.representedObject as? String == "sidebar" && currentTab == .charts)
    }

    /// A View-menu command the page carries out (toggle the sidebar / the inspector): the page owns its layout.
    @objc private func pageCommand(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String, let wv = webViews[currentTab] else { return }
        wv.evaluateJavaScript("window.HBApple&&HBApple.command&&HBApple.command(\(jsString(name)))", completionHandler: nil)
    }

    // ---------------------------------------------------------------- link interception
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard navigationAction.targetFrame?.isMainFrame == true,
              let url = navigationAction.request.url,
              let sourceTab = tab(for: webView) else {
            decisionHandler(.allow); return
        }
        if let target = tabFor(url: url) {
            if target != sourceTab {
                decisionHandler(.cancel)
                showTab(target, fragment: target == .desk ? url.fragment(percentEncoded: false) : nil)   // the Desk opens the Lab strategy the link names
            } else {
                decisionHandler(.allow)
            }
            return
        }
        // a URL that is not one of our own three tabs never navigates a tab away from its own page
        decisionHandler(.cancel)
        openExternal(url)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if let target = tabFor(url: url) { showTab(target) } else { openExternal(url) }
        }
        return nil
    }

    // the page's alert() and confirm(): native panels (without them a web view drops alert and answers confirm "no")
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.runModal()
        completionHandler()
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancel")
        completionHandler(a.runModal() == .alertFirstButtonReturn)
    }

    /// http/https only: a page this viewer merely navigated to must never launch a local file or another app.
    private func openExternal(_ url: URL) {
        guard let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" else { return }
        NSWorkspace.shared.open(url)
    }

    /// Which tab a URL belongs to, by origin and, for Charts/Lab which share one origin, by path.
    private func tabFor(url: URL) -> Tab? {
        func sameOrigin(_ a: URL, _ b: URL) -> Bool { a.scheme == b.scheme && a.host == b.host && a.port == b.port }
        let desk = Tab.desk.baseURL, charts = Tab.charts.baseURL, lab = Tab.lab.baseURL
        if sameOrigin(url, desk) { return .desk }
        if sameOrigin(url, charts) || sameOrigin(url, lab) {
            let labPath = lab.path.isEmpty || lab.path == "/" ? "/backtest" : lab.path
            return url.path.hasPrefix(labPath) ? .lab : .charts
        }
        return nil
    }

    // service mid-restart? retry until that tab's page answers -- per tab, so one tab's outage never touches another's
    func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { retry(w, e) }
    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { retry(w, e) }
    private func retry(_ w: WKWebView, _ e: Error) {
        guard let tab = tab(for: w) else { return }
        let err = e as NSError      // a cancelled load (another one took its place) is not a page that is down
        if !(err.domain == NSURLErrorDomain && err.code == NSURLErrorCancelled) && !(err.domain == "WebKitErrorDomain" && err.code == 102) {
            down.insert(tab)
            showNotice()
        }
        if debugDir != nil { debugLog.append("load failed: \(tab.key)") }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self, weak w] in
            guard let self = self else { return }
            w?.load(URLRequest(url: self.startURL(for: tab)))
        }
    }

    func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
        if let t = tab(for: w) { down.remove(t) }
        showNotice()
        windowChanged(Notification(name: NSWindow.didBecomeKeyNotification))
        guard debugDir != nil, let tab = tab(for: w), debugQueue.first == tab else { return }
        let wait = Double(env("HB_DEBUG_WAIT") ?? "4") ?? 4
        DispatchQueue.main.asyncAfter(deadline: .now() + wait) { [weak self] in self?.debugCapture(tab) }
    }

    // ⌘R: the skin's files and the CURRENT tab's page, both from the server, never from the cache
    @objc func reloadPage() {
        if currentTab != .lab { reloadNow(); return }    // only the current tab's page is reloaded
        askIfLabUnsaved("Reload") { [weak self] ok in if ok { self?.reloadNow() } }
    }

    private func reloadNow() {
        // the window's own style depends on whether there is a skin: never half-switch. A failed reload (a service
        // restarting) keeps the design already loaded; a design back after an unskinned launch waits for a reopen.
        let old = skin, fresh = loadSkin()
        skin = old == nil ? nil : fresh ?? old
        if (old == nil) != (fresh == nil) {
            let a = NSAlert()
            a.messageText = fresh == nil ? "The new design could not be reloaded" : "The new design is available again"
            a.informativeText = fresh == nil ? "The one already loaded is kept." : "Quit and reopen \(appName) to switch."
            a.runModal()
        }
        for (t, v) in webViews { installScripts(v.configuration.userContentController, tab: t) }
        webViews[currentTab]?.reloadFromOrigin()
    }

    @objc private func selectTabFromMenu(_ sender: NSMenuItem) {
        if let tab = Tab(rawValue: sender.tag) { showTab(tab) }
    }

    private func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu()
        let reload = NSMenuItem(title: "Reload", action: #selector(reloadPage), keyEquivalent: "r")
        reload.target = self
        appMenu.addItem(reload)
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Hide \(appName)", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Quit \(appName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
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
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit

        let viewItem = NSMenuItem()
        main.addItem(viewItem)
        let viewMenu = NSMenu(title: "View")
        for tab in Tab.allCases {
            #if VPS
            if tab != .desk { continue }
            #endif
            let item = NSMenuItem(title: tab.title, action: #selector(selectTabFromMenu(_:)), keyEquivalent: String(tab.rawValue + 1))
            item.target = self
            item.tag = tab.rawValue
            viewMenu.addItem(item)
        }
        if skinned {
            viewMenu.addItem(NSMenuItem.separator())
            for (title, cmd, key, mods) in [("Toggle Sidebar", "sidebar", "s", NSEvent.ModifierFlags([.command, .control])),
                                            ("Toggle Inspector", "inspector", "i", NSEvent.ModifierFlags([.command, .option]))] {
                let it = NSMenuItem(title: title, action: #selector(pageCommand(_:)), keyEquivalent: key)
                it.keyEquivalentModifierMask = mods
                it.target = self
                it.representedObject = cmd
                viewMenu.addItem(it)
            }
            let aItem = NSMenuItem(title: "Appearance", action: nil, keyEquivalent: "")
            let aMenu = NSMenu(title: "Appearance")
            let current = UserDefaults.standard.string(forKey: appearanceKey) ?? "system"
            for (i, (title, key)) in [("Match System", "system"), ("Light", "light"), ("Dark", "dark")].enumerated() {
                let it = NSMenuItem(title: title, action: #selector(pickAppearance(_:)), keyEquivalent: "")
                it.target = self
                it.tag = i
                it.state = current == key ? .on : .off
                aMenu.addItem(it)
            }
            aItem.submenu = aMenu
            viewMenu.addItem(aItem)
        }
        viewMenu.addItem(NSMenuItem.separator())
        viewMenu.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f").keyEquivalentModifierMask = [.command, .control]
        viewItem.submenu = viewMenu

        let winItem = NSMenuItem()
        main.addItem(winItem)
        let winMenu = NSMenu(title: "Window")
        winMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        winMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        winItem.submenu = winMenu
        NSApp.windowsMenu = winMenu

        NSApp.mainMenu = main
    }

    // ---------------------------------------------------------------- debug: snapshot + diagnostics, then quit
    private func debugCapture(_ tab: Tab) {
        guard let dir = debugDir, let wv = webViews[tab] else { return }
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        let finish: () -> Void = { [weak self] in
            guard let self = self else { return }
            // a click in the middle of the toolbar strip: does the page get it, and does it ask for a drag?
            let before = self.debugDragRequests
            let p = NSPoint(x: self.window.frame.width / 2, y: self.window.frame.height - self.chrome.toolbarHeight / 2)
            var hit = "?"
            if let frameView = self.window.contentView?.superview {
                var parts: [String] = []
                for (label, pt) in [("centre", p), ("left200", NSPoint(x: 200, y: p.y)), ("right40", NSPoint(x: self.window.frame.width - 40, y: p.y)),
                                    ("below", NSPoint(x: p.x, y: self.window.frame.height - self.chrome.toolbarHeight - 30))] {
                    let v = frameView.hitTest(pt)
                    parts.append(label + "=" + (v.map { String(describing: type(of: $0)) } ?? "nil"))
                }
                hit = parts.joined(separator: " ")
                let radius = (self.window.value(forKey: "_cornerRadius") as? NSNumber)?.doubleValue ?? -1
                hit += " cornerRadius=\(radius) contentLayoutTop=\(self.window.frame.height - self.window.contentLayoutRect.maxY)"
            }
            // straight to the web view (the window is not key in a debug run, so AppKit would swallow a first click)
            for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
                if let ev = NSEvent.mouseEvent(with: type, location: p, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                               windowNumber: self.window.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1) {
                    if type == .leftMouseDown { wv.mouseDown(with: ev) } else { wv.mouseUp(with: ev) }
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                let probe = """
                JSON.stringify({ua:navigator.userAgent,inner:[innerWidth,innerHeight],dpr:devicePixelRatio,cls:document.documentElement.className,
                  theme:document.documentElement.getAttribute('data-theme'),errors:window.__hbErrors||null,down:window.__hbDown||null,
                  title:document.title,native:window.HB_NATIVE||null,
                  supports:{backdrop:CSS.supports('backdrop-filter','blur(2px)'),wbackdrop:CSS.supports('-webkit-backdrop-filter','blur(2px)'),
                    backdropUrl:CSS.supports('backdrop-filter','url(#a)'),colorMix:CSS.supports('color','color-mix(in srgb, red 50%, blue)'),
                    has:CSS.supports('selector(:has(a))'),viewTransition:!!document.startViewTransition,textWrap:CSS.supports('text-wrap','balance')},
                  font:getComputedStyle(document.body).fontFamily,fontSize:getComputedStyle(document.body).fontSize,
                  extra:(window.__hbProbe?window.__hbProbe():null)})
                """
                wv.evaluateJavaScript(probe) { value, err in
                    var out: [String: Any] = ["tab": tab.key, "skinned": self.skinned, "hitAtToolbarCentre": hit,
                                              "dragRequests": self.debugDragRequests - before,
                                              "chrome": ["toolbar": self.chrome.toolbarHeight, "buttonX": self.chrome.buttonX,
                                                         "buttonW": self.chrome.buttonSize.width, "buttonH": self.chrome.buttonSize.height,
                                                         "measured": self.chrome.measured, "reserved": self.chrome.reserved],
                                              "window": [self.window.frame.width, self.window.frame.height],
                                              "webView": [wv.bounds.width, wv.bounds.height], "log": self.debugLog]
                    var lights: [[CGFloat]] = []
                    for kind in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] {
                        if let b = self.window.standardWindowButton(kind) {
                            let r = b.convert(b.bounds, to: nil)
                            lights.append([r.minX, self.window.frame.height - r.maxY, r.width, r.height])   // from the top-left
                        }
                    }
                    out["trafficLights"] = lights
                    if let s = value as? String, let d = s.data(using: .utf8), let j = try? JSONSerialization.jsonObject(with: d) { out["page"] = j }
                    if let err = err { out["probeError"] = String(describing: err) }
                    if let d = try? JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted, .sortedKeys]) {
                        try? d.write(to: URL(fileURLWithPath: dir + "/" + tab.key + ".json"))
                    }
                    let cfg = WKSnapshotConfiguration()
                    wv.takeSnapshot(with: cfg) { img, _ in
                        if let img = img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                           let png = rep.representation(using: .png, properties: [:]) {
                            try? png.write(to: URL(fileURLWithPath: dir + "/" + tab.key + ".png"))
                        }
                        self.debugQueue.removeFirst()
                        if let next = self.debugQueue.first { self.showTab(next) } else { NSApp.terminate(nil) }
                    }
                }
            }
        }
        if let path = env("HB_DEBUG_JS"), let js = try? String(contentsOfFile: path, encoding: .utf8) {
            wv.evaluateJavaScript(js) { _, _ in
                DispatchQueue.main.asyncAfter(deadline: .now() + (Double(env("HB_DEBUG_JSWAIT") ?? "1.5") ?? 1.5)) { finish() }
            }
        } else {
            finish()
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
if env("HB_DEBUG_DIR") != nil {
    // a debug run never outlives its job
    DispatchQueue.main.asyncAfter(deadline: .now() + (Double(env("HB_DEBUG_TIMEOUT") ?? "60") ?? 60)) { exit(3) }
}
app.run()
