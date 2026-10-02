// Homebase.app (built by build_app_apple.sh --as-homebase; "Homebase Next.app" when built beside it) — the same VIEWER
// as the classic one (the trading process is the launchd service; closing this
// window changes nothing about execution), with an Apple-style window and the new design delivered as a SKIN.
//
// What differs from main.swift (the classic viewer, which is left exactly as it is):
//  * The window has no title bar of its own: the page's toolbar IS the window's toolbar, and the traffic lights
//    sit inside it (full-size content view). The window carries an EMPTY unified NSToolbar, which is what gives
//    it macOS 26's toolbar-window shape (26 pt corners) and makes the system place the traffic lights itself.
//    The toolbar's height and the lights' position are READ FROM THE SYSTEM at launch, never hard-coded.
//    Proven with real HID events (HB_DEBUG_REAL, 2026-10-02): a click on a page button inside the strip
//    arrives as one mousedown/mouseup/click, and a press-drag on the empty strip moves the window by exactly
//    the pointer's travel. HB_NO_TOOLBAR=1 falls back to repositioning the lights by hand (16 pt corners).
//  * The page follows the window's appearance (View > Appearance: Match System / Light / Dark).
//  * The new design is a skin: /static/apple/manifest.json on the desk names, per tab, an optional start page
//    and the stylesheets / scripts to inject at document start. The classic pages are served unchanged, so the
//    classic app shows them exactly as before. No manifest, a broken one, or a file that does not load = this
//    app behaves like the classic one (its own title bar, no injection): all of the skin or none of it.
//  * A mousedown on the page's toolbar asks for a window drag through a message handler (a web view swallows
//    the mouse, so the page has to ask); a double-click there does what the system setting says.
//  * View menu: Desk / Charts / Lab (⌘1/⌘2/⌘3). Design samples open in their own window, marked "not live".
//
// Link handling is the classic viewer's (opus review, three-tabs): a navigation to one of the three tabs' own
// origins switches to that tab; anything else opens in the default browser. A tab never leaves its own origin.
//
// Debug (never set in the installed app): HB_DEBUG_DIR=<dir> makes the app load the tabs named in
// HB_DEBUG_TABS (default "desk"), wait HB_DEBUG_WAIT seconds each, optionally run the JS in the file
// HB_DEBUG_JS, write <dir>/<tab>.png (the web view's own snapshot) and <dir>/<tab>.json (diagnostics), then
// quit. HB_DEBUG_OFFSCREEN=1 keeps the window off every display; HB_DEBUG_SIZE=WxH sets its size.
import Cocoa
import WebKit

enum Tab: Int, CaseIterable {
    case desk = 0
    case charts = 1
    case lab = 2

