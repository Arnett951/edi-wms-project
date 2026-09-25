"""Generate reports/location-heatmap/template.rtf, the BI Publisher RTF layout.

A starting point, not the source of truth: once generated, the RTF can be opened and
restyled in Word / Template Builder like any other template. BI Publisher reads the
<?...?> tags from plain RTF text, so no Word form fields are needed.

Layout (landscape): logo + title, facility/date/summary, a color legend, one grid per
aisle (rows = rack level, top first; columns = bay 01-10), then the floor areas.
Cell color is BI Publisher conditional formatting:
    <?if:B01_HEAT='RED'?><?attribute@incontext:background-color;'#F4A4A4'?><?end if?>
EMPTY cells keep the default gray cell shading.

BI Publisher's RTF parser is stricter than Word. Lessons baked in here, all found by
compiling test files with the engine:
  * page size and margins are ignored unless the file has an {\\info} group;
  * landscape comes from Word's section syntax (\\sectd\\ltrsect\\lndscpsxn) with the
    landscape dimensions in \\paperw / \\paperh, not from \\landscape;
  * character formatting must sit in {...} groups, or it (and sometimes the whole
    paragraph) is dropped;
  * a raw <xsl:attribute> typed as text is printed, not executed; use
    <?attribute@incontext:name;'value'?>;
  * a plain <?if?> mid-line starts a new paragraph; use <?if@inlines:...?> to stay inline;
  * "keep together" on every row plus keep-with-next headings chains the whole grid
    into one unbreakable block that jumps to the next page; keep only the headers.

    python bip-report/tools/build_heatmap_template.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT.parent / "dashboard" / "public" / "bi-publisher" / "hello-world-tire-logo.png"
OUT = ROOT / "reports" / "location-heatmap" / "template.rtf"

# \colortbl indexes (1-based)
BLACK, BRAND_RED, SLATE, BORDER, HDR_BG, EMPTY_BG, WHITE, RED_BG, YELLOW_BG, GREEN_BG = range(1, 11)
COLORS = [(0, 0, 0), (215, 25, 32), (100, 116, 139), (203, 213, 225), (38, 38, 38),
          (236, 239, 243), (255, 255, 255), (244, 164, 164), (253, 224, 120), (178, 223, 184)]
HEAT_HEX = {"RED": "#F4A4A4", "YELLOW": "#FDE078", "GREEN": "#B2DFB8"}

PAGE_W, PAGE_H, MARGIN = 15840, 12240, 720   # twips; landscape letter, 0.5" margins
USABLE = PAGE_W - 2 * MARGIN                  # 14400
LEVEL_COL = 700
BAY_COL = (USABLE - LEVEL_COL) // 10          # 1370


def t(text, size=None, bold=False, color=None):
    """A formatted run, always in its own {...} group."""
    words = ""
    if size:
        words += f"\\fs{size}"
    if bold:
        words += "\\b"
    if color:
        words += f"\\cf{color}"
    return "{" + words + " " + text + "}"


def heat_attrs(field):
    """BI Publisher conditional cell shading, one <?if?> per bucket."""
    return "".join(
        f"<?if:{field}='{bucket}'?><?attribute@incontext:background-color;'{hexcolor}'?><?end if?>"
        for bucket, hexcolor in HEAT_HEX.items()
    )


def cell_def(right, shade=None, borders=True):
    parts = []
    if borders:
        for side in ("t", "l", "b", "r"):
            parts.append(f"\\clbrdr{side}\\brdrs\\brdrw10\\brdrcf{BORDER}")
    if shade:
        parts.append(f"\\clcbpat{shade}")
    parts.append("\\clvertalc")
    parts.append(f"\\cellx{right}")
    return "".join(parts)


def row(cells, header=False, keep=True, height=None):
    """cells: list of (width, shade, content_rtf)."""
    out = ["\\trowd\\trgaph30\\trleft0"]
    if header:
        out.append("\\trhdr")
    if keep:
        out.append("\\trkeep")
    if height:
        out.append(f"\\trrh{height}")
    x = 0
    for width, shade, _ in cells:
        x += width
        out.append(cell_def(x, shade))
    for _, _, content in cells:
        out.append(f"\\pard\\intbl\\qc\\plain\\f0\\fs16 {content}\\cell")
    out.append("\\row")
    return "\n".join(out)


def para(content, space_after=60, keepn=False):
    k = "\\keepn" if keepn else ""
    return f"\\pard\\ql{k}\\sa{space_after}\\plain\\f0\\fs18 {content}\\par"


def logo_pict():
    data = LOGO.read_bytes()
    # PNG IHDR: width/height as 4-byte big-endian at offsets 16/20
    w_px, h_px = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    goal_w = 2300
    goal_h = round(goal_w * h_px / w_px)
    return (f"{{\\pict\\pngblip\\picw{w_px}\\pich{h_px}\\picwgoal{goal_w}\\pichgoal{goal_h} "
            f"{data.hex()}}}")


def build():
    parts = [
        "{\\rtf1\\ansi\\ansicpg1252\\deff0",
        "{\\fonttbl{\\f0\\fswiss\\fcharset0 Arial;}}",
        "{\\colortbl;" + "".join(f"\\red{r}\\green{g}\\blue{b};" for r, g, b in COLORS) + "}",
        "{\\stylesheet{\\ql\\f0\\fs18 Normal;}}",
        # Required: without an \info group BI Publisher ignores the page size and margins.
        "{\\info{\\title Location Aging Heatmap}{\\author Hello World Tire lab}}",
        f"\\paperw{PAGE_W}\\paperh{PAGE_H}\\margl{MARGIN}\\margr{MARGIN}\\margt{MARGIN}\\margb{MARGIN}",
        "\\sectd\\ltrsect\\lndscpsxn\\sectdefaultcl",
    ]

    # --- header: logo | title block, red rule under it
    parts.append("\\trowd\\trgaph60\\trleft0"
                 + f"\\clbrdrb\\brdrs\\brdrw30\\brdrcf{BRAND_RED}\\clvertalc\\cellx2700"
                 + f"\\clbrdrb\\brdrs\\brdrw30\\brdrcf{BRAND_RED}\\clvertalc\\cellx{USABLE}")
    parts.append(f"\\pard\\intbl\\ql\\plain\\f0 {logo_pict()}\\cell")
    parts.append("\\pard\\intbl\\ql\\plain\\f0 "
                 + t("Location Aging Heatmap", 30, bold=True) + "\\line "
                 + t("Warehouse locations shaded by the age of their oldest lot", 18, color=SLATE)
                 + "\\cell\\row")

    parts.append(para(
        t("Facility: ", 17) + t("<?WAREHOUSE_CODE?>", 17, bold=True) + t(" - <?WAREHOUSE_NAME?>", 17)
        + t("      Report date: ", 17) + t("<?REPORT_DATE?>", 17, bold=True)
        + t("      Occupied: ", 17) + t("<?OCCUPIED_LOCS?>", 17, bold=True)
        + t(" of <?TOTAL_LOCS?> locations", 17)
        + t("      Oldest lot: ", 17) + t("<?MAX_AGE?> days", 17, bold=True),
        space_after=80))

    # --- legend
    legend_w = 3000
    parts.append(row([
        (legend_w, RED_BG, t("Oldest 10%", 15, bold=True) + t(" (<?RED_LOCS?> locs, <?RED_MIN_AGE?>+ days)", 15)),
        (legend_w, YELLOW_BG, t("Next 10%", 15, bold=True) + t(" (<?YELLOW_LOCS?> locs, <?YELLOW_MIN_AGE?>+ days)", 15)),
        (legend_w, GREEN_BG, t("Remaining occupied", 15, bold=True) + t(" (<?GREEN_LOCS?> locs)", 15)),
        (legend_w, EMPTY_BG, t("Empty", 15, bold=True)),
    ], keep=False, height=300))
    parts.append(para(t(" ", 8), space_after=40))

    # --- rack grid: one table per aisle
    parts.append(para(t("<?for-each-group:DATA_RECORD[ROW_TYPE='RACK'];AISLE?>", 4), space_after=0))
    parts.append(para(t("Aisle <?AISLE?>", 20, bold=True), space_after=40, keepn=True))
    header = [(LEVEL_COL, HDR_BG, t("Level", 14, bold=True, color=WHITE))] + [
        (BAY_COL, HDR_BG, t(f"Bay {b:02d}", 14, bold=True, color=WHITE)) for b in range(1, 11)]
    parts.append(row(header, header=True))
    body = [(LEVEL_COL, HDR_BG, t("<?for-each:current-group()?>", 4)
             + t("L<?RACK_LEVEL?>", 16, bold=True, color=WHITE))]
    for b in range(1, 11):
        f = f"B{b:02d}"
        body.append((BAY_COL, EMPTY_BG,
                     t(heat_attrs(f + "_HEAT"), 4)
                     + t(f"<?{f}_LOC?>", 13, color=SLATE) + "\\line "
                     + t(f"<?{f}_SKU?><?if@inlines:{f}_AGE!=''?> <?{f}_AGE?>d<?end if?>", 14, bold=True)
                     + (t("<?end for-each?>", 4) if b == 10 else "")))
    parts.append(row(body, keep=False, height=400))
    parts.append(para(t("<?end for-each-group?>", 4), space_after=60))

    # --- floor areas
    parts.append(para(t("Floor areas (not racked)", 20, bold=True), space_after=40, keepn=True))
    widths = [2600, 2000, 2600, 2400, 1400]
    parts.append(row([(w, HDR_BG, t(h, 14, bold=True, color=WHITE)) for w, h in
                      zip(widths, ["Location", "Zone", "Oldest SKU", "Oldest lot age", "Lots"])], header=True))
    area_fields = ["AREA_LOC", "AREA_ZONE", "AREA_SKU", "AREA_AGE", "AREA_LOTS"]
    area_cells = []
    for i, (w, fld) in enumerate(zip(widths, area_fields)):
        content = t(heat_attrs("AREA_HEAT"), 4)
        if i == 0:
            content = t("<?for-each:DATA_RECORD[ROW_TYPE='AREA']?>", 4) + content
        value = f"<?{fld}?>" + ("<?if@inlines:AREA_AGE!=''?> days<?end if?>" if fld == "AREA_AGE" else "")
        content += t(value, 16, bold=(i == 0))
        if i == len(widths) - 1:
            content += t("<?end for-each?>", 4)
        area_cells.append((w, EMPTY_BG, content))
    parts.append(row(area_cells, keep=False, height=300))

    parts.append(para(t(
        "How it's colored: occupied locations are ranked by the age of their oldest lot (days since received). "
        "The oldest 10% (rounded up) are red and the next 10% yellow; ties share a color, so a bucket can run "
        "slightly over. The ranking is computed in the SQL dataset with a RANK() window function; the template "
        "only maps each bucket to a cell color with BI Publisher conditional formatting. Synthetic lab data.",
        14, color=SLATE), space_after=0))

    parts.append("}")
    return "\n".join(parts)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="ascii")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
