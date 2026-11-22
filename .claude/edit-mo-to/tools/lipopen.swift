// lipopen <video>: one line per frame "time openness" (inner-lip gap / face height; -1 = no face). Apple Vision.
import AVFoundation
import Vision
import Foundation

let url = URL(fileURLWithPath: CommandLine.arguments[1])
let asset = AVURLAsset(url: url)
let sem = DispatchSemaphore(value: 0)
var track: AVAssetTrack?
Task { track = try? await asset.loadTracks(withMediaType: .video).first; sem.signal() }
sem.wait()
guard let vt = track, let reader = try? AVAssetReader(asset: asset) else { exit(1) }
let out = AVAssetReaderTrackOutput(track: vt, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
reader.add(out)
reader.startReading()
var lines: [String] = []
while let sb = out.copyNextSampleBuffer() {
    let t = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sb))
    guard let pb = CMSampleBufferGetImageBuffer(sb) else { continue }
    let req = VNDetectFaceLandmarksRequest()
    let h = VNImageRequestHandler(cvPixelBuffer: pb, options: [:])
    try? h.perform([req])
    var v = -1.0
    var g = -1.0
    if let faces = req.results, let f = faces.max(by: { $0.boundingBox.height < $1.boundingBox.height }),
       let inner = f.landmarks?.innerLips, inner.pointCount >= 6 {
        let p = inner.normalizedPoints.map { Double($0.y) }
        // inner lip contour: gap = spread of y over the middle points (upper vs lower)
        let ys = p.sorted()
        let n = ys.count
        let top = ys[(n * 3) / 4 ..< n].reduce(0, +) / Double(n - (n * 3) / 4)
        let bot = ys[0 ..< max(1, n / 4)].reduce(0, +) / Double(max(1, n / 4))
        v = (top - bot)
        g = (top - bot) * Double(f.boundingBox.height) / Double(f.boundingBox.height)
        let ip = inner.normalizedPoints
        // upper-middle vs lower-middle inner lip points by x near the centre
        let cx = ip.map { Double($0.x) }.reduce(0, +) / Double(ip.count)
        let mid = ip.filter { abs(Double($0.x) - cx) < 0.04 }.map { Double($0.y) }
        if mid.count >= 2 { g = mid.max()! - mid.min()! }
        if let outer = f.landmarks?.outerLips {
            let oy = outer.normalizedPoints.map { Double($0.y) }
            let ox = outer.normalizedPoints.map { Double($0.x) }
            let w = (ox.max()! - ox.min()!)
            if w > 0 { v = (oy.max()! - oy.min()!) / w }   // mouth height / width of the outer lips
        }
    }
    lines.append(String(format: "%.4f %.5f %.5f", t, v, g))
}
print(lines.joined(separator: "\n"))