    var title: String { ["Desk", "Charts", "Lab"][rawValue] }
    var key: String { ["desk", "charts", "lab"][rawValue] }
    private var envVar: String { ["HOMEBASE_DESK_URL", "HOMEBASE_CHARTS_URL", "HOMEBASE_BACKTEST_URL"][rawValue] }
    private var defaultURLString: String {
        ["http://localhost:8850/", "http://localhost:8852/", "http://localhost:8852/backtest"][rawValue]
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
    var samples: [(title: String, path: String)]
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
    let task = URLSession(configuration: .ephemeral).dataTask(with: req) { data, resp, _ in
        if let http = resp as? HTTPURLResponse, http.statusCode == 200 { out = data }
        sem.signal()
    }
    task.resume()
    _ = sem.wait(timeout: .now() + timeout + 1)
    return out
}

func jsString(_ s: String) -> String {
    guard let d = try? JSONSerialization.data(withJSONObject: [s]), let t = String(data: d, encoding: .utf8) else { return "\"\"" }
    return String(t.dropFirst().dropLast())     // ["..."] -> "..."
}

func origin(of url: URL) -> URL {
    var c = URLComponents()
    c.scheme = url.scheme; c.host = url.host; c.port = url.port
    return c.url ?? url
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webViews: [Tab: WKWebView] = [:]
    var currentTab: Tab = .desk
    var skin: Skin?
    var chrome = Chrome(toolbarHeight: 52, buttonX: [20, 40, 60], buttonSize: NSSize(width: 14, height: 16), measured: false)
    var sampleWindows: [NSWindow] = []
    var lastMouseDown: NSEvent?
    var relayouting = false
    var systemToolbar = false

    private let lastTabKey = "HomebaseLastTab"
    private let appName = (Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String) ?? "Homebase"
    private let debugDir = env("HB_DEBUG_DIR")
    private var debugQueue: [Tab] = []
    private var debugDragRequests = 0
    private var debugLog: [String] = []

    var skinned: Bool { skin != nil }

    // ---------------------------------------------------------------- launch
    func applicationDidFinishLaunching(_ n: Notification) {
        skin = loadSkin()
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
        win.title = "Homebase"
        win.delegate = self
        win.minSize = NSSize(width: 980, height: 620)
        if skinned {
            win.titlebarAppearsTransparent = true
            win.titleVisibility = .hidden
            win.isMovableByWindowBackground = false
            if env("HB_NO_TOOLBAR") == nil {
                // an empty unified toolbar: macOS 26's toolbar-window shape (26 pt corners), lights placed by the system
                let tb = NSToolbar(identifier: "hb.main")
                tb.displayMode = .iconOnly
                win.toolbar = tb
                win.toolbarStyle = .unified
                win.titlebarSeparatorStyle = .none
                systemToolbar = true
            }
        }
        if debugDir != nil {
            if env("HB_DEBUG_OFFSCREEN") != nil { win.setFrameOrigin(NSPoint(x: -30000, y: -30000)) } else { win.center() }
        } else {
            win.center()
            win.setFrameAutosaveName(skinned ? "HomebaseNextMain" : "HomebaseNextClassic")
        }
        window = win

        NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown]) { [weak self] e in self?.lastMouseDown = e; return e }
        let nc = NotificationCenter.default
        for name in [NSWindow.didResizeNotification, NSWindow.didEndLiveResizeNotification, NSWindow.didExitFullScreenNotification,
                     NSWindow.didEnterFullScreenNotification, NSWindow.didBecomeKeyNotification, NSWindow.didResignKeyNotification,
                     NSWindow.didChangeBackingPropertiesNotification] {
            nc.addObserver(self, selector: #selector(windowChanged(_:)), name: name, object: win)
        }

        let saved = UserDefaults.standard.object(forKey: lastTabKey) as? Int
        var startTab = saved.flatMap { Tab(rawValue: $0) } ?? .desk
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
            self.layoutTrafficLights()
        }

        NSApp.setActivationPolicy(.regular)
        if debugDir == nil || env("HB_DEBUG_OFFSCREEN") == nil { NSApp.activate(ignoringOtherApps: true) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

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
        func text(_ paths: [String], _ base: URL) -> String? {
            var out: [String] = []
            for p in paths {
                guard let u = URL(string: p, relativeTo: base), let d = fetch(u), let t = String(data: d, encoding: .utf8) else { return nil }
                out.append("/* \(p) */\n" + t)
            }
            return out.joined(separator: "\n")
        }
        var result: [Tab: TabSkin] = [:]
        for tab in Tab.allCases {
            guard let t = tabs[tab.key] as? [String: Any] else { return nil }
            let base = origin(of: tab.baseURL)
            let cssPaths = (shared["css"] as? [String] ?? []) + (t["css"] as? [String] ?? [])
            let jsPaths = (shared["js"] as? [String] ?? []) + (t["js"] as? [String] ?? [])
            guard let css = text(cssPaths, base), let js = text(jsPaths, base) else { return nil }
            var start = t["url"] as? String
            if let s = start, let u = URL(string: s, relativeTo: base), fetch(u) == nil { start = nil; return nil }
            result[tab] = TabSkin(startPath: start, css: css, js: js)
        }
        var samples: [(String, String)] = []
        for s in root["samples"] as? [[String: Any]] ?? [] {
            if let t = s["title"] as? String, let u = s["url"] as? String { samples.append((t, u)) }
        }
        return Skin(tabs: result, samples: samples)
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
        var radius: CGFloat = env("HB_NO_TOOLBAR") == nil ? 26 : 16
        if env("HB_NO_TOOLBAR") == nil, ref.responds(to: Selector(("_cornerRadius"))),
           let r = (ref.value(forKey: "_cornerRadius") as? NSNumber)?.doubleValue, r >= 6, r <= 40 { radius = CGFloat(r) }
        ref.toolbar = nil
        ref.close()
        if h >= 28, h <= 90, xs.count == 3, xs[0] >= 4, xs[2] < 140 {
            c = Chrome(toolbarHeight: h.rounded(), buttonX: xs, buttonSize: size, measured: true)
        }
        c.cornerRadius = radius
        return c
    }

