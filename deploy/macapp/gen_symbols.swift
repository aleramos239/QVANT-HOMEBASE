// gen_symbols.swift -- writes homebase/static/apple/symbols.css: the SF Symbols the Apple skin uses, drawn BY THIS
// macOS (NSImage(systemSymbolName:)) at the point size and weight the system uses in that place, as 3x alpha masks.
// The page colours them with currentColor (background + mask), so they follow the label colours like native symbols.
//
//   swiftc -O deploy/macapp/gen_symbols.swift -o /tmp/gen_symbols && /tmp/gen_symbols homebase/static/apple/symbols.css
//
// A row is "css-name  symbol.name  pointSize  weight". Sizes: 13 pt medium = sidebar rows (measured: NSOutlineView
// source list, medium row size); 17 pt regular = toolbar items (measured: 13 pt symbols drawn 1.31x in a unified
// toolbar); 13 / 11 / 10 pt regular = inline in lists, pop-ups and small controls.
import Cocoa

let rows = """
sidebar-left          sidebar.left                       17 regular
sidebar-right         sidebar.right                      17 regular
gear                  gearshape                          17 regular
search                magnifyingglass                    17 regular
plus-tb               plus                               17 regular
ellipsis-tb           ellipsis                           17 regular
refresh-tb            arrow.clockwise                    17 regular
share-tb              square.and.arrow.up                17 regular
play-tb               play.fill                          17 regular
stop-tb               stop.fill                          17 regular
checkmark-tb          checkmark                          17 regular
save-tb               square.and.arrow.down              17 regular
trash-tb              trash                              17 regular
doc-plus-tb           doc.badge.plus                     17 regular
camera-tb             camera                             17 regular
bell-tb               bell                               17 regular
undo-tb               arrow.uturn.backward               17 regular
redo-tb               arrow.uturn.forward                17 regular
function-tb           function                           17 regular
grid-tb               square.grid.2x2                    17 regular
chart-tb              chart.xyaxis.line                  17 regular
candles-tb            chart.bar.xaxis                    17 regular
ruler-tb              ruler                              17 regular
cursor-tb             cursorarrow                        17 regular
pencil-tb             pencil.tip                         17 regular
eye-tb                eye                                17 regular
lock-tb               lock                               17 regular
paperplane-tb         paperplane                         17 regular
code-tb               curlybraces                        17 regular
list-tb               list.bullet                        17 regular
info-tb               info.circle                        17 regular
moon-tb               moon                               17 regular
bolt-tb               bolt.fill                          17 regular
calendar              calendar                           13 medium
today                 calendar.day.timeline.left         13 medium
clock                 clock                              13 medium
bolt                  bolt.fill                          13 medium
bolt-off              bolt.slash                         13 medium
bolt-line             bolt                               13 medium
eye                   eye                                13 medium
warn                  exclamationmark.triangle.fill      13 medium
card                  creditcard                         13 medium
bank                  building.columns                   13 medium
paper                 doc.text                           13 medium
offline               wifi.slash                         13 medium
journal               list.bullet.rectangle              13 medium
history               clock.arrow.circlepath             13 medium
chart                 chart.xyaxis.line                  13 medium
chart-up              chart.line.uptrend.xyaxis          13 medium
code                  curlybraces                        13 medium
doc                   doc                                13 medium
doc-code              doc.text.below.ecg                 13 medium
folder                folder                             13 medium
star                  star                               13 medium
star-fill             star.fill                          13 medium
tray                  tray.full                          13 medium
person                person.crop.circle                 13 medium
plus                  plus                               13 regular
minus                 minus                              13 regular
ellipsis              ellipsis                           13 regular
ellipsis-circle       ellipsis.circle                    13 regular
xmark                 xmark                              11 medium
xmark-circle          xmark.circle.fill                  13 regular
check                 checkmark                          11 semibold
check-circle          checkmark.circle.fill              13 regular
info                  info.circle                        13 regular
chevron-right         chevron.right                      11 semibold
chevron-left          chevron.left                       11 semibold
chevron-down          chevron.down                       10 semibold
chevron-updown        chevron.up.chevron.down            10 semibold
chevron-back          chevron.backward                   17 regular
arrow-up-right        arrow.up.right                     11 medium
dot                   circle.fill                         7 regular
power                 power                              13 medium
shield                checkmark.shield                   13 medium
shield-warn           exclamationmark.shield             13 medium
antenna               antenna.radiowaves.left.and.right  13 medium
link                  link                               13 medium
play                  play.fill                          11 regular
copy                  doc.on.doc                         13 regular
trash                 trash                              13 regular
pencil                pencil                             13 regular
lock                  lock                               13 medium
"""

func weight(_ s: String) -> NSFont.Weight {
    switch s { case "medium": return .medium; case "semibold": return .semibold; case "bold": return .bold; case "light": return .light; default: return .regular }
}

var out = "/* Generated by deploy/macapp/gen_symbols.swift on \(ProcessInfo.processInfo.operatingSystemVersionString). Do not edit.\n   SF Symbols drawn by the system, as 3x alpha masks. --sf-<name>: the mask; --sf-<name>-w / -h: its size in pt. */\n"
var vars = "", classes = "", missing: [String] = []
let scale: CGFloat = 3
for line in rows.split(separator: "\n") {
    let p = line.split(separator: " ", omittingEmptySubsequences: true).map(String.init)
    guard p.count == 4, let pt = Double(p[2]) else { continue }
    let cfg = NSImage.SymbolConfiguration(pointSize: CGFloat(pt), weight: weight(p[3]), scale: .medium)
    guard let img = NSImage(systemSymbolName: p[1], accessibilityDescription: nil)?.withSymbolConfiguration(cfg) else { missing.append(p[1]); continue }
    let size = img.size
    let w = Int((size.width * scale).rounded(.up)), h = Int((size.height * scale).rounded(.up))
    guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                     isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { continue }
    rep.size = size
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    NSColor.black.set()
    img.draw(in: NSRect(origin: .zero, size: size), from: .zero, operation: .sourceOver, fraction: 1)
    NSGraphicsContext.restoreGraphicsState()
    guard let png = rep.representation(using: .png, properties: [:]) else { continue }
    let f = { (v: CGFloat) -> String in String(format: "%g", Double((v * 100).rounded() / 100)) }
    vars += "  --sf-\(p[0]): url(\"data:image/png;base64,\(png.base64EncodedString())\");\n  --sf-\(p[0])-w: \(f(size.width))px; --sf-\(p[0])-h: \(f(size.height))px;\n"
    classes += ".sf-\(p[0]){--sf:var(--sf-\(p[0]));--sf-w:var(--sf-\(p[0])-w);--sf-h:var(--sf-\(p[0])-h)}\n"
}
out += "html.hb-apple{\n" + vars + "}\n"
out += ".sf{display:inline-block;flex:none;width:var(--sf-w);height:var(--sf-h);background:currentColor;vertical-align:middle;\n  -webkit-mask:var(--sf) center/100% 100% no-repeat;mask:var(--sf) center/100% 100% no-repeat}\n" + classes
let path = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "symbols.css"
try! out.write(toFile: path, atomically: true, encoding: .utf8)
print("wrote \(path): \(out.utf8.count) bytes; missing: \(missing)")
