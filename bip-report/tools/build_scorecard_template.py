"""Generate reports/client-kpi-scorecard/template.rtf: a one-page client KPI scorecard.

Same approach as the heatmap and BOL generators: a reproducible starting point that can
be restyled in Word afterward (once edited in Word, the Word file is the master copy).

Layout (portrait): header (logo, client, facility, period, targets met), the KPI table
grouped by section (Outbound / Inbound / Inventory) with a green MET / red MISSED status
cell, the 4-week trend table, and the metric definitions. Renders to PDF or .xlsx.

Data: bip-report/reports/client-kpi-scorecard/dataset.sql (ROW_TYPE KPI / WEEK rows).

    python bip-report/tools/build_scorecard_template.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT.parent / "dashboard" / "public" / "bi-publisher" / "hello-world-tire-logo.png"
OUT = ROOT / "reports" / "client-kpi-scorecard" / "template.rtf"

BLACK, SLATE, BORDER, HDR_BG, WHITE, LIGHT_BG, BRAND_RED, SECTION_BG = range(1, 9)
COLORS = [(0, 0, 0), (71, 85, 105), (203, 213, 225), (38, 38, 38), (255, 255, 255),
          (241, 243, 246), (215, 25, 32), (226, 232, 240)]
STATUS_BG = {"MET": "#B7E1C1", "MISSED": "#F4B6B6"}

PAGE_W, PAGE_H, MARGIN = 12240, 15840, 720    # portrait letter, 0.5" margins
USABLE = PAGE_W - 2 * MARGIN                  # 10800


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
    """cells: list of (width, content, options) with options: shade, align, valign, borders."""
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
        out.append(f"\\pard\\intbl{align}\\plain\\f0\\fs17 {content}\\cell")
    out.append("\\row")
    return "\n".join(out)


def cell(content, width, **opt):
    return (width, content, opt)


def para(content, space_after=0, space_before=0):
    return f"\\pard\\ql\\sb{space_before}\\sa{space_after}\\plain\\f0\\fs17 {content}\\par"


def status_cell_attrs():
    """Green MET / red MISSED cell shading: BI Publisher conditional formatting."""
    return "".join(
        f"<?if:KPI_STATUS='{status}'?><?attribute@incontext:background-color;'{hexcolor}'?><?end if?>"
        for status, hexcolor in STATUS_BG.items())


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
        "{\\info{\\title Client KPI Scorecard}{\\author Hello World Tire lab}}",
        f"\\paperw{PAGE_W}\\paperh{PAGE_H}\\margl{MARGIN}\\margr{MARGIN}\\margt{MARGIN}\\margb{MARGIN}",
        "\\sectd\\ltrsect\\sectdefaultcl",
    ]

    # --- header
    rule = f"\\clbrdrb\\brdrs\\brdrw30\\brdrcf{BRAND_RED}\\clvertalc"
    p.append("\\trowd\\trgaph80\\trleft0" + f"{rule}\\cellx2400{rule}\\cellx7800{rule}\\cellx{USABLE}")
    p.append(f"\\pard\\intbl\\ql\\plain\\f0 {logo_pict()}\\cell")
    p.append("\\pard\\intbl\\ql\\plain\\f0 " + t("Client KPI Scorecard", 30, bold=True) + L
             + t("Client: ", 17, color=SLATE) + t("<?CLIENT_NAME?>", 17, bold=True) + L
             + t("Facility: ", 17, color=SLATE) + t("<?FACILITY_CODE?>", 17, bold=True)
             + t(" - <?FACILITY_NAME?>", 17) + "\\cell")
    p.append("\\pard\\intbl\\qr\\plain\\f0 " + t("Period", 15, color=SLATE) + L
             + t("<?PERIOD_START?> - <?PERIOD_END?>", 17, bold=True) + L
             + t("Targets met: ", 15, color=SLATE) + t("<?KPIS_MET?> of <?KPIS_WITH_TARGET?>", 17, bold=True)
             + "\\cell\\row")
    p.append(para(t(" ", 8), space_after=60))

    # --- KPI table, grouped by section
    kw = [3800, 2400, 2400, 2200]
    p.append(row([cell(t(h, 16, bold=True, color=WHITE), w, shade=HDR_BG, align=a)
                  for w, h, a in zip(kw, ["Measure", "Result", "Target", "Status"],
                                     ["left", "right", "right", "center"])], header=True))
    p.append(row([cell(t("<?for-each-group:DATA_RECORD[ROW_TYPE='KPI'];SECTION?>", 4)
                       + t("<?SECTION?>", 17, bold=True), USABLE, shade=SECTION_BG)]))
    p.append(row([
        cell(t("<?for-each:current-group()?>", 4) + t("<?KPI_NAME?>", 17), kw[0]),
        cell(t("<?KPI_VALUE?>", 18, bold=True), kw[1], align="right"),
        cell(t("<?KPI_TARGET?>", 17, color=SLATE), kw[2], align="right"),
        cell(t(status_cell_attrs(), 4)
             + t("<?if@inlines:KPI_STATUS!='INFO'?><?KPI_STATUS?><?end if?>", 16, bold=True)
             + t("<?end for-each?><?end for-each-group?>", 4), kw[3], align="center"),
    ], height=330))
    p.append(para(t(" ", 8), space_after=120))

    # --- 4-week trend
    ww = [1800, 1800, 1800, 1800, 1800, 1800]
    p.append(para(t("Weekly trend", 20, bold=True), space_after=60))
    p.append(row([cell(t(h, 16, bold=True, color=WHITE), w, shade=HDR_BG, align="center")
                  for w, h in zip(ww, ["Week ending", "Orders shipped", "Units shipped",
                                       "On-time %", "Unit fill rate", "Receipts"])], header=True))
    p.append(row([
        cell(t("<?for-each:DATA_RECORD[ROW_TYPE='WEEK']?>", 4) + t("<?WEEK_ENDING?>", 17, bold=True),
             ww[0], align="center"),
        cell(t("<?WK_ORDERS?>", 17), ww[1], align="center"),
        cell(t("<?WK_UNITS?>", 17), ww[2], align="center"),
        cell(t("<?WK_ON_TIME?>", 17), ww[3], align="center"),
        cell(t("<?WK_FILL?>", 17), ww[4], align="center"),
        cell(t("<?WK_RECEIPTS?>", 17) + t("<?end for-each?>", 4), ww[5], align="center"),
    ], height=330))

    # --- definitions
    p.append(para(t("Definitions", 17, bold=True), space_before=240, space_after=40))
    for name, text in [
        ("On-time ship %", "shipped orders whose actual ship date is on or before the promised ship date."),
        ("Unit fill rate", "units shipped / units ordered, on orders shipped in the period."),
        ("Open orders past due", "orders not yet shipped whose promised ship date is before the period end."),
        ("Avg dock-to-stock", "hours from receipt to first putaway of the same item and lot."),
        ("Units aged over 180 days", "share of on-hand units received more than 180 days before period end."),
        ("Period", "the 4 weeks ending on the facility's last shipping day; weeks are 7-day buckets ending on that day."),
    ]:
        p.append(para(t(name + ": ", 15, bold=True) + t(text, 15), space_after=20))
    p.append(para(t("Targets are illustrative SLA terms. Synthetic lab data: Hello World Tire is demo branding; "
                    "all orders and figures are fictional. Rendered by the BI Publisher engine from Db2.",
                    13, color=SLATE, italic=True), space_before=160))
    p.append("}")
    return "\n".join(p)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="ascii")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