    /// Put the traffic lights where the system puts them for a toolbar of this height. AppKit lays the title bar
    /// out again on resize, key changes and full screen, so this is re-applied each time.
    private func layoutTrafficLights() {
        guard skinned, !systemToolbar, let win = window, !relayouting, !win.styleMask.contains(.fullScreen),
              let close = win.standardWindowButton(.closeButton),
              let titlebar = close.superview, let container = titlebar.superview else { return }
        relayouting = true
        defer { relayouting = false }
        let h = chrome.toolbarHeight
        var cf = container.frame
        cf.size.height = h
        cf.origin.y = win.frame.height - h
        if container.frame != cf { container.frame = cf }
        let kinds: [NSWindow.ButtonType] = [.closeButton, .miniaturizeButton, .zoomButton]
        for (i, kind) in kinds.enumerated() {
            guard let b = win.standardWindowButton(kind) else { continue }
            let o = NSPoint(x: chrome.buttonX[i], y: ((h - b.frame.height) / 2).rounded())
            if b.frame.origin != o { b.setFrameOrigin(o) }
        }
    }

    @objc private func windowChanged(_ n: Notification) {
        layoutTrafficLights()
        DispatchQueue.main.async { [weak self] in self?.layoutTrafficLights() }
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

    private func installScripts(_ controller: WKUserContentController, tab: Tab) {
        controller.removeAllUserScripts()
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
    private func webView(for tab: Tab) -> WKWebView {
        if let existing = webViews[tab] { return existing }
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
        wv.load(URLRequest(url: startURL(for: tab)))
        return wv
    }

    private func tab(for webView: WKWebView) -> Tab? {
        webViews.first(where: { $0.value === webView })?.key
    }

    func showTab(_ tab: Tab) {
        let target = webView(for: tab)   // creates + starts loading on first visit
        for (t, v) in webViews { v.isHidden = (t != tab) }
        currentTab = tab
        if debugDir == nil { UserDefaults.standard.set(tab.rawValue, forKey: lastTabKey) }
        window.makeFirstResponder(target)
        layoutTrafficLights()
    }

    // ---------------------------------------------------------------- the page asks for the window
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        guard let body = m.body as? [String: Any], let op = body["op"] as? String else { return }
        switch op {
        case "drag":
            if debugDir != nil { debugDragRequests += 1; if env("HB_DEBUG_REAL") == nil { return } }
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
        case "tab":
            if let k = body["tab"] as? String, let t = Tab.allCases.first(where: { $0.key == k }) { showTab(t) }
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

    /// A View-menu command the page carries out (toggle the sidebar / the inspector): the page owns its layout.
    @objc private func pageCommand(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String, let wv = webViews[currentTab] else { return }
        wv.evaluateJavaScript("window.HBApple&&HBApple.command&&HBApple.command(\(jsString(name)))", completionHandler: nil)
    }

    // ---------------------------------------------------------------- link interception (the classic viewer's rule)
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
                showTab(target)
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
    func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { retry(w) }
    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { retry(w) }
    private func retry(_ w: WKWebView) {
        guard let tab = tab(for: w) else { return }
        if debugDir != nil { debugLog.append("load failed: \(tab.key)") }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self, weak w] in
            guard let self = self else { return }
            w?.load(URLRequest(url: self.startURL(for: tab)))
        }
    }

    func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
        windowChanged(Notification(name: NSWindow.didBecomeKeyNotification))
        guard debugDir != nil, let tab = tab(for: w), debugQueue.first == tab else { return }
        if env("HB_DEBUG_ROUTED") != nil { NSApp.activate(ignoringOtherApps: true); window.makeKeyAndOrderFront(nil) }
        let wait = Double(env("HB_DEBUG_WAIT") ?? "4") ?? 4
        DispatchQueue.main.asyncAfter(deadline: .now() + wait) { [weak self] in self?.debugCapture(tab) }
    }

