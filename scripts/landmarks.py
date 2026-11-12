# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Named places in Kanaleneiland, Utrecht; positions from BAG/OSM and resident stories."""

import json

import numpy as np

from config import BUILD, RAW
from geo import wgs_to_rd

# Local stories supplied by the resident; address positions resolved from BAG.
BUILDINGS = []
POINTS = [{"name": "Churchilllaan 321", "addr": "Churchilllaan 321", "kind": "Bewonersbijdrage", "address": "Churchilllaan 321, Utrecht", "text": "Niek en Nicole — de bazinnen van Utrecht wonen hier.", "stop": "Churchilllaan 321"}, {"name": "Churchilllaan", "at": (134853.867, 453889.313), "kind": "Kanaleneiland", "text": "De Churchilllaan vormt het beginpunt van deze kaart. Volg de laan door Kanaleneiland en ontdek de woonblokken, het groen en de routes naar de kanalen.", "more": "https://www.openstreetmap.org/search?query=Churchilllaan%20Utrecht"}]
POINTS += [{'name': 'Prins Clausbrug', 'latlon': (52.07096, 5.08804), 'kind': 'Brug · 2003', 'text': 'De Prins Clausbrug verbindt Kanaleneiland met Papendorp over het Amsterdam-Rijnkanaal. De tuibrug is ontworpen door Ben van Berkel en werd op 25 juni 2003 officieel geopend door prinses Máxima.', 'more': 'https://www.koninklijkhuis.nl/actueel/nieuws/2003/06/25/prinses-maxima-opent-prins-clausbrug-utrecht'}, {'name': 'Park Transwijk', 'latlon': (52.0725, 5.105), 'kind': 'Park', 'text': 'Het grote park naast Kanaleneiland is ingericht voor verschillende vormen van ontspanning. Het groen hoort bij de opzet van de naoorlogse wijk: wonen en recreëren kregen elk hun eigen ruimte.', 'more': 'https://www.utrecht.nl/wonen-en-leven/parken-en-groen/parken-en-plantsoenen/park-transwijk'}, {'name': 'Stadsboerderij Eilandsteede', 'latlon': (52.06949048, 5.10356188), 'kind': 'Stadsboerderij', 'text': 'In Park Transwijk ligt stadsboerderij Eilandsteede. Een herkenbare bestemming voor een wandeling vanuit de woonstraten van Kanaleneiland naar het park.', 'more': 'https://www.utrecht.nl/wonen-en-leven/parken-en-groen/parken-en-plantsoenen/park-transwijk'}]
CATEGORIES = [("buurtverhalen", "Buurtverhalen", ["Churchilllaan 321"]), ("wijk", "Ontdek Kanaleneiland", ["Churchilllaan", "Prins Clausbrug", "Park Transwijk", "Stadsboerderij Eilandsteede"])]

# What the viewer shows when a place is clicked; the rest of an entry is for the render.
INFO = ("note", "kind", "text", "address", "web", "more", "photo", "stop")

# A steel lattice telecom mast next to the A67 (three antenna entries in OSM, one structure in AHN).
MASTS = []


def point_in_ring(x, y, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, np.roll(ring, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


ADDRESSES = None


def address_xy(name):
    """RD position of a BAG address such as "Geldersestraat 3" (data/raw/addresses.json, from scripts/fetch.py)."""
    global ADDRESSES
    if ADDRESSES is None:
        ADDRESSES = {label.replace(", Utrecht", "").split(", ")[0]: (x, y) for x, y, label in json.loads((RAW / "addresses.json").read_text())}
    return ADDRESSES[name]


def building_at(rings, x, y):
    for rid, ring, a in rings:
        if point_in_ring(x, y, ring):
            return rid, a
    return None, None


def main():
    feats = [json.loads(line) for line in open(RAW / "3dbag.jsonl")]
    rings = []
    for f in feats:
        t = f["transform"]
        V = np.array(f["vertices"], dtype=np.float64) * t["scale"] + t["translate"]
        co = f["CityObjects"][f["id"]]
        rings.append((f["id"], V[co["geometry"][0]["boundaries"][0][0]][:, :2], co["attributes"]))

    out = {"buildings": {}, "places": [], "masts": [], "hotspots": [], "categories": []}
    for b in BUILDINGS:
        if "addrs" in b:
            pts = [address_xy(a) for a in b["addrs"]]
            pids = [building_at(rings, *pt)[0] for pt in pts]
            assert all(pids), f"{b['name']}: no building at {b['addrs']}"
            x, y = np.mean(pts, axis=0)
            out["places"].append({"name": b["name"], "note": b.get("note"), "x": x, "y": y, "h": 4.0})
            out["hotspots"].append({"name": b["name"], "pids": pids, "x": x, "y": y, **{k: b[k] for k in INFO if k in b}})
            print(f"{b['name']}: {', '.join(pids)}")
            continue
        x, y = b["at"] if "at" in b else wgs_to_rd(*b["latlon"])
        pid, attrs = None, None
        for rid, ring, a in rings:
            if point_in_ring(x, y, ring):
                pid, attrs = rid, a
                break
        if pid is None:
            d = [(np.hypot(*(ring.mean(0) - (x, y))), rid, a) for rid, ring, a in rings]
            dist, pid, attrs = min(d, key=lambda t: t[0])
            if dist > 20:
                pid = None
        height = ((attrs or {}).get("b3_h_dak_max") or 0) - ((attrs or {}).get("b3_h_maaiveld") or 0)
        if "tower" in b:
            height = b["tower"]["top"]
        elif "turret" in b:
            height = b["turret"]["top"]
        out["places"].append({"name": b["name"], "note": b.get("note"), "x": x, "y": y, "h": round(height, 1)})
        if pid and "style" in b:
            out["buildings"][pid] = {k: v for k, v in b.items() if k not in ("at", "latlon", *INFO)}
        if pid:
            out["hotspots"].append({"name": b["name"], "pid": pid, "x": x, "y": y, **{k: b[k] for k in INFO if k in b}})
        print(f"{b['name']}: {pid or 'no building'}")
    for p in POINTS:
        x, y = p["at"] if "at" in p else address_xy(p["addr"]) if "addr" in p else wgs_to_rd(*p["latlon"])
        out["places"].append({"name": p["name"], "note": p.get("note"), "x": x, "y": y, "h": 2.0})
        out["hotspots"].append({"name": p["name"], "x": x, "y": y, **{k: p[k] for k in INFO if k in p}})
    for m in MASTS:
        x, y = wgs_to_rd(*m["latlon"])
        out["masts"].append({**{k: v for k, v in m.items() if k != "latlon"}, "x": x, "y": y})
    names = {h["name"] for h in out["hotspots"]}
    for key, label, members in CATEGORIES:
        missing = [n for n in members if n not in names]
        assert not missing, f"{label}: no hotspot for {missing}"
        out["categories"].append({"key": key, "label": label, "names": members})
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "landmarks.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
