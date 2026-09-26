"""Generate reports/held-damaged-inventory/template.rtf: held and damaged inventory by status.

Same approach as the scorecard, heatmap and BOL generators: a reproducible starting point
that can be restyled in Word afterward (once edited in Word, the Word file is the master copy).

Layout (portrait): header (logo, facility, run date, lot / unit / value totals), then one
table: a repeating column header, a section row per STOCK_STATUS, its lots oldest receipt
first, a subtotal row per status, and a grand total. Group order and row order come from
the SQL's ORDER BY; current-group() keeps that order. A facility with nothing held prints
a one-line message instead of the table.

Data: bip-report/reports/held-damaged-inventory/dataset.sql (sample: sample.xml).

    python bip-report/tools/build_held_damaged_template.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT.parent / "dashboard" / "public" / "bi-publisher" / "hello-world-tire-logo.png"
OUT = ROOT / "reports" / "held-damaged-inventory" / "template.rtf"

BLACK, SLATE, BORDER, HDR_BG, WHITE, LIGHT_BG, BRAND_RED, SECTION_BG = range(1, 9)
COLORS = [(0, 0, 0), (71, 85, 105), (203, 213, 225), (38, 38, 38), (255, 255, 255),
          (241, 243, 246), (215, 25, 32), (226, 232, 240)]

PAGE_W, PAGE_H, MARGIN = 12240, 15840, 720    # portrait letter, 0.5" margins
USABLE = PAGE_W - 2 * MARGIN                  # 10800

HELD = "DATA_RECORD[STOCK_STATUS]"            # rows with a lot (an empty facility has none)
QTY = "'#,##0'"
MONEY = "'#,##0.00'"


def t(text, size=None, bold=False, color=None, italic=False):
    """A formatted run in its own {...} group (BI Publisher drops ungrouped formatting)."""
    words = ""
    if size:
        words += f"\\fs{size}"
    if bold:
        words += "\\b"
    if italic:
        words += "\\i"
    if color:
        words += f"\\cf{color}"
    return "{" + words + " " + text + "}"


def row(cells, height=None, header=False, keep=True):
    """cells: list of (width, content, options) with options: shade, align, borders."""
    out = ["\\trowd\\trgaph80\\trleft0"]
    if keep:
        out.append("\\trkeep")
    if header:
        out.append("\\trhdr")
    if height:
        out.append(f"\\trrh{height}")
    x = 0
    for width, _, opt in cells:
        x += width
        spec = ""
        if opt.get("borders", True):
            spec += "".join(f"\\clbrdr{side}\\brdrs\\brdrw10\\brdrcf{BORDER}" for side in "tlbr")
        if opt.get("shade"):
            spec += f"\\clcbpat{opt['shade']}"
        spec += "\\clvertalc"
        out.append(f"{spec}\\cellx{x}")
    for _, content, opt in cells:
        align = {"center": "\\qc", "right": "\\qr"}.get(opt.get("align"), "\\ql")
        out.append(f"\\pard\\intbl{align}\\plain\\f0\\fs16 {content}\\cell")
    out.append("\\row")
    return "\n".join(out)


def cell(content, width, **opt):
    return (width, content, opt)


def para(content, space_after=0, space_before=0):
    return f"\\pard\\ql\\sb{space_before}\\sa{space_after}\\plain\\f0\\fs17 {content}\\par"


def fmt(path, mask):
    return f"<?format-number({path},{mask})?>"


def logo_pict(goal_w=1900):
    data = LOGO.read_bytes()
    w_px, h_px = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    goal_h = round(goal_w * h_px / w_px)
    return f"{{\\pict\\pngblip\\picw{w_px}\\pich{h_px}\\picwgoal{goal_w}\\pichgoal{goal_h} {data.hex()}}}"


def build():
    L = "\\line "
    p = [
        "{\\rtf1\\ansi\\ansicpg1252\\deff0",
        "{\\fonttbl{\\f0\\fswiss\\fcharset0 Arial;}}",
        "{\\colortbl;" + "".join(f"\\red{r}\\green{g}\\blue{b};" for r, g, b in COLORS) + "}",
        "{\\stylesheet{\\ql\\f0\\fs17 Normal;}}",
        # An \info group is required for BI Publisher to honor the page size and margins.
        "{\\info{\\title Held and Damaged Inventory}{\\author Hello World Tire lab}}",
        f"\\paperw{PAGE_W}\\paperh{PAGE_H}\\margl{MARGIN}\\margr{MARGIN}\\margt{MARGIN}\\margb{MARGIN}",
        "\\sectd\\ltrsect\\sectdefaultcl",
    ]

    # --- header
    rule = f"\\clbrdrb\\brdrs\\brdrw30\\brdrcf{BRAND_RED}\\clvertalc"
    p.append("\\trowd\\trgaph80\\trleft0" + f"{rule}\\cellx2400{rule}\\cellx7800{rule}\\cellx{USABLE}")
    p.append(f"\\pard\\intbl\\ql\\plain\\f0 {logo_pict()}\\cell")
    p.append("\\pard\\intbl\\ql\\plain\\f0 " + t("Held & Damaged Inventory", 30, bold=True) + L
             + t("Facility: ", 17, color=SLATE) + t("<?WAREHOUSE_CODE?>", 17, bold=True)
             + t(" - <?WAREHOUSE_NAME?>", 17) + L
             + t("Stock status other than AVAILABLE, oldest receipt first", 15, color=SLATE) + "\\cell")
    p.append("\\pard\\intbl\\qr\\plain\\f0 " + t("Run date ", 15, color=SLATE) + t("<?RUN_DATE?>", 17, bold=True) + L
             + t("Lots ", 15, color=SLATE) + t(f"<?count({HELD})?>", 17, bold=True) + L
             + t("Units ", 15, color=SLATE) + t(fmt(f"sum({HELD}/ON_HAND_QTY)", QTY), 17, bold=True) + L
             + t("Value ", 15, color=SLATE) + t("$" + fmt(f"sum({HELD}/EXTENDED_VALUE)", MONEY), 17, bold=True)
             + "\\cell\\row")
    p.append(para(t(" ", 8), space_after=60))

    # --- nothing held
    p.append(para(t(f"<?if:not({HELD})?>", 4)
                  + t("No held, damaged or other non-available inventory at this facility.", 18, italic=True)
                  + t("<?end if?>", 4), space_before=120))

    # --- the table, only when there are lots
    p.append(para(t(f"<?if:{HELD}?>", 4)))
    cw = [1350, 1450, 2950, 1250, 900, 1150, 650, 1100]   # sums to USABLE
    heads = ["Location", "SKU", "Description", "Lot", "On hand", "Received", "Age (days)", "Ext. value"]
    aligns = ["left", "left", "left", "left", "right", "center", "right", "right"]
    p.append(row([cell(t(h, 15, bold=True, color=WHITE), w, shade=HDR_BG, align=a)
                  for w, h, a in zip(cw, heads, aligns)], header=True))
    # Section row: the attribute keeps it on the same page as its first lot.
    p.append(row([cell(t(f"<?for-each-group:{HELD};STOCK_STATUS?>", 4)
                       + t("<?attribute@row:keep-with-next.within-page;'always'?>", 4)
                       + t("<?STOCK_STATUS?>", 18, bold=True)
                       + t("   <?count(current-group())?> lot(s)", 15, color=SLATE), USABLE, shade=SECTION_BG)]))
    p.append(row([
        cell(t("<?for-each:current-group()?>", 4) + t("<?LOCATION_CODE?>", 16), cw[0]),
        cell(t("<?SKU?>", 16), cw[1]),
        cell(t("<?DESCRIPTION?>", 16), cw[2]),
        cell(t("<?LOT_NUMBER?>", 16), cw[3]),
        cell(t(fmt("ON_HAND_QTY", QTY), 16), cw[4], align="right"),
        cell(t("<?RECEIVED_DATE?>", 16), cw[5], align="center"),
        cell(t("<?AGE_DAYS?>", 16), cw[6], align="right"),
        cell(t(fmt("EXTENDED_VALUE", MONEY), 16) + t("<?end for-each?>", 4), cw[7], align="right"),
    ], height=300))
    lead = sum(cw[:4])
    p.append(row([
        cell(t("Total <?STOCK_STATUS?>", 16, bold=True), lead, shade=LIGHT_BG, align="right"),
        cell(t(fmt("sum(current-group()/ON_HAND_QTY)", QTY), 16, bold=True), cw[4], shade=LIGHT_BG, align="right"),
        cell(t(" ", 16), cw[5] + cw[6], shade=LIGHT_BG),
        cell(t("$" + fmt("sum(current-group()/EXTENDED_VALUE)", MONEY), 16, bold=True)
             + t("<?end for-each-group?>", 4), cw[7], shade=LIGHT_BG, align="right"),
    ], height=320))
    p.append(row([
        cell(t("Grand total", 17, bold=True, color=WHITE), lead, shade=HDR_BG, align="right"),
        cell(t(fmt(f"sum({HELD}/ON_HAND_QTY)", QTY), 17, bold=True, color=WHITE), cw[4], shade=HDR_BG, align="right"),
        cell(t(" ", 16), cw[5] + cw[6], shade=HDR_BG),
        cell(t("$" + fmt(f"sum({HELD}/EXTENDED_VALUE)", MONEY), 17, bold=True, color=WHITE),
             cw[7], shade=HDR_BG, align="right"),
    ], height=340))
    p.append(para(t("<?end if?>", 4)))

    p.append(para(t("Age is days since the lot was received. Extended value is on-hand quantity times the "
                    "item unit cost, the same valuation as the Inventory Aging report.", 14, color=SLATE),
                  space_before=160))
    p.append(para(t("Synthetic lab data: Hello World Tire is demo branding; all items and figures are fictional. "
                    "Rendered by the BI Publisher engine from Db2.", 13, color=SLATE, italic=True), space_before=60))
    p.append("}")
    return "\n".join(p)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="ascii")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
