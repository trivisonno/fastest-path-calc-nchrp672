# fastest-path-calc-nchrp672

A Python CLI re-implementation of Roadway Mastery's
**[Fastest Path Spreadsheet](https://roadwaymastery.org/product/fastest-path-spreadsheet/)**.

Given the controlling fastest-path radii for the entry, circulatory, exit,
left-turn and right-turn vehicle paths of a roundabout (**R1–R5**), it predicts
the operating speed of each movement and runs the **NCHRP Report 672**
speed-consistency performance checks. US customary (ft / mph) and metric
(m / km/h) units are both supported.

> Educational / preliminary-design tool. Final designs must be verified by a
> licensed Professional Engineer.

## Install

```bash
pip install -e .
# or run without installing:
python -m fastestpath --help
```

No third-party dependencies (Python 3.9+). `pytest` only for the test suite.

## Usage

```bash
# All five radii, US customary, with the acceleration-limited exit check
fastest-path --units us --r1 92 --r2 98 --r3 150 --r4 55 --r5 70 --exit-distance 140

# Metric, just a through movement
fastest-path --units si --r1 28 --r2 30 --r3 45

# Read one approach (or a list of approaches) from JSON
fastest-path --input examples/single_lane_us.json
fastest-path --input examples/multi_approach_us.json --json

# Convert a single measured radius to a turning speed (see "Turning speeds" below)
fastest-path --units us --r5 60 --method point-mass
```

### Radii (measured from the layout, not curb radii)

| Flag | Path | Definition (NCHRP 672 §6.2.1.5) |
|------|------|--------------------------------|
| `--r1` | Entry | Min radius on the fastest through path prior to the yield line |
| `--r2` | Circulatory | Min radius on the fastest through path around the central island |
| `--r3` | Exit | Min radius on the fastest through path into the exit |
| `--r4` | Left turn | Min radius on the path of the conflicting left-turn movement |
| `--r5` | Right turn | Min radius on the fastest right-turn path |

The fastest path is the smoothest, flattest path a single vehicle can take
ignoring lane markings. NCHRP 672 draws it for a 2 m (6 ft) wide vehicle whose
path centerline stays **1.5 m (5 ft) from a concrete curb or roadway centerline**
and **1.0 m (3 ft) from a painted edge line**. This tool takes the resulting
radii as input; measure them in CAD or Google Earth.

## Methodology

### Speed from radius

**`--method regression`** (default within its valid range) — NCHRP 1043
Eq. 9.3 / 9.4, the power-curve fit used for roundabout fastest-path checks,
valid for R ≤ 400 ft (120 m):

```
e = +0.02:  V = 3.4415 · R^0.3861      (US: V mph, R ft)
e = -0.02:  V = 3.4614 · R^0.3673
e = +0.02:  V = 8.7602 · R^0.3861      (SI: V km/h, R m)
e = -0.02:  V = 8.6169 · R^0.3673
```

**`--method point-mass`** — NCHRP 672 **Equation 6-1**, the AASHTO Green Book
point-mass relationship:

```
V = sqrt(127 · R · (e + f))   (SI)
V = sqrt( 15 · R · (e + f))   (US customary)
```

with `f` the AASHTO side-friction factor for curves at intersections
(Green Book Fig. III-19 / NCHRP 672 Exhibits 6-8, 6-9), solved iteratively
because `f` depends on `V`.

**`--method auto`** (default) uses the regression up to 400 ft (120 m) and the
point-mass equation above that. The two agree within ~1 mph across the normal
range because both are grounded in the same AASHTO speed-radius relationship.

### Superelevation (`--super-mode`)

NCHRP 672 §6.2.1.4: assume **+0.02 for entry/exit curves** and **−0.02 for
curves around the central island**.

| Mode | Cross slope used for the "governing" speed |
|------|--------------------------------------------|
| `typical` (default) | +0.02 for R1/R3/R5, −0.02 for R2/R4 |
| `normal-crown` | +0.02 everywhere — conservative concept-level default |
| `both` | higher of the two bounds |

Every run still reports both the +2% and −2% speed for each radius.

### Conflicting-stream speeds

* **Entering stream** ≈ average of the entry-path (R1) and circulating-path (R2) speeds
* **Circulating stream** ≈ left-turn-path (R4) speed

### Exit speed (NCHRP 1043 Eq. 9.7)

If `--exit-distance D` (path distance from the middle of the R2 path to the exit
point of interest) is given, the governing exit speed is the lesser of the R3
prediction and the acceleration-limited speed:

```
V3 = min( V3_path ,  (1/c)·sqrt( (c·V2)^2 + 2·a23·d23 ) )
a23 = 6.9 ft/s^2 (2.1 m/s^2)
```

### Performance checks

Based on NCHRP 672 §6.2.1.5 (speed consistency):

1. `R1 ≤ R2` — entry radius not larger than circulating radius
2. `R3 ≥ R2` — exit radius not smaller than circulating radius
3. `|V(R1) − V(R2)| ≤ 12 mph (20 km/h)` — differential between consecutive elements
4. `V(R1) − V(R4)` within the 10–12 mph (16–20 km/h) target band — entering vs. circulating conflict
5. `|entering stream − circulating stream| ≤ 12 mph (20 km/h)`
6. `V(R5) ≤ V(R1)` — right turn not faster than the through entry

The process exit code is `0` when every check passes, `1` when any check needs
review, `2` on input error.

## Turning speeds for a single movement (NCHRP 672 fastest-path method)

To reproduce the "measure the fastest-path radius, apply Equation 6-1 to convert
radius to speed" workflow (e.g. right/left turn approach speeds at a crosswalk or
a vehicle crossing a yield-controlled movement), pass just the relevant radius
with `--method point-mass`:

