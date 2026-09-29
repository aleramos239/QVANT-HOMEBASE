// Homebase.app — a native window onto the dashboard. This is a VIEWER:
// the trading process is the launchd service; closing this window changes
// nothing about execution.
//
// 2026-09-28 three-tabs plan: Desk / Charts / Backtest, each its own WKWebView
// (own WKProcessPool, so a heavy Backtest run can't stall the live chart's
// renderer where WebKit allows separate WebContent processes), built lazily
// the first time its tab is opened and kept alive after that. See
// docs/superpowers/specs/2026-09-28-three-tabs-design.md.
import Cocoa
import WebKit

/// The three tabs, in switcher/menu order. Base URLs are overridable via
/// environment variables so a test build can point at dev servers instead of
/// the real services.
enum Tab: Int, CaseIterable {
    case desk = 0
    case charts = 1
    case backtest = 2

    var title: String {
        switch self {
        case .desk: return "Desk"
        case .charts: return "Charts"
        case .backtest: return "Backtest"
        }
    }

    private var envVar: String {
        switch self {
        case .desk: return "HOMEBASE_DESK_URL"
        case .charts: return "HOMEBASE_CHARTS_URL"
        case .backtest: return "HOMEBASE_BACKTEST_URL"
        }
    }

    private var defaultURLString: String {
        switch self {
        case .desk: return "http://localhost:8850"
        case .charts: return "http://localhost:8852/"
        case .backtest: return "http://localhost:8852/backtest"
        }
    }

    var url: URL {
        let raw = ProcessInfo.processInfo.environment[envVar] ?? defaultURLString
        return URL(string: raw) ?? URL(string: defaultURLString)!
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, NSToolbarDelegate {
    var window: NSWindow!
    var webViews: [Tab: WKWebView] = [:]
    var currentTab: Tab = .desk
    var tabSegmented: NSSegmentedControl?

    private let lastTabKey = "HomebaseLastTab"
    private let toolbarID = NSToolbar.Identifier("HomebaseToolbar")
    private let tabSwitcherID = NSToolbarItem.Identifier("HomebaseTabSwitcher")

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()   // without this, ⌘V/⌘C/⌘A do nothing on macOS
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1120, height: 840),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        win.title = "Homebase"
        win.center()
        win.setFrameAutosaveName("HomebaseMain")
        window = win
        setupToolbar()

        let saved = UserDefaults.standard.object(forKey: lastTabKey) as? Int
        let startTab = saved.flatMap { Tab(rawValue: $0) } ?? .desk

        // The dashboard sends no cache headers, and WebKit's heuristic cache otherwise keeps
        // serving a page (and its scripts) from before an upgrade (2026-09-26: the old chart
        // page kept showing after the charts redesign went live). Cleared ONCE at launch, for
        // the shared default data store every tab's WKWebView uses -- before any tab loads.
        // Cookies and localStorage (theme, chart layouts, favourites) are kept.
        let caches: Set<String> = [WKWebsiteDataTypeDiskCache, WKWebsiteDataTypeMemoryCache]
        WKWebsiteDataStore.default().removeData(ofTypes: caches,
                                                modifiedSince: Date(timeIntervalSince1970: 0)) { [weak self] in
            guard let self = self else { return }
            self.showTab(startTab)
            self.window.makeKeyAndOrderFront(nil)
        }

        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    // ---- tabs: lazy webviews, shown/hidden on the same content view ----

    /// The tab's WKWebView, creating (and starting its first load) on first use.
    ///
    /// Design note: `WKWebViewConfiguration.processPool` (a per-tab `WKProcessPool`, to force
    /// separate WebContent processes) is deprecated since macOS 12 and is a documented no-op --
    /// "Creating and using multiple instances of WKProcessPool no longer has any effect." Modern
    /// WebKit assigns WebContent processes per ORIGIN automatically instead, which Desk (:8850)
    /// already gets for free (a different origin from the other two); Charts and Backtest share
    /// one origin (:8852, differing only by path) and so will share a process regardless of
    /// anything this app does. That is a smaller gap than it sounds: the actual heavy work (a
    /// Strategy Tester run) already runs off the charts service's own event loop, in its own OS
    /// process (homebase/charts/tester_api.py's runner, capped at 2 concurrent per machine, per
    /// GOTCHAS.md) -- the browser tab is a thin client reading results over /ws either way.
    private func webView(for tab: Tab) -> WKWebView {
        if let existing = webViews[tab] { return existing }
        let config = WKWebViewConfiguration()
        let wv = WKWebView(frame: window.contentView!.bounds, configuration: config)
        wv.autoresizingMask = [.width, .height]
        wv.navigationDelegate = self
        wv.isHidden = true
        window.contentView!.addSubview(wv)
        webViews[tab] = wv
        wv.load(URLRequest(url: tab.url))
        return wv
    }

    private func tab(for webView: WKWebView) -> Tab? {
        webViews.first(where: { $0.value === webView })?.key
    }

    func showTab(_ tab: Tab) {
        let target = webView(for: tab)   // creates + starts loading on first visit
        for (t, v) in webViews { v.isHidden = (t != tab) }
        currentTab = tab
        UserDefaults.standard.set(tab.rawValue, forKey: lastTabKey)
        tabSegmented?.selectedSegment = tab.rawValue
        window.makeFirstResponder(target)
    }

    // ---- link interception: the desk/charts pages' own in-app links switch tabs here instead
    // of navigating (a plain browser never sees this delegate, so they stay plain links there) ----
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard navigationAction.targetFrame?.isMainFrame == true,
              let url = navigationAction.request.url,
              let sourceTab = tab(for: webView) else {
            decisionHandler(.allow); return
        }
        if let target = tabFor(url: url), target != sourceTab {
            decisionHandler(.cancel)
            showTab(target)
            return
        }
        decisionHandler(.allow)
    }

