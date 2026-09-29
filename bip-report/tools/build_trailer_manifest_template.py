"""Generate reports/trailer-manifest/template.rtf: the facility's single most recent trailer.

Same approach as the scorecard, heatmap, BOL and held-damaged generators: a reproducible
starting point that can be restyled in Word afterward (once edited in Word, the Word file is
the master copy).

Layout (portrait): header (logo, facility, run date, PO / unit / weight totals), then a
details box with the trailer, seal, PRO, carrier and ship date, then one table grouped by
customer: a repeating column header, a section row per customer, one row per PO (its
quantity and weight, i.e. the PO subtotal), a subtotal row per customer and a grand total.
Group order and row order come from the SQL's ORDER BY; current-group() keeps that order.
The quantity and weight totals reconcile with the VICS BOL for the same trailer.

Data: bip-report/reports/trailer-manifest/dataset.sql (sample: sample.xml).

    python bip-report/tools/build_trailer_manifest_template.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT.parent / "dashboard" / "public" / "bi-publisher" / "hello-world-tire-logo.png"
OUT = ROOT / "reports" / "trailer-manifest" / "template.rtf"

BLACK, SLATE, BORDER, HDR_BG, WHITE, LIGHT_BG, BRAND_RED, SECTION_BG = range(1, 9)
COLORS = [(0, 0, 0), (71, 85, 105), (203, 213, 225), (38, 38, 38), (255, 255, 255),
          (241, 243, 246), (215, 25, 32), (226, 232, 240)]

PAGE_W, PAGE_H, MARGIN = 12240, 15840, 720    # portrait letter, 0.5" margins
USABLE = PAGE_W - 2 * MARGIN                  # 10800

REC = "DATA_RECORD"                           # one record per customer PO
QTY = "'#,##0'"


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
        "{\\info{\\title Trailer Manifest}{\\author Hello World Tire lab}}",
        f"\\paperw{PAGE_W}\\paperh{PAGE_H}\\margl{MARGIN}\\margr{MARGIN}\\margt{MARGIN}\\margb{MARGIN}",
        "\\sectd\\ltrsect\\sectdefaultcl",
    ]

    # --- header
    rule = f"\\clbrdrb\\brdrs\\brdrw30\\brdrcf{BRAND_RED}\\clvertalc"
    p.append("\\trowd\\trgaph80\\trleft0" + f"{rule}\\cellx2400{rule}\\cellx7800{rule}\\cellx{USABLE}")
    p.append(f"\\pard\\intbl\\ql\\plain\\f0 {logo_pict()}\\cell")
    p.append("\\pard\\intbl\\ql\\plain\\f0 " + t("Trailer Manifest", 30, bold=True) + L
             + t("Facility: ", 17, color=SLATE) + t("<?WAREHOUSE_CODE?>", 17, bold=True)
             + t(" - <?WAREHOUSE_NAME?>", 17) + L
             + t("Single most recent trailer (same scope as the VICS BOL)", 15, color=SLATE) + "\\cell")
    p.append("\\pard\\intbl\\qr\\plain\\f0 " + t("Run date ", 15, color=SLATE) + t("<?RUN_DATE?>", 17, bold=True) + L
             + t("POs ", 15, color=SLATE) + t(f"<?count({REC})?>", 17, bold=True) + L
             + t("Units ", 15, color=SLATE) + t(fmt(f"sum({REC}/PO_QTY)", QTY), 17, bold=True) + L
             + t("Weight (lb) ", 15, color=SLATE) + t(fmt(f"sum({REC}/PO_WEIGHT)", QTY), 17, bold=True)
             + "\\cell\\row")
    p.append(para(t(" ", 8), space_after=60))

    # --- trailer details box (trailer / seal / PRO are constant for the single trailer)
    dw = [1350, 3050, 1350, 2200, 1350, USABLE - 1350 - 3050 - 1350 - 2200 - 1350]
    lab = lambda s: t(s, 14, color=SLATE)
    p.append(row([
        cell(lab("Trailer"), dw[0], shade=LIGHT_BG),
        cell(t("<?TRAILER_NUMBER?>", 17, bold=True), dw[1]),
        cell(lab("Seal"), dw[2], shade=LIGHT_BG),
        cell(t("<?SEAL_NUMBER?>", 17, bold=True), dw[3]),
        cell(lab("PRO"), dw[4], shade=LIGHT_BG),
        cell(t("<?PRO_NUMBER?>", 17, bold=True), dw[5]),
    ], height=300))
    p.append(row([
        cell(lab("Carrier"), dw[0], shade=LIGHT_BG),
        cell(t("<?CARRIER_NAME?>", 16) + t(" (<?SCAC?>)", 14, color=SLATE), dw[1]),
        cell(lab("Ship date"), dw[2], shade=LIGHT_BG),
        cell(t("<?SHIP_DATE?>", 17, bold=True) + t(" <?SHIPMENT_STATUS?>", 14, color=SLATE), dw[3]),
        cell(lab("BOL"), dw[4], shade=LIGHT_BG),
        cell(t("<?BOL_NUMBER?>", 16), dw[5]),
    ], height=300))
    p.append(para(t(" ", 8), space_after=60))

    # --- nothing loaded (a facility with no trailer returns no records)
    p.append(para(t(f"<?if:not({REC})?>", 4)
                  + t("No loaded or shipped trailer for this facility.", 18, italic=True)
                  + t("<?end if?>", 4), space_before=120))

    # --- the manifest table, only when there is a trailer
    p.append(para(t(f"<?if:{REC}?>", 4)))
    cw = [5000, 2900, 2900]                               # Customer PO / Quantity / Weight; sums to USABLE
    heads = ["Customer PO", "Quantity", "Weight (lb)"]
    aligns = ["left", "right", "right"]
    p.append(row([cell(t(h, 15, bold=True, color=WHITE), w, shade=HDR_BG, align=a)
                  for w, h, a in zip(cw, heads, aligns)], header=True))
    # Section row per customer: the attribute keeps it on the same page as its first PO.
    p.append(row([cell(t(f"<?for-each-group:{REC};CUSTOMER_NAME?>", 4)
                       + t("<?attribute@row:keep-with-next.within-page;'always'?>", 4)
                       + t("<?CUSTOMER_NAME?>", 17, bold=True)
                       + t("   <?count(current-group())?> PO(s)", 15, color=SLATE), USABLE, shade=SECTION_BG)]))
    # One row per PO (the PO subtotal).
    p.append(row([
        cell(t("<?for-each:current-group()?>", 4) + t("<?CUSTOMER_PO?>", 16), cw[0]),
        cell(t(fmt("PO_QTY", QTY), 16), cw[1], align="right"),
        cell(t(fmt("PO_WEIGHT", QTY), 16) + t("<?end for-each?>", 4), cw[2], align="right"),
    ], height=300))
    # Subtotal per customer.
    p.append(row([
        cell(t("Subtotal ", 16, bold=True) + t("<?CUSTOMER_NAME?>", 16, bold=True), cw[0], shade=LIGHT_BG, align="right"),
        cell(t(fmt("sum(current-group()/PO_QTY)", QTY), 16, bold=True), cw[1], shade=LIGHT_BG, align="right"),
        cell(t(fmt("sum(current-group()/PO_WEIGHT)", QTY), 16, bold=True)
             + t("<?end for-each-group?>", 4), cw[2], shade=LIGHT_BG, align="right"),
    ], height=320))
    # Grand total: the same arithmetic the VICS BOL grand total uses, so the two reconcile.
    p.append(row([
        cell(t("Grand total", 17, bold=True, color=WHITE), cw[0], shade=HDR_BG, align="right"),
        cell(t(fmt(f"sum({REC}/PO_QTY)", QTY), 17, bold=True, color=WHITE), cw[1], shade=HDR_BG, align="right"),
        cell(t(fmt(f"sum({REC}/PO_WEIGHT)", QTY), 17, bold=True, color=WHITE), cw[2], shade=HDR_BG, align="right"),
    ], height=340))
    p.append(para(t("<?end if?>", 4)))

    p.append(para(t("Quantity is ordered tires; weight is tires plus 40 lb per pallet, the same basis as the "
                    "VICS Bill of Lading, so the grand total reconciles with the BOL for this trailer.",
                    14, color=SLATE), space_before=160))
    p.append(para(t("Synthetic lab data: Hello World Tire is demo branding; all parties, numbers and figures "
                    "are fictional. Rendered by the BI Publisher engine from Db2.", 13, color=SLATE, italic=True),
                  space_before=60))
    p.append("}")
    return "\n".join(p)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="ascii")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