```bash
# right-turn approach speed from a 60 ft fastest-path radius
fastest-path --units us --r5 60 --method point-mass

# left-turn / circulating movement (adverse crossfall) from a 45 ft radius
fastest-path --units us --r4 45 --method point-mass --super-mode typical
```

Read the `govern` column (or the +2% / −2% bounds) for the movement of interest.

## Map webapp

`webapp/fastest-path-map.html` is a standalone Leaflet page (open it directly in
a browser — no server, no build). It:

* lets you **draw the entering and exiting vehicle paths** (two points each) on
  an OSM or satellite basemap, with **direction-of-travel arrows**, and drag the
  endpoints to adjust;
* **imports / exports a project file** — a GeoJSON `FeatureCollection` of the two
  2-point `LineString`s (identified by `properties.role = "entering" | "exiting"`,
  or by order) **plus a `fastest_path` block** holding the radii (value, color,
  visibility) and the calc/style settings (units, equation, arc & vehicle-path
  toggles, offset). Export writes it, import restores all of it; a plain
  two-LineString file still loads fine (settings left as-is);
* computes the **tangent intersection and deflection angle** of the two paths;
* takes **one or more turn radii** and, for each, predicts the fastest-path
  speed (same equations as the CLI — regression / point-mass / auto, both +2%
  and −2% superelevation) and **draws the fitted circular turn arc** on the map
  so you can check the radius against the real pavement. Each radius keeps a
  fixed color; toggle curves individually (per-chip checkbox) or all at once;
* optionally overlays **vehicle-path lines** — the centerline offset both ways by
  an editable distance (default 3 ft / 0.9 m each side, i.e. half a 6 ft / 2 m
  vehicle per the NCHRP 672 fastest-path construction);
* labels the standard circular-curve points **PC, PI, PT** on the map (with the
  tangent lines drawn to the PI) and reports the curve elements in the sidebar
  for each radius — **Δ** (deflection / central angle), **T** (tangent
  distance), **L** (length of curve), **LC** (long chord), **M** (middle
  ordinate), **E** (external distance), **D** (degree of curve, arc definition,
  US units) — plus the PC / PT coordinates.

The satellite layer uses Esri World Imagery; if you host the file somewhere with
a strict image CSP, only the OSM layer will load.

## JSON input

```json
{ "name": "NB approach", "units": "us",
  "r1": 92, "r2": 98, "r3": 150, "r4": 55, "r5": 70,
  "exit_distance": 140, "method": "auto" }
```

A top-level array evaluates several approaches in one run.

## Library API

```python
from fastestpath import predict_speed, ApproachInput, evaluate_approach

predict_speed(125, superelevation=0.02, units="us", method="regression")  # 22.2 mph

res = evaluate_approach(ApproachInput(r1=92, r2=98, r3=150, r4=55, r5=70, units="us"))
for r in res.radii:
    print(r.key, round(r.governing, 1))
for c in res.checks:
    print(c.passed, c.name)
```

## Tests

```bash
pip install pytest
pytest -q
```

## References

* Rodegerdts et al., **NCHRP Report 672 — *Roundabouts: An Informational Guide*,
  2nd ed.**, TRB, 2010. Ch. 6 (Geometric Design), Eq. 6-1, §6.2.1.
* **NCHRP Report 1043 — *Guide for Roundabouts***, TRB, 2023. Eq. 9.3, 9.4, 9.7.
* FHWA-RD-00-067, *Roundabouts: An Informational Guide*, 2000 (Eq. 6-1, Exhibits 6-8–6-12).
* AASHTO, *A Policy on Geometric Design of Highways and Streets* (Green Book) — speed-radius relationship, side-friction factors.
