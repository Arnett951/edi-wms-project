"""Generate reports/vics-bol/template.rtf: a straight Bill of Lading in the VICS layout.

Like build_heatmap_template.py, a reproducible starting point that can be restyled in
Word afterward. It follows the section order of the VICS (now GS1 US) voluntary BOL:
ship from / ship to / third party / special instructions on the left, BOL number,
carrier, trailer, seal, SCAC, PRO and freight terms on the right, then Customer Order
Information (one row per PO) and Carrier Information (one row per commodity) with
grand totals, then the liability / declared value text and the signature block.

The form wording below is written for this lab; check any production form against
your carrier contracts and the current GS1 US BOL guideline.

Data: bip-report/reports/vics-bol/dataset.sql (ROW_TYPE ORDER / COMMODITY rows, header
fields and totals on every row).

    python bip-report/tools/build_bol_template.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT.parent / "dashboard" / "public" / "bi-publisher" / "hello-world-tire-logo.png"
OUT = ROOT / "reports" / "vics-bol" / "template.rtf"

BLACK, SLATE, BORDER, HDR_BG, WHITE, LIGHT_BG, BRAND_RED = range(1, 8)
COLORS = [(0, 0, 0), (71, 85, 105), (0, 0, 0), (38, 38, 38), (255, 255, 255), (241, 243, 246), (215, 25, 32)]

PAGE_W, PAGE_H, MARGIN = 12240, 15840, 540    # portrait letter, 0.375" margins
USABLE = PAGE_W - 2 * MARGIN                  # 11160
HALF = USABLE // 2                            # 5580


def t(text, size=None, bold=False, color=None, italic=False, font=0):
    """A formatted run, always in its own {...} group (BI Publisher drops ungrouped formatting)."""
    words = f"\\f{font}" if font else ""
    if size:
        words += f"\\fs{size}"
    if bold:
        words += "\\b"
    if italic:
        words += "\\i"
    if color:
        words += f"\\cf{color}"
    return "{" + words + " " + text + "}"


def row(cells, height=None, header=False):
    """cells: list of (width, content, options) with options: shade, align, borders."""
    out = ["\\trowd\\trgaph60\\trleft0\\trkeep"]
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
        spec += "\\clvertalc" if opt.get("valign") == "center" else "\\clvertalt"
        out.append(f"{spec}\\cellx{x}")
    for _, content, opt in cells:
        align = {"center": "\\qc", "right": "\\qr"}.get(opt.get("align"), "\\ql")
        out.append(f"\\pard\\intbl{align}\\plain\\f0\\fs15 {content}\\cell")
    out.append("\\row")
    return "\n".join(out)


def bar(text, width):
    """Dark section header cell."""
    return (width, t(text, 15, bold=True, color=WHITE), {"shade": HDR_BG, "valign": "center"})


def cell(content, width, **opt):
    return (width, content, opt)


def para(content, space_after=0):
    return f"\\pard\\ql\\sa{space_after}\\plain\\f0\\fs15 {content}\\par"


def label(text):
    return t(text, 14, color=SLATE)


def value(field, size=16, bold=True):
    return t(f"<?{field}?>", size, bold=bold)


def logo_pict(goal_w=1700):
    data = LOGO.read_bytes()
    w_px, h_px = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    goal_h = round(goal_w * h_px / w_px)
    return f"{{\\pict\\pngblip\\picw{w_px}\\pich{h_px}\\picwgoal{goal_w}\\pichgoal{goal_h} {data.hex()}}}"


def build():
    L = "\\line "
    p = [
        "{\\rtf1\\ansi\\ansicpg1252\\deff0",
        # f1 = the barcode font. Default Code 128 is BI Publisher's built-in family name: Template
        # Builder's own xdo.cfg maps it to Libre Barcode 128, and so does config/xdo.cfg here, so the
        # local preview and the live service draw the same barcode.
        "{\\fonttbl{\\f0\\fswiss\\fcharset0 Arial;}{\\f1\\fnil\\fcharset0 Default Code 128;}}",
        "{\\colortbl;" + "".join(f"\\red{r}\\green{g}\\blue{b};" for r, g, b in COLORS) + "}",
        "{\\stylesheet{\\ql\\f0\\fs15 Normal;}}",
        # An \info group is required for BI Publisher to honor the page size and margins.
        "{\\info{\\title VICS Bill of Lading}{\\author Hello World Tire lab}}",
        f"\\paperw{PAGE_W}\\paperh{PAGE_H}\\margl{MARGIN}\\margr{MARGIN}\\margt{MARGIN}\\margb{MARGIN}",
        "\\sectd\\ltrsect\\sectdefaultcl",
    ]

    # --- title
    p.append(row([
        cell(logo_pict(), 2600, borders=False, valign="center"),
        cell(t("BILL OF LADING", 34, bold=True), 5960, align="center", borders=False, valign="center"),
        cell(label("Date: ") + value("SHIP_DATE", 18) + L + label("Page 1 of 1"), 2600, align="right",
             borders=False, valign="center"),
    ]))
    p.append(para(t(" ", 6)))

    # --- top half: left column (ship from / to / third party / instructions), right column
    p.append(row([bar("SHIP FROM", HALF),
                  cell(label("Bill of Lading Number: ") + t("<?BOL_NUMBER?>", 22, bold=True), HALF, valign="center")]))
    p.append(row([
        cell(label("Name: ") + value("FROM_NAME") + L
             + label("Address: ") + value("FROM_ADDRESS", bold=False) + L
             + label("City/State/Zip: ") + value("FROM_CITY_STATE_ZIP", bold=False) + L
             + label("SID#: ") + value("FROM_SID", bold=False) + t("          FOB: [  ]", 14), HALF),
        # Code 128 text encoded in SQL (start B + data + check + stop), drawn with the barcode font.
        cell(t("<?BOL_BARCODE?>", 64, font=1) + L + t("<?BOL_NUMBER?>", 15), HALF,
             align="center", valign="center"),
    ], height=1100))
    p.append(row([bar("SHIP TO", HALF),
                  cell(label("CARRIER NAME: ") + value("CARRIER_NAME"), HALF, valign="center")]))
    p.append(row([
        cell(label("Name: ") + value("TO_NAME") + label("      Location #: ") + value("TO_LOCATION") + L
             + label("Address: ") + value("TO_ADDRESS", bold=False) + L
             + label("City/State/Zip: ") + value("TO_CITY_STATE_ZIP", bold=False) + L
             + label("CID#: ") + value("TO_CID", bold=False) + t("          FOB: [  ]", 14), HALF),
        cell(label("Trailer number: ") + value("TRAILER_NUMBER") + L
             + label("Serial number(s): ") + value("SEAL_NUMBER") + t(" (seal)", 13, color=SLATE) + L
             + label("SCAC: ") + value("SCAC") + L
             + label("Pro number: ") + value("PRO_NUMBER")
             # Own centered paragraph: a barcode needs a blank quiet zone on both sides to scan.
             + "\\par\\pard\\intbl\\qc\\plain\\f0 " + t("<?PRO_BARCODE?>", 52, font=1), HALF),
    ], height=900))
    p.append(row([bar("THIRD PARTY FREIGHT CHARGES BILL TO:", HALF),
                  bar("FREIGHT CHARGE TERMS", HALF)]))
    p.append(row([
        cell(label("Name:") + L + label("Address:") + L + label("City/State/Zip:"), HALF),
        cell(t("(freight charges are prepaid unless marked otherwise)", 13, italic=True) + L
             + label("Prepaid ") + value("BOX_PREPAID") + label("      Collect ") + value("BOX_COLLECT")
             + label("      3rd Party ") + value("BOX_THIRD_PARTY"), HALF, valign="center"),
    ], height=620))
    p.append(row([
        cell(label("SPECIAL INSTRUCTIONS: ") + L + value("SPECIAL_INSTRUCTIONS", 15, bold=False), HALF),
        cell(t("[  ]", 15, bold=True) + t(" Master Bill of Lading: with attached underlying Bills of Lading", 14),
             HALF, valign="center"),
    ], height=620))
    p.append(para(t(" ", 6)))

    # --- customer order information
    co = [3000, 1100, 1300, 1000, 600, 4160]
    p.append(row([bar("CUSTOMER ORDER INFORMATION", USABLE)]))
    p.append(row([cell(t(h, 13, bold=True), w, shade=LIGHT_BG, align="center", valign="center") for w, h in zip(
        co, ["CUSTOMER ORDER NUMBER", "# PKGS", "WEIGHT", "PALLET/SLIP  Y", "N", "ADDITIONAL SHIPPER INFO"])],
        header=True))
    p.append(row([
        cell(t("<?for-each:DATA_RECORD[ROW_TYPE='ORDER']?>", 4) + value("ORD_PO", 15, bold=False), co[0]),
        cell(value("ORD_PKGS", 15, bold=False), co[1], align="center"),
        cell(value("ORD_WEIGHT", 15, bold=False), co[2], align="right"),
        cell(t("<?if@inlines:ORD_PALLET_SLIP='Y'?>(Y)<?end if?>", 15, bold=True), co[3], align="center"),
        cell(t("<?if@inlines:ORD_PALLET_SLIP='N'?>(N)<?end if?>", 15, bold=True), co[4], align="center"),
        cell(value("ORD_ADDL_INFO", 15, bold=False) + t("<?end for-each?>", 4), co[5]),
    ]))
    p.append(row([
        cell(t("GRAND TOTAL", 15, bold=True), co[0], shade=LIGHT_BG),
        cell(value("TOTAL_PALLETS", 15), co[1], align="center", shade=LIGHT_BG),
        cell(value("TOTAL_WEIGHT", 15), co[2], align="right", shade=LIGHT_BG),
        cell("", co[3] + co[4] + co[5], shade=LIGHT_BG),
    ]))
    p.append(para(t(" ", 6)))

    # --- carrier information
    ci = [800, 800, 900, 900, 1100, 600, 4260, 1000, 800]
    p.append(row([bar("CARRIER INFORMATION", USABLE)]))
    p.append(row([cell(t(h, 13, bold=True), w, shade=LIGHT_BG, align="center", valign="center") for w, h in zip(
        [ci[0] + ci[1], ci[2] + ci[3], ci[4], ci[5], ci[6], ci[7] + ci[8]],
        ["HANDLING UNIT", "PACKAGE", "WEIGHT", "H.M. (X)", "COMMODITY DESCRIPTION", "LTL ONLY"])], header=True))
    p.append(row([cell(t(h, 13, bold=True), w, shade=LIGHT_BG, align="center", valign="center") for w, h in zip(
        ci, ["QTY", "TYPE", "QTY", "TYPE", "", "", "Commodities requiring special or additional care or attention "
             "in handling or stowing must be so marked and packaged as to ensure safe transportation.",
             "NMFC #", "CLASS"])], header=True))
    p.append(row([
        cell(t("<?for-each:DATA_RECORD[ROW_TYPE='COMMODITY']?>", 4) + value("CMD_HU_QTY", 15, bold=False),
             ci[0], align="center"),
        cell(value("CMD_HU_TYPE", 15, bold=False), ci[1], align="center"),
        cell(value("CMD_PKG_QTY", 15, bold=False), ci[2], align="center"),
        cell(value("CMD_PKG_TYPE", 15, bold=False), ci[3], align="center"),
        cell(value("CMD_WEIGHT", 15, bold=False), ci[4], align="right"),
        cell(value("CMD_HM", 15, bold=False), ci[5], align="center"),
        cell(value("CMD_DESCRIPTION", 15, bold=False), ci[6]),
        cell("", ci[7], align="center"),
        cell(t("<?end for-each?>", 4), ci[8], align="center"),
    ]))
    p.append(row([
        cell(value("TOTAL_PALLETS", 15), ci[0], align="center", shade=LIGHT_BG),
        cell(t("PLT", 15), ci[1], align="center", shade=LIGHT_BG),
        cell(value("TOTAL_PIECES", 15), ci[2], align="center", shade=LIGHT_BG),
        cell(t("TIRES", 15), ci[3], align="center", shade=LIGHT_BG),
        cell(value("TOTAL_WEIGHT", 15), ci[4], align="right", shade=LIGHT_BG),
        cell("", ci[5], shade=LIGHT_BG),
        cell(t("GRAND TOTAL", 15, bold=True), ci[6], shade=LIGHT_BG),
        cell("", ci[7] + ci[8], shade=LIGHT_BG),
    ]))

    # --- declared value / COD, liability note, receipt terms
    p.append(row([
        cell(t("Where the rate is dependent on value, shippers are required to state specifically in writing "
               "the agreed or declared value of the property as follows: The agreed or declared value of the "
               "property is specifically stated by the shipper to be not exceeding ________ per ________.", 13),
             6600),
        cell(label("COD Amount: $ ____________") + L
             + t("Fee Terms:  Collect [  ]   Prepaid [  ]", 14) + L
             + t("Customer check acceptable: [  ]", 14), USABLE - 6600),
    ]))
    p.append(row([cell(
        t("NOTE", 14, bold=True) + t("  Liability limitation for loss or damage in this shipment may be applicable. "
                                     "See 49 U.S.C. 14706(c)(1)(A) and (B).", 14), USABLE)]))
    p.append(row([cell(
        t("RECEIVED, subject to individually determined rates or contracts that have been agreed upon in writing "
          "between the carrier and shipper, if applicable, otherwise to the rates, classifications and rules that "
          "have been established by the carrier and are available to the shipper, on request, and to all applicable "
          "state and federal regulations.", 13), 6600),
        cell(t("The carrier shall not make delivery of this shipment without payment of charges and all other "
               "lawful fees.", 13) + L + L + label("Shipper Signature ____________________"), USABLE - 6600),
    ]))

    # --- signature block
    s = [3900, 1600, 1900, USABLE - 3900 - 1600 - 1900]
    p.append(row([
        cell(t("SHIPPER SIGNATURE / DATE", 14, bold=True) + L + L + t("______________________________", 14) + L
             + t("This is to certify that the above named materials are properly classified, packaged, marked "
                 "and labeled, and are in proper condition for transportation according to the applicable "
                 "regulations of the DOT.", 12), s[0]),
        cell(t("Trailer Loaded:", 14, bold=True) + L + value("BOX_LOADED_SHIPPER", 14) + t(" By Shipper", 14) + L
             + value("BOX_LOADED_DRIVER", 14) + t(" By Driver", 14), s[1]),
        cell(t("Freight Counted:", 14, bold=True) + L + value("BOX_COUNTED_SHIPPER", 14) + t(" By Shipper", 14) + L
             + value("BOX_COUNTED_DRV_PALLETS", 14) + t(" By Driver/pallets said to contain", 14) + L
             + value("BOX_COUNTED_DRV_PIECES", 14) + t(" By Driver/Pieces", 14), s[2]),
        cell(t("CARRIER SIGNATURE / PICKUP DATE", 14, bold=True) + L + L + t("______________________________", 14) + L
             + t("Carrier acknowledges receipt of packages and required placards. Carrier certifies emergency "
                 "response information was made available and/or carrier has the DOT emergency response "
                 "guidebook or equivalent documentation in the vehicle. Property described above is received in "
                 "good order, except as noted.", 12), s[3]),
    ], height=1500))
    p.append(para(t("Synthetic lab data: Hello World Tire is demo branding; all parties, numbers and addresses "
                    "are fictional. Rendered by the BI Publisher engine from Db2.", 12, color=SLATE, italic=True)))
    p.append("}")
    return "\n".join(p)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="ascii")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
