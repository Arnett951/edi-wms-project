# bip-report: live Db2 + BI Publisher report service

Backs the **Run it live** panel on the dashboard's *Operational Reporting* tab.
It runs on Skynet (home lab, Docker) next to the `dhl-db2` container and is
reachable only on the tailnet IP.

```
Browser ──► ediwms-api  /api/public/bi-report/{reports,facilities,pdf}
              │  (public, validated ids, 10 PDFs / 5 min per client)
              ▼  tailscale sidecar, socks5h://localhost:1055
            Skynet 100.123.161.53:8790  bip-report (this service)
              │  JDBC, read-only user RPTVIEW          reports/ folder (mounted)
              ▼
            dhl-db2  TIREWMS (synthetic tire-distribution WMS schema)
```

Per request it:

1. Runs the chosen report's SQL for one facility (`:P_FACILITY` bound like a BI
   Publisher data model parameter).
2. Writes the rows as `<DATA>/<DATA_RECORD>` XML, the shape Template Builder's sample XML uses.
3. Renders the report's RTF to PDF with the BI Publisher core engine: `RTFProcessor` compiles
   the RTF to XSL-FO (recompiled whenever the file changes), and `FOProcessor` merges the XML
   to PDF. This is the same path Template Builder for Word uses for its local preview.

Renders take about 1–2 s. The same report/source/facility is served from a 60-second cache,
which a changed template or SQL file bypasses.

## Reports: a folder each, no rebuild

```
reports/
  inventory-aging/     report.json  dataset.sql  dataset_legacy.sql  template.rtf
  location-heatmap/    report.json  dataset.sql  template.rtf
```

On Skynet the folder is `~/bip-report/reports`, mounted read-only into the container. The
service re-reads it on every request, so **adding or editing a report is just a file copy**:
it appears in the page's Report dropdown immediately, with no rebuild or restart.

### Adding a report

1. Write the dataset in DBeaver as **one SELECT**. Use `:P_FACILITY` wherever the facility
   code goes (as many times as needed). A trailing `;` and comment-only lines are fine; they
   are stripped. End with `WITH UR` so reports never lock warehouse transactions. Only
   `:P_FACILITY` is supported so far.
2. Export sample XML from DBeaver and build the RTF in Template Builder for Word against it.
   The column names are the XML element names.
3. Create `report.json`:

   ```json
   {
     "title": "Held & Damaged Inventory",
     "description": "One line shown under the Report dropdown.",
     "order": 30,
     "template": "template.rtf",
     "keepGroupHeaders": false,
     "sources": [
       { "id": "wms", "label": "Modern schema (WMS.*)", "sql": "dataset.sql", "note": "" }
     ]
   }
   ```

   - `order` sorts the dropdown; the folder name is the report's id (lowercase, digits, `-`).
   - `sources` lists one or more datasets for the same template. The first is the default.
     The page shows a Data source dropdown only when there's more than one.
   - `keepGroupHeaders` turns on the pagination patch below.

4. Copy the folder to Skynet, then check the compile log:

   ```bash
   scp -r bip-report/reports/held-damaged skynet:~/bip-report/reports/
   ssh skynet 'docker logs bip-report 2>&1 | grep -E "SEVERE|compiled|skipping"'
   ```

   A folder missing `report.json`, its template or a source SQL file is skipped, and the log says why.

### Updating a template

Save and close Word, then copy the RTF over the report's `template.rtf`. It recompiles on the
next request:

```bash
scp "C:/Users/chich/OneDrive/Desktop/O_BI/RTFS/WAREHOUSE_Fix_loop.rtf" skynet:~/bip-report/reports/inventory-aging/template.rtf
```

To try a template without touching the live report, put it in a new folder under another id
first. For layout debugging, `TEMPLATE_XSL_<REPORT_ID>` (e.g. `TEMPLATE_XSL_LOCATION_HEATMAP`)
renders a hand-edited XSL-FO instead of compiling the RTF.