    // ⌘R: the skin's files and the CURRENT tab's page, both from the server, never from the cache
    @objc func reloadPage() {
        let was = skinned
        skin = loadSkin()
        if skinned != was {
            // the window's own style depends on whether there is a skin: say so instead of half-switching
            let a = NSAlert()
            a.messageText = skinned ? "The new design is available again" : "The new design could not be loaded"
            a.informativeText = "Quit and reopen \(appName) to switch."
            a.runModal()
            skin = was ? skin : nil
        }
        for (t, v) in webViews { installScripts(v.configuration.userContentController, tab: t) }
        webViews[currentTab]?.reloadFromOrigin()
    }

    @objc private func selectTabFromMenu(_ sender: NSMenuItem) {
        if let tab = Tab(rawValue: sender.tag) { showTab(tab) }
    }

    @objc private func openClassic() {
        // installed as "Homebase", the old viewer is kept as "Homebase Classic"; beside "Homebase Next" it is "Homebase"
        let apps = NSHomeDirectory() + "/Applications/"
        for name in ["Homebase Classic.app", "Homebase.app"] where apps + name != Bundle.main.bundlePath && FileManager.default.fileExists(atPath: apps + name) {
            NSWorkspace.shared.open(URL(fileURLWithPath: apps + name))
            return
        }
    }

    // ---------------------------------------------------------------- design samples: their own window, never a tab
    @objc private func openSample(_ sender: NSMenuItem) {
        guard let s = skin?.samples, sender.tag < s.count,
              let url = URL(string: s[sender.tag].path, relativeTo: origin(of: Tab.desk.baseURL)) else { return }
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                           styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        win.title = "Sample (not live): " + s[sender.tag].title
        win.isReleasedWhenClosed = false
        let wv = WKWebView(frame: win.contentView!.bounds, configuration: WKWebViewConfiguration())
        wv.autoresizingMask = [.width, .height]
        win.contentView!.addSubview(wv)
        wv.load(URLRequest(url: url.absoluteURL))
        win.center()
        win.makeKeyAndOrderFront(nil)
        sampleWindows.append(win)
    }

