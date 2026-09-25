# bip-report: live Db2 + BI Publisher report service

Backs the **Run it live** panel on the dashboard's *Operational Reporting* tab.
It runs on Skynet (home lab, Docker) next to the `dhl-db2` container and is
reachable only on the tailnet IP.

```
Browser ──► ediwms-api  /api/public/bi-report/{facilities,pdf}
              │  (public, facility-validated, 10 PDFs / 5 min per client)
              ▼  tailscale sidecar, socks5h://localhost:1055
            Skynet 100.123.161.53:8790  bip-report (this service)
              │  JDBC, read-only user RPTVIEW
              ▼
            dhl-db2  TIREWMS (synthetic tire-distribution WMS schema)
```

Per request it:

1. Runs the lot-level Inventory Aging dataset query (the same SQL behind the
   Template Builder `Inventory.xml` sample), filtered to one `WAREHOUSE_CODE`.
2. Writes the rows as the `<DATA>/<DATA_RECORD>` XML that `WAREHOUSE.rtf` binds to.
3. Renders the RTF to PDF with the BI Publisher core engine (`RTFProcessor` compiles the
   RTF to XSL-FO once at startup; `FOProcessor` merges XML to PDF per request).
   This is the same path Template Builder for Word uses for its local preview.

Renders take about 1–2 s. The same facility is served from a 60-second cache.

## What isn't in git

| Path on Skynet | Source |
| --- | --- |
| `vendor/*.jar` (22 jars) | BI Publisher Desktop: `Template Builder for Word\jlib\` (all jars in `RTF2PDFv2.jar`'s manifest Class-Path), plus `db2jcc4.jar` from `docker cp dhl-db2:/opt/ibm/db2/V12.1/java/db2jcc4.jar` |
| `template/WAREHOUSE.rtf` | `Desktop\O_BI\WAREHOUSE.rtf` |
| `.env` (mode 600) | `DB2_USER=rptview`, `DB2_PASSWORD=<generated on Skynet>` |

The BI Publisher jars come from Oracle's free BI Publisher Desktop download. This is a personal dev/demo lab, not a production deployment.

`RPTVIEW` is an OS user inside the `dhl-db2` container. It has `CONNECT` plus `SELECT` on
`WMS.INVENTORY`, `ITEM`, `LOCATION`, `WAREHOUSE` and `LOT_ATTRIBUTE` only. The OS user lives in the
container's writable layer, so if `dhl-db2` is ever **recreated** (not just restarted), re-run:

```bash
PW=$(grep ^DB2_PASSWORD= ~/bip-report/.env | cut -d= -f2)
docker exec dhl-db2 useradd -M -s /sbin/nologin rptview
printf "rptview:%s\n" "$PW" | docker exec -i dhl-db2 chpasswd
```

(The Db2 grants live in the database volume and survive.)

## Updating the template

After editing the template in Word, save and close Word, then copy it over. Whatever the local
filename is, it must land on Skynet as `template/WAREHOUSE.rtf`:

```bash
scp "C:/Users/chich/OneDrive/Desktop/O_BI/WAREHOUSE_Fix_loop.rtf" skynet:~/bip-report/template/WAREHOUSE.rtf
ssh skynet 'cd ~/bip-report && docker build -q -t bip-report:latest . && docker rm -f bip-report && docker run -d --name bip-report --restart unless-stopped --env-file .env -p 100.123.161.53:8790:8790 bip-report:latest'
ssh skynet 'docker logs bip-report 2>&1 | grep -E "SEVERE|compiled"'   # template compile errors show here
```

To test a template without touching the live container, run a second one on another port with
the RTF mounted over `TEMPLATE_RTF`. Set `TEMPLATE_XSL` to skip RTF compilation and render a
hand-edited XSL-FO instead; that's useful for isolating pagination and keep issues.

## Routes

- `GET /health`
- `GET /facilities`: `[{"code":"DEMO-EAST","name":"..."}, ...]` from `WMS.WAREHOUSE`
- `GET /report.pdf?facility=DEMO-EAST`: `application/pdf`. Unknown codes return 400.

## API configuration

`ediwms-api` needs `BI_REPORT_BASE_URL=http://100.123.161.53:8790`. The Container App's
`LOCAL_MODEL_SOCKS5_PROXY` (the tailscale sidecar) is reused for the hop. For local dev on a
tailnet machine, put the same `BI_REPORT_BASE_URL` in `api/.env`; no proxy is needed.