### Pagination patch (`"keepGroupHeaders": true`)

A service-side fallback, now off for the aging report. Word's "Keep with next" doesn't work on
table rows in BI Publisher: it's applied to the paragraphs inside the cells, and the PDF engine
only honors keeps on the rows themselves. With this option the service strips those paragraph
keeps from the compiled XSL-FO and puts keep-with-next on the first group table's header rows.

The template-side fix, which the aging RTF now uses: type this at the start of the first cell of
each group header row,

    <?attribute@row:keep-with-next.within-page;'always'?>

`@row` makes BI Publisher attach the attribute to the table row. A header then always stays with
its first lot, however long the group is. To keep a whole group on one page instead (Crystal's
"keep group together"), nest the group in a one-cell outer table and turn off "Allow row to break
across pages" on that row; that only works for groups shorter than a page.

### The Location Aging Heatmap

- **Dataset (`reports/location-heatmap/dataset.sql`):** lists every rack location and floor
  area, empty ones included, and pivots each rack row (aisle + level) into bay columns
  `B01_*`..`B10_*`. It also buckets each occupied location by its oldest lot's age: the oldest
  10% red, the next 10% yellow, the rest green (10% rounded up; `RANK()`, so ties share a
  color). The percentile math lives in SQL because the template can't do it.
- **Template (`template.rtf`):** generated by `tools/build_heatmap_template.py` as a starting
  point; it can be restyled in Word afterward. Cell color is BI Publisher conditional
  formatting:
  `<?if:B01_HEAT='RED'?><?attribute@incontext:background-color;'#F4A4A4'?><?end if?>`.
- **RTF parser lessons** found while building it, all verified by compiling test files with
  the engine:
  - page size and margins are ignored unless the RTF has an `{\info}` group;
  - landscape needs Word's `\sectd\ltrsect\lndscpsxn` section syntax plus landscape
    `\paperw`/`\paperh`, not `\landscape`;
  - character formatting must be in `{...}` groups;
  - a raw `<xsl:attribute>` typed as text prints instead of running;
  - a plain `<?if?>` mid-line starts a new paragraph (use `<?if@inlines:...?>`);
  - keep-together on every row chains the whole grid onto the next page.
- **Rack data:** the grid comes from `sql/lab/01_rack_grid.sql`, which added AISLE / BAY /
  RACK_LEVEL and a 4 × 10 × 3 rack per warehouse. It relocated the floor PICK/BULK lots with
  MOVE transactions, so `V_INVENTORY_RECONCILIATION` stays at zero differences. The pre-change
  tables are backed up in schema `BAK20260925`.

### The VICS Bill of Lading

A straight BOL in the VICS (GS1 US) layout for the facility's current loaded trailer, one page.

- **Data:** `sql/lab/02_outbound_bol.sql` adds warehouse addresses, item weights and
  tires-per-pallet, the `CARRIER`, `SHIP_TO` and `SHIPMENT` tables, and one loaded trailer per
  facility (3 POs for one store). BOL numbers follow the VICS 17-digit format: GS1 company
  prefix + serial + mod-10 check digit, using GS1's documentation example prefix `0614141`.
  Everything is fictional. Pre-change tables are backed up as `BAK20260925.*_B2`.
- **Dataset (`reports/vics-bol/dataset.sql`):** `ORDER` rows (one per PO) for Customer Order
  Information and `COMMODITY` rows (one per tire category) for Carrier Information. Each row
  carries the header fields and grand totals. Pallets per line are
  `CEILING(qty / tires per pallet)`; weight is the tires plus 40 lb per pallet. Both sections
  reconcile to the same totals.
- **Template:** generated by `tools/build_bol_template.py`, and restylable in Word afterward.

#### Barcodes

The BOL and PRO numbers are Code 128 barcodes:

