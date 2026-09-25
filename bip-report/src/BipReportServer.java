import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import oracle.xdo.template.FOProcessor;
import oracle.xdo.template.RTFProcessor;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Types;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * Live Inventory Aging report for the synthetic Db2 tire-distribution lab.
 *
 * Runs the same lot-level dataset query the Template Builder XML export came
 * from (filtered to one facility), writes it as the <DATA>/<DATA_RECORD> XML
 * that WAREHOUSE.rtf binds to, and renders the RTF to PDF with the BI
 * Publisher core engine -- the same RTFProcessor -> FOProcessor path Template
 * Builder for Word uses for its local preview.
 *
 * Routes: GET /health, GET /facilities (JSON), GET /report.pdf?facility=CODE
 */
public class BipReportServer {

    private static final String DATASET_SQL =
        "SELECT w.WAREHOUSE_CODE, w.WAREHOUSE_NAME, i.SKU, i.DESCRIPTION, i.TIRE_SIZE,"
      + " l.LOCATION_CODE, l.ZONE, inv.LOT_NUMBER,"
      + " la.DOT_CODE, la.MFG_WEEK, la.MFG_YEAR, la.MFG_DATE, inv.RECEIVED_DATE,"
      + " DAYS(CURRENT DATE) - DAYS(inv.RECEIVED_DATE) AS WAREHOUSE_AGE_DAYS,"
      + " DAYS(CURRENT DATE) - DAYS(la.MFG_DATE) AS TIRE_AGE_DAYS,"
      + " inv.STOCK_STATUS, inv.ON_HAND_QTY, inv.RESERVED_QTY,"
      + " CASE WHEN inv.STOCK_STATUS = 'AVAILABLE' THEN inv.ON_HAND_QTY - inv.RESERVED_QTY ELSE 0 END AS AVAILABLE_QTY,"
      + " DECIMAL(inv.ON_HAND_QTY * i.UNIT_COST, 14, 2) AS INVENTORY_VALUE"
      + " FROM WMS.INVENTORY inv"
      + " JOIN WMS.ITEM i ON i.ITEM_ID = inv.ITEM_ID"
      + " JOIN WMS.LOCATION l ON l.LOCATION_ID = inv.LOCATION_ID"
      + " JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = l.WAREHOUSE_ID"
      + " LEFT JOIN WMS.LOT_ATTRIBUTE la ON la.ITEM_ID = inv.ITEM_ID AND la.LOT_NUMBER = inv.LOT_NUMBER"
      + " WHERE DAYS(CURRENT DATE) - DAYS(inv.RECEIVED_DATE) >= 7"
      + "   AND w.WAREHOUSE_CODE = ?"
      + " ORDER BY w.WAREHOUSE_CODE, i.SKU, la.MFG_DATE, inv.RECEIVED_DATE"
      + " WITH UR";

    private static final String FACILITIES_SQL =
        "SELECT WAREHOUSE_CODE, WAREHOUSE_NAME FROM WMS.WAREHOUSE ORDER BY WAREHOUSE_CODE WITH UR";

    // Re-rendering the same facility within this window just returns the last PDF.
    private static final long PDF_CACHE_MS = 60_000;

    private static String dbUrl;
    private static String dbUser;
    private static String dbPassword;
    private static String xslPath;

    private static final Map<String, byte[]> pdfCache = new LinkedHashMap<>();
    private static final Map<String, Long> pdfCacheAt = new LinkedHashMap<>();

