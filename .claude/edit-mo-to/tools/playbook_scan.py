"""Scan a Playbook shared folder: list videos and build a labelled contact sheet from each clip's frame sheet.
usage: python playbook_scan.py <sharedLinkSlug> <folderToken> <outdir> [maxclips]
Folder tokens: the last path segment of a folder link in the shared page. Needs Pillow. Writes sheet_NN.jpg (5 frames per clip), index.tsv, assets.json.
"""
import json, sys, os, urllib.request, urllib.parse, io
from PIL import Image, ImageDraw, ImageFont

slug, tok, out = sys.argv[1], sys.argv[2], sys.argv[3]
maxclips = int(sys.argv[4]) if len(sys.argv) > 4 else 200
os.makedirs(out, exist_ok=True)
H = {"organization": "exchange-life", "sharedlinkslug": slug, "clienttype": "web-app",
     "content-type": "application/json", "User-Agent": "Mozilla/5.0"}
OP = "graphql-frontend-prod/d08562bf9160f2a10df024d39382c6fb"

def q(after=None):
    v = {"collectionToken": tok, "filters": {}, "includeSubboards": True, "sortBySubboards": True, "first": 100,
         "sort": {"field": "CREATED_AT", "direction": "DESC"}, "discarded": False, "includeGroups": False,
         "incompleteOnly": False}
    if after: v["after"] = after
    u = "https://www.playbook.com/graphql?" + urllib.parse.urlencode(
        {"operationName": "CollectionAssetsQuery", "variables": json.dumps(v), "extensions": json.dumps({"operationId": OP})})
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H)))

vids, after = [], None
while True:
    c = q(after)["data"]["collection"]["assetsCursor"]
    for e in c["edges"]:
        n = e["node"]
        if n.get("duration") and n.get("frameSheet"):
            vids.append(n)
    if not c["pageInfo"]["hasNextPage"] or len(vids) >= maxclips: break
    after = c["pageInfo"]["endCursor"]
vids = vids[:maxclips]

font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 22)
PICK = [3, 25, 50, 75, 96]
TW = 120
rows = []
idx = []
for i, n in enumerate(vids, 1):
    fs = n["frameSheet"]
    try:
        sheet = Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(fs["url"], headers={"User-Agent": "Mozilla/5.0"})).read())).convert("RGB")
    except Exception as ex:
        print("ERR", i, n["title"], ex); continue
    fw, fh, cols = fs["frameWidth"], fs["frameHeight"], fs["colCount"]
    total = len(fs["frameOffsets"])
    # frame sheet frames may be landscape-coded; actual shown aspect from the sheet itself
    th = int(TW * fh / fw)
    row = Image.new("RGB", (60 + TW * len(PICK), th), "black")
    for j, p in enumerate(PICK):
        k = min(p, total - 1)
        x, y = (k % cols) * fw, (k // cols) * fh
        row.paste(sheet.crop((x, y, x + fw, y + fh)).resize((TW, th)), (60 + j * TW, 0))
    d = ImageDraw.Draw(row); d.text((6, 6), str(i), fill="yellow", font=font)
    rows.append(row)
    idx.append(f"{i}\t{n['title']}\t{n['duration']:.1f}s\t{n['primaryWidth']}x{n['primaryHeight']}")

# write sheets of 8 rows each
per = 8
for s in range(0, len(rows), per):
    chunk = rows[s:s + per]
    W = max(r.width for r in chunk); Ht = sum(r.height for r in chunk) + 4 * len(chunk)
    im = Image.new("RGB", (W, Ht), "white"); y = 0
    for r in chunk: im.paste(r, (0, y)); y += r.height + 4
    im.save(os.path.join(out, f"sheet_{s // per + 1:02d}.jpg"), quality=80)
open(os.path.join(out, "index.tsv"), "w", encoding="utf-8").write("\n".join(idx))
json.dump([{"title": n["title"], "token": n["token"], "url": n["url"], "duration": n["duration"]} for n in vids],
          open(os.path.join(out, "assets.json"), "w"))
print(len(vids), "videos"); print("\n".join(idx))