    /// Which tab a URL belongs to, by origin (scheme+host+port) and, for Charts/Backtest which
    /// normally share one origin (:8852), by path -- /backtest vs everything else.
    private func tabFor(url: URL) -> Tab? {
        func sameOrigin(_ a: URL, _ b: URL) -> Bool {
            a.scheme == b.scheme && a.host == b.host && a.port == b.port
        }
        let desk = Tab.desk.url, charts = Tab.charts.url, backtest = Tab.backtest.url
        if sameOrigin(url, desk) { return .desk }
        if sameOrigin(url, charts) || sameOrigin(url, backtest) {
            let backtestPath = backtest.path.isEmpty ? "/backtest" : backtest.path
            return url.path.hasPrefix(backtestPath) ? .backtest : .charts
        }
        return nil
    }

    // service mid-restart? retry until that tab's page answers -- per tab, not global, so one
    // tab's outage never touches another's session
    func webView(_ w: WKWebView, didFail n: WKNavigation!, withError e: Error) { retry(w) }
    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) { retry(w) }
    private func retry(_ w: WKWebView) {
        guard let tab = tab(for: w) else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak w] in
            w?.load(URLRequest(url: tab.url))
        }
    }

    // ⌘R reloads the CURRENT tab from the server, never from the cache
    @objc func reloadPage() {
        webViews[currentTab]?.reloadFromOrigin()
    }

    // ---- toolbar: a Desk/Charts/Backtest segmented switcher in the title bar ----
    private func setupToolbar() {
        let toolbar = NSToolbar(identifier: toolbarID)
        toolbar.delegate = self
        toolbar.displayMode = .iconAndLabel
        window.toolbar = toolbar
        window.toolbarStyle = .unified
    }

    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier itemIdentifier: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        guard itemIdentifier == tabSwitcherID else { return nil }
        let seg = NSSegmentedControl(labels: Tab.allCases.map { $0.title }, trackingMode: .selectOne,
                                     target: self, action: #selector(segmentChanged(_:)))
        seg.segmentStyle = .texturedRounded
        seg.selectedSegment = currentTab.rawValue
        tabSegmented = seg
        let item = NSToolbarItem(itemIdentifier: tabSwitcherID)
        item.view = seg
        item.label = "Tabs"
        item.paletteLabel = "Desk / Charts / Backtest"
        return item
    }

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { [tabSwitcherID] }
    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] { [tabSwitcherID] }

    @objc private func segmentChanged(_ sender: NSSegmentedControl) {
        if let tab = Tab(rawValue: sender.selectedSegment) { showTab(tab) }
    }

    @objc private func selectTabFromMenu(_ sender: NSMenuItem) {
        if let tab = Tab(rawValue: sender.tag) { showTab(tab) }
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

        // Desk/Charts/Backtest, ⌘1/⌘2/⌘3 -- the same switch the toolbar segmented control drives
        let viewItem = NSMenuItem()
        main.addItem(viewItem)
        let viewMenu = NSMenu(title: "View")
        for tab in Tab.allCases {
            let item = NSMenuItem(title: tab.title, action: #selector(selectTabFromMenu(_:)),
                                  keyEquivalent: String(tab.rawValue + 1))
            item.target = self
            item.tag = tab.rawValue
            viewMenu.addItem(item)
        }
        viewItem.submenu = viewMenu

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