- **Encoding in SQL:** the dataset builds the Code 128 set B text (start B `U+00CC`, data,
  check character, stop `U+00CE`). The check value is `(104 + sum(position * (ASCII - 32))) mod 103`.
  `U&` literals keep the non-ASCII characters valid in the UTF-8 database.
- **Font:** the template draws that text in the Libre Barcode 128 font (SIL Open Font License,
  `fonts/`). `config/xdo.cfg` maps the font family to the TTF, and the service passes that
  config to the engine on every render.
- **Verified:** all four barcodes on the two BOLs decode correctly from the rendered PDF. A
  barcode needs a blank quiet zone on both sides; flush against a cell edge, it won't scan.

Adding another font works the same way: put the TTF in `fonts/`, add a `<font>` entry to
`config/xdo.cfg`, and rebuild.

## What isn't in git

| Path on Skynet | Source |
| --- | --- |
| `vendor/*.jar` (22 jars) | BI Publisher Desktop: `Template Builder for Word\jlib\` (all jars in `RTF2PDFv2.jar`'s manifest Class-Path), plus `db2jcc4.jar` from `docker cp dhl-db2:/opt/ibm/db2/V12.1/java/db2jcc4.jar` |
| `.env` (mode 600) | `DB2_USER=rptview`, `DB2_PASSWORD=<generated on Skynet>` |

The BI Publisher jars come from Oracle's free BI Publisher Desktop download. This is a personal
dev/demo lab, not a production deployment. Everything in `reports/` is in git, including both
templates. The aging RTF (~18 MB, Word-built; working copy at `Desktop\O_BI\RTFS\WAREHOUSE_Fix_loop.rtf`)
is committed because it rarely changes. Copy it into `reports/inventory-aging/template.rtf`
after an edit, so git and Skynet stay the same.

`RPTVIEW` is an OS user inside the `dhl-db2` container with `CONNECT` plus `SELECT` on the
tables the reports read (`WMS.INVENTORY`, `ITEM`, `LOCATION`, `WAREHOUSE`, `LOT_ATTRIBUTE` and
the `LGCYLIB` files). A new report reading another table needs a `GRANT SELECT ... TO USER
RPTVIEW` first. The OS user lives in the container's writable layer, so if `dhl-db2` is ever
**recreated** (not just restarted), re-run:

```bash
PW=$(grep ^DB2_PASSWORD= ~/bip-report/.env | cut -d= -f2)
docker exec dhl-db2 useradd -M -s /sbin/nologin rptview
printf "rptview:%s\n" "$PW" | docker exec -i dhl-db2 chpasswd
```

(The Db2 grants live in the database volume and survive.)

## Rebuilding the service

Only needed when `src/`, `vendor/`, `config/` or `fonts/` changes:

```bash
ssh skynet 'cd ~/bip-report && docker build -q -t bip-report:latest . && docker rm -f bip-report && docker run -d --name bip-report --restart unless-stopped --env-file .env -v ~/bip-report/reports:/app/reports:ro -p 100.123.161.53:8790:8790 bip-report:latest'
```

## Routes

- `GET /health`
- `GET /facilities`: `[{"code":"PERRIS","name":"..."}, ...]` from `WMS.WAREHOUSE`
- `GET /reports`: the registry, `[{"id","title","description","sources":[{"id","label","note"}]}]`
- `GET /report.pdf?report=ID&facility=CODE[&source=ID]`: `application/pdf`. `report` defaults
  to `inventory-aging`, `source` to the report's first. Unknown ids return 400.

## API configuration

`ediwms-api` needs `BI_REPORT_BASE_URL=http://100.123.161.53:8790`. The Container App's
`LOCAL_MODEL_SOCKS5_PROXY` (the tailscale sidecar) is reused for the hop. For local dev on a
tailnet machine, put the same `BI_REPORT_BASE_URL` in `api/.env`; no proxy is needed.