    private func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu()
        let reload = NSMenuItem(title: "Reload", action: #selector(reloadPage), keyEquivalent: "r")
        reload.target = self
        appMenu.addItem(reload)
        let classic = NSMenuItem(title: "Open Classic Homebase", action: #selector(openClassic), keyEquivalent: "")
        classic.target = self
        appMenu.addItem(classic)
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
            let item = NSMenuItem(title: tab.title, action: #selector(selectTabFromMenu(_:)), keyEquivalent: String(tab.rawValue + 1))
            item.target = self
            item.tag = tab.rawValue
            viewMenu.addItem(item)
        }
        if let samples = skin?.samples, !samples.isEmpty {
            viewMenu.addItem(NSMenuItem.separator())
            let sItem = NSMenuItem(title: "Design Samples", action: nil, keyEquivalent: "")
            let sMenu = NSMenu(title: "Design Samples")
            for (i, s) in samples.enumerated() {
                let it = NSMenuItem(title: s.title, action: #selector(openSample(_:)), keyEquivalent: "")
                it.target = self
                it.tag = i
                sMenu.addItem(it)
            }
            sItem.submenu = sMenu
            viewMenu.addItem(sItem)
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
            // ...and the same through AppKit's own routing (NSApp.sendEvent -> NSWindow -> hit test), 40% across
            if env("HB_DEBUG_ROUTED") != nil {
                self.debugLog.append("key=\(self.window.isKeyWindow) active=\(NSApp.isActive) visible=\(self.window.isVisible)")
                // a control point in the content first (must arrive), then the toolbar strip
                for q in [NSPoint(x: self.window.frame.width * 0.6, y: self.window.frame.height - 300), NSPoint(x: self.window.frame.width * 0.4, y: p.y)] {
                    for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
                        if let ev = NSEvent.mouseEvent(with: type, location: q, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                                       windowNumber: self.window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1) {
                            NSApp.sendEvent(ev)
                        }
                    }
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
        let afterJS: () -> Void = { [weak self] in
            if env("HB_DEBUG_REAL") != nil { self?.realEventTest(wv) { finish() } } else { finish() }
        }
        if let path = env("HB_DEBUG_JS"), let js = try? String(contentsOfFile: path, encoding: .utf8) {
            wv.evaluateJavaScript(js) { _, _ in
                DispatchQueue.main.asyncAfter(deadline: .now() + (Double(env("HB_DEBUG_JSWAIT") ?? "1.5") ?? 1.5)) { afterJS() }
            }
        } else {
            afterJS()
        }
    }

    // ---------------------------------------------------------------- debug: REAL mouse events (HB_DEBUG_REAL)
    // Posts genuine HID mouse events (the same path a hand on the trackpad takes, WindowServer included) at this
    // window only: every event is preceded by a check that the topmost window under the point is THIS window, and
    // the run stops if it is not. The pointer is put back where it was. Used once, on a throwaway page, to prove
    // that a click in the toolbar strip reaches the page and that a drag there moves the window.
    private func realEventTest(_ wv: WKWebView, done: @escaping () -> Void) {
        NSApp.activate(ignoringOtherApps: true)
        window.orderFrontRegardless()
        window.makeKey()
        let screenH = NSScreen.screens.first?.frame.height ?? 0
        let home = CGEvent(source: nil)?.location ?? .zero
        let src = CGEventSource(stateID: .hidSystemState)
        func mine(_ p: NSPoint) -> Bool { NSWindow.windowNumber(at: p, belowWindowWithWindowNumber: 0) == window.windowNumber }
        func post(_ type: CGEventType, _ p: NSPoint) -> Bool {
            guard mine(p) else { debugLog.append("ABORT: another window is on top at \(Int(p.x)),\(Int(p.y))"); return false }
            CGEvent(mouseEventSource: src, mouseType: type, mouseCursorPosition: CGPoint(x: p.x, y: screenH - p.y), mouseButton: .left)?.post(tap: .cghidEventTap)
            return true
        }
        func after(_ t: Double, _ f: @escaping () -> Void) { DispatchQueue.main.asyncAfter(deadline: .now() + t, execute: f) }
        let finishUp: () -> Void = {
            CGWarpMouseCursorPosition(home)
            after(0.4) { done() }
        }
        after(0.8) { [self] in
            debugLog.append("real: key=\(window.isKeyWindow) active=\(NSApp.isActive) frame=\(window.frame)")
            wv.evaluateJavaScript("(function(){var b=document.querySelector('[data-hb-realtest]');if(!b)return null;var r=b.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2];})()") { [self] v, _ in
                let f = window.frame
                // 1. a click on a page button that sits in the toolbar strip
                var steps: [(Double, () -> Bool)] = []
                if let a = v as? [Double], a.count == 2 {
                    let b = NSPoint(x: f.minX + a[0], y: f.maxY - a[1])
                    steps.append((0.05, { post(.mouseMoved, b) }))
                    steps.append((0.25, { post(.leftMouseDown, b) }))
                    steps.append((0.08, { post(.leftMouseUp, b) }))
                } else { debugLog.append("real: no [data-hb-realtest] button") }
                // 2. a press-drag-release on the empty part of the strip: the window should move by the same amount
                let s0 = NSPoint(x: f.minX + f.width * 0.62, y: f.maxY - chrome.toolbarHeight / 2)
                steps.append((0.5, { post(.mouseMoved, s0) }))
                steps.append((0.25, { post(.leftMouseDown, s0) }))
                for i in 1...12 {
                    let q = NSPoint(x: s0.x + CGFloat(i) * 5, y: s0.y - CGFloat(i) * 3)
                    steps.append((0.03, {
                        // while a window drag is in flight the window follows the pointer, so the point stays inside it
                        CGEvent(mouseEventSource: src, mouseType: .leftMouseDragged, mouseCursorPosition: CGPoint(x: q.x, y: screenH - q.y), mouseButton: .left)?.post(tap: .cghidEventTap)
                        return true
                    }))
                }
                let s1 = NSPoint(x: s0.x + 60, y: s0.y - 36)
                steps.append((0.15, {
                    CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: CGPoint(x: s1.x, y: screenH - s1.y), mouseButton: .left)?.post(tap: .cghidEventTap)
                    return true
                }))
                func run(_ i: Int) {
                    if i >= steps.count {
                        after(0.6) { [self] in
                            let g = window.frame
                            debugLog.append("real: window moved by \(Int(g.minX - f.minX)),\(Int(g.minY - f.minY)) (asked 60,-36)")
                            finishUp()
                        }
                        return
                    }
                    after(steps[i].0) { if steps[i].1() { run(i + 1) } else { finishUp() } }
                }
                run(0)
            }
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