    public static void main(String[] args) throws Exception {
        dbUrl = env("DB2_URL", "jdbc:db2://100.123.161.53:50000/TIREWMS");
        dbUser = env("DB2_USER", null);
        dbPassword = env("DB2_PASSWORD", null);
        String template = env("TEMPLATE_RTF", "/app/template/WAREHOUSE.rtf");
        int port = Integer.parseInt(env("PORT", "8790"));

        // Compile the RTF layout to XSL-FO once at startup; every request reuses it.
        // TEMPLATE_XSL skips compilation and uses a pre-built XSL-FO (for layout debugging).
        xslPath = env("TEMPLATE_XSL", null);
        if (xslPath == null) {
            xslPath = "/tmp/warehouse.xsl";
            RTFProcessor rtf = new RTFProcessor(template);
            rtf.setOutput(xslPath);
            rtf.process();
            log("compiled " + template + " -> " + xslPath);
        } else {
            log("using pre-built XSL " + xslPath);
        }

        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/health", ex -> send(ex, 200, "application/json", "{\"status\":\"ok\"}".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/facilities", BipReportServer::handleFacilities);
        server.createContext("/report.pdf", BipReportServer::handleReport);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();
        log("listening on :" + port);
    }

    private static void handleFacilities(HttpExchange ex) throws IOException {
        try {
            StringBuilder json = new StringBuilder("[");
            for (Map.Entry<String, String> f : loadFacilities().entrySet()) {
                if (json.length() > 1) json.append(',');
                json.append("{\"code\":\"").append(jsonEscape(f.getKey()))
                    .append("\",\"name\":\"").append(jsonEscape(f.getValue())).append("\"}");
            }
            json.append(']');
            send(ex, 200, "application/json", json.toString().getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log("facilities failed: " + e);
            send(ex, 502, "application/json", "{\"detail\":\"Database unavailable\"}".getBytes(StandardCharsets.UTF_8));
        }
    }

    private static void handleReport(HttpExchange ex) throws IOException {
        String facility = queryParam(ex, "facility");
        try {
            // Only codes that actually exist in WMS.WAREHOUSE are accepted.
            if (facility == null || !loadFacilities().containsKey(facility)) {
                send(ex, 400, "application/json", "{\"detail\":\"Unknown facility\"}".getBytes(StandardCharsets.UTF_8));
                return;
            }
            byte[] pdf = renderCached(facility);
            ex.getResponseHeaders().set("Content-Disposition", "inline; filename=\"inventory-aging-" + facility + ".pdf\"");
            send(ex, 200, "application/pdf", pdf);
        } catch (Exception e) {
            log("report failed for " + facility + ": " + e);
            send(ex, 502, "application/json", "{\"detail\":\"Report generation failed\"}".getBytes(StandardCharsets.UTF_8));
        }
    }

    private static synchronized byte[] renderCached(String facility) throws Exception {
        Long at = pdfCacheAt.get(facility);
        if (at != null && System.currentTimeMillis() - at < PDF_CACHE_MS) return pdfCache.get(facility);

        long start = System.currentTimeMillis();
        byte[] xml = buildXml(facility);
        ByteArrayOutputStream pdf = new ByteArrayOutputStream();
        FOProcessor fo = new FOProcessor();
        fo.setData(new ByteArrayInputStream(xml));
        fo.setTemplate(xslPath);
        fo.setOutput(pdf);
        fo.setOutputFormat(FOProcessor.FORMAT_PDF);
        fo.generate();

        byte[] bytes = pdf.toByteArray();
        pdfCache.put(facility, bytes);
        pdfCacheAt.put(facility, System.currentTimeMillis());
        log("rendered " + facility + " (" + xml.length + " B xml -> " + bytes.length + " B pdf) in "
            + (System.currentTimeMillis() - start) + " ms");
        return bytes;
    }

    /** Same element names as the Template Builder sample XML (Inventory.xml). */
    private static byte[] buildXml(String facility) throws Exception {
        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<DATA>\n");
        try (Connection c = connect(); PreparedStatement ps = c.prepareStatement(DATASET_SQL)) {
            ps.setString(1, facility);
            try (ResultSet rs = ps.executeQuery()) {
                ResultSetMetaData md = rs.getMetaData();
                while (rs.next()) {
                    xml.append("  <DATA_RECORD>\n");
                    for (int col = 1; col <= md.getColumnCount(); col++) {
                        String name = md.getColumnLabel(col);
                        String value = format(rs, col, md.getColumnType(col));
                        if (value == null) continue;
                        xml.append("    <").append(name).append('>').append(xmlEscape(value))
                           .append("</").append(name).append(">\n");
                    }
                    xml.append("  </DATA_RECORD>\n");
                }
            }
        }
        return xml.append("</DATA>\n").toString().getBytes(StandardCharsets.UTF_8);
    }

    private static String format(ResultSet rs, int col, int type) throws Exception {
        if (type == Types.DATE) {
            java.sql.Date d = rs.getDate(col);
            return d == null ? null : d.toString(); // yyyy-mm-dd, as in the sample XML
        }
        if (type == Types.DECIMAL || type == Types.NUMERIC) {
            BigDecimal b = rs.getBigDecimal(col);
            return b == null ? null : b.stripTrailingZeros().toPlainString();
        }
        String s = rs.getString(col);
        return s == null ? null : s.trim();
    }

    private static Map<String, String> loadFacilities() throws Exception {
        Map<String, String> out = new LinkedHashMap<>();
        try (Connection c = connect(); PreparedStatement ps = c.prepareStatement(FACILITIES_SQL);
             ResultSet rs = ps.executeQuery()) {
            while (rs.next()) out.put(rs.getString(1).trim(), rs.getString(2).trim());
        }
        return out;
    }

    private static Connection connect() throws Exception {
        Connection c = DriverManager.getConnection(dbUrl, dbUser, dbPassword);
        c.setReadOnly(true);
        return c;
    }

    private static String queryParam(HttpExchange ex, String key) throws IOException {
        String q = ex.getRequestURI().getRawQuery();
        if (q == null) return null;
        for (String pair : q.split("&")) {
            int i = pair.indexOf('=');
            if (i > 0 && pair.substring(0, i).equals(key)) {
                return URLDecoder.decode(pair.substring(i + 1), "UTF-8");
            }
        }
        return null;
    }

    private static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.getResponseHeaders().set("Cache-Control", "no-store");
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(body);
        }
    }

    private static String xmlEscape(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    private static String jsonEscape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String env(String key, String fallback) {
        String v = System.getenv(key);
        return v == null || v.isEmpty() ? fallback : v;
    }

    private static void log(String msg) {
        System.out.println(new java.util.Date() + " " + msg);
    }
}
