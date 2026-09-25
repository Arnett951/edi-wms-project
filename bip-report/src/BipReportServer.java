import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import oracle.xdo.template.FOProcessor;
import oracle.xdo.template.RTFProcessor;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Types;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Live BI Publisher reports for the synthetic Db2 tire-distribution lab.
 *
 * Reports are folders under REPORTS_DIR (default /app/reports, mounted from the host),
 * so adding one means dropping in a folder -- no rebuild, no restart:
 *
 *   reports/<id>/report.json    title, description, order, sources, options
 *   reports/<id>/<dataset>.sql  one SELECT; :P_FACILITY is bound to the chosen facility
 *   reports/<id>/template.rtf   BI Publisher RTF layout (Template Builder for Word)
 *
 * Per request: run the source's SQL, write the rows as <DATA>/<DATA_RECORD> XML (the
 * shape Template Builder's sample XML uses), and render the RTF to PDF with the BI
 * Publisher core engine -- RTFProcessor compiles the RTF to XSL-FO (recompiled whenever
 * the file changes), FOProcessor merges XML into it.
 *
 * Routes: GET /health
 *         GET /facilities                          facilities from WMS.WAREHOUSE
 *         GET /reports                             the registry, for the report picker
 *         GET /report.pdf?report=ID&facility=CODE[&source=ID]
 */
public class BipReportServer {

    private static final String FACILITIES_SQL =
        "SELECT WAREHOUSE_CODE, WAREHOUSE_NAME FROM WMS.WAREHOUSE ORDER BY WAREHOUSE_CODE WITH UR";

    private static final Pattern REPORT_ID = Pattern.compile("[a-z0-9][a-z0-9-]{0,39}");
    private static final Pattern SOURCE_ID = Pattern.compile("[a-z0-9-]{1,20}");
    private static final Pattern BIND_PARAM = Pattern.compile(":P_[A-Z0-9_]+");
    private static final String DEFAULT_REPORT = "inventory-aging";

    // Re-rendering the same report/source/facility within this window returns the last PDF.
    private static final long PDF_CACHE_MS = 60_000;

    private static String dbUrl;
    private static String dbUser;
    private static String dbPassword;
    private static File reportsDir;
    private static final Gson GSON = new Gson();

    private static final Map<String, byte[]> pdfCache = new HashMap<>();
    private static final Map<String, Long> pdfCacheAt = new HashMap<>();
    // report id -> compiled XSL path and the template mtime it was compiled from
    private static final Map<String, String> xslByReport = new HashMap<>();
    private static final Map<String, Long> xslCompiledFrom = new HashMap<>();

    public static void main(String[] args) throws Exception {
        dbUrl = env("DB2_URL", "jdbc:db2://100.123.161.53:50000/TIREWMS");
        dbUser = env("DB2_USER", null);
        dbPassword = env("DB2_PASSWORD", null);
        reportsDir = new File(env("REPORTS_DIR", "/app/reports"));
        int port = Integer.parseInt(env("PORT", "8790"));

        // Compile every template up front so broken ones show in the startup log.
        for (JsonObject r : listReports()) {
            try {
                compiledXsl(r.get("id").getAsString());
            } catch (Exception e) {
                log("template compile failed for " + r.get("id").getAsString() + ": " + e);
            }
        }

        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/health", ex -> send(ex, 200, "application/json", "{\"status\":\"ok\"}".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/facilities", BipReportServer::handleFacilities);
        server.createContext("/reports", BipReportServer::handleReports);
        server.createContext("/report.pdf", BipReportServer::handleReport);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();
        log("listening on :" + port + ", reports from " + reportsDir);
    }

    // ------------------------------------------------------------------ registry

    /** Every valid report folder, sorted by "order" then title. Read fresh on each call. */
    private static List<JsonObject> listReports() {
        List<JsonObject> out = new ArrayList<>();
        File[] dirs = reportsDir.listFiles(File::isDirectory);
        if (dirs == null) return out;
        for (File dir : dirs) {
            if (!REPORT_ID.matcher(dir.getName()).matches()) continue;
            try {
                out.add(loadReport(dir.getName()));
            } catch (Exception e) {
                log("skipping report folder " + dir.getName() + ": " + e.getMessage());
            }
        }
        out.sort((a, b) -> {
            int c = Integer.compare(intOr(a, "order", 100), intOr(b, "order", 100));
            return c != 0 ? c : a.get("title").getAsString().compareToIgnoreCase(b.get("title").getAsString());
        });
        return out;
    }

    /** report.json plus its id, validated: needs a title, a template and at least one source. */
    private static JsonObject loadReport(String id) throws IOException {
        if (!REPORT_ID.matcher(id).matches()) throw new IOException("invalid report id");
        File dir = new File(reportsDir, id);
        File json = new File(dir, "report.json");
        if (!json.isFile()) throw new IOException("no report.json");
        JsonObject r = GSON.fromJson(new String(Files.readAllBytes(json.toPath()), StandardCharsets.UTF_8), JsonObject.class);
        r.addProperty("id", id);
        if (!r.has("title")) throw new IOException("report.json needs a title");
        if (!r.has("template")) r.addProperty("template", "template.rtf");
        if (!new File(dir, r.get("template").getAsString()).isFile()) throw new IOException("template file missing");
        if (!r.has("sources") || r.getAsJsonArray("sources").size() == 0) throw new IOException("report.json needs sources");
        for (JsonElement s : r.getAsJsonArray("sources")) {
            JsonObject src = s.getAsJsonObject();
            if (!src.has("id") || !SOURCE_ID.matcher(src.get("id").getAsString()).matches()) throw new IOException("bad source id");
            if (!src.has("sql") || !new File(dir, src.get("sql").getAsString()).isFile()) throw new IOException("source SQL file missing");
        }
        return r;
    }

    /** Compiled XSL-FO for a report, recompiled whenever its RTF changes on disk. */
    private static synchronized String compiledXsl(String id) throws Exception {
        String override = env("TEMPLATE_XSL_" + id.toUpperCase().replace('-', '_'), null);
        if (override != null) return override; // hand-edited XSL-FO, for layout debugging

        JsonObject r = loadReport(id);
        File rtf = new File(new File(reportsDir, id), r.get("template").getAsString());
        long mtime = rtf.lastModified();
        Long compiledFrom = xslCompiledFrom.get(id);
        if (compiledFrom != null && compiledFrom == mtime) return xslByReport.get(id);

        File xslDir = new File("/tmp/xsl");
        xslDir.mkdirs();
        String xslPath = new File(xslDir, id + ".xsl").getPath();
        RTFProcessor proc = new RTFProcessor(rtf.getPath());
        proc.setOutput(xslPath);
        proc.process();
        log("compiled " + id + "/" + rtf.getName() + " -> " + xslPath);
        if (r.has("keepGroupHeaders") && r.get("keepGroupHeaders").getAsBoolean()) {
            keepGroupHeadersWithRows(xslPath);
        }
        xslByReport.put(id, xslPath);
        xslCompiledFrom.put(id, mtime);
        return xslPath;
    }

    /**
     * Stops a group's header from being stranded at the bottom of a page.
     *
     * Opt in per report with "keepGroupHeaders": true. For templates with "Keep with
     * next" on every paragraph (including the detail row), every group chains to the
     * next one and the engine can't honor any of the keeps. This strips them and puts
     * keep-with-next only on the first group table's header rows (the rows before the
     * current-group() detail loop): the header stays with its first row, and the group
     * can still break between rows. Equivalent to setting it in Word on just the group
     * header rows.
     */
    private static void keepGroupHeadersWithRows(String path) throws IOException {
        Path file = Paths.get(path);
        String xsl = new String(Files.readAllBytes(file), StandardCharsets.UTF_8);
        String stripped = xsl.replaceAll("\\s*keep-with-next(\\.within-page)?=\"always\"", "");

        int group = stripped.indexOf("<xsl:for-each-group");
        int table = group < 0 ? -1 : stripped.indexOf("<fo:table ", group);
        int detail = table < 0 ? -1 : stripped.indexOf("<xsl:for-each select=\"current-group()\"", table);
        if (detail < 0) {
            log("keepGroupHeaders: group table / detail loop not found; XSL left unchanged");
            return;
        }
        String headerRows = stripped.substring(table, detail)
            .replace("<fo:table-row ", "<fo:table-row keep-with-next.within-page=\"always\" ");
        int kept = headerRows.split("keep-with-next", -1).length - 1;
        Files.write(file, (stripped.substring(0, table) + headerRows + stripped.substring(detail))
            .getBytes(StandardCharsets.UTF_8));
        log("keepGroupHeaders: keep-with-next on " + kept + " group header rows");
    }

    // ------------------------------------------------------------------ routes

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
            sendError(ex, 502, "Database unavailable");
        }
    }

    /** Public view of the registry: no file names, just what the picker needs. */
    private static void handleReports(HttpExchange ex) throws IOException {
        JsonArray out = new JsonArray();
        for (JsonObject r : listReports()) {
            JsonObject pub = new JsonObject();
            pub.addProperty("id", r.get("id").getAsString());
            pub.addProperty("title", r.get("title").getAsString());
            pub.addProperty("description", r.has("description") ? r.get("description").getAsString() : "");
            JsonArray sources = new JsonArray();
            for (JsonElement s : r.getAsJsonArray("sources")) {
                JsonObject src = s.getAsJsonObject();
                JsonObject p = new JsonObject();
                p.addProperty("id", src.get("id").getAsString());
                p.addProperty("label", src.has("label") ? src.get("label").getAsString() : src.get("id").getAsString());
                p.addProperty("note", src.has("note") ? src.get("note").getAsString() : "");
                sources.add(p);
            }
            pub.add("sources", sources);
            out.add(pub);
        }
        send(ex, 200, "application/json", GSON.toJson(out).getBytes(StandardCharsets.UTF_8));
    }

    private static void handleReport(HttpExchange ex) throws IOException {
        String reportId = orDefault(queryParam(ex, "report"), DEFAULT_REPORT);
        String facility = queryParam(ex, "facility");
        String sourceId = queryParam(ex, "source");
        try {
            JsonObject report;
            try {
                report = loadReport(reportId);
            } catch (IOException e) {
                sendError(ex, 400, "Unknown report");
                return;
            }
            JsonObject source = findSource(report, sourceId);
            if (source == null) {
                sendError(ex, 400, "Unknown source");
                return;
            }
            // Only codes that exist in WMS.WAREHOUSE are accepted.
            if (facility == null || !loadFacilities().containsKey(facility)) {
                sendError(ex, 400, "Unknown facility");
                return;
            }
            byte[] pdf = renderCached(reportId, source, facility);
            String suffix = source == report.getAsJsonArray("sources").get(0).getAsJsonObject()
                ? "" : "-" + source.get("id").getAsString();
            ex.getResponseHeaders().set("Content-Disposition",
                "inline; filename=\"" + reportId + "-" + facility + suffix + ".pdf\"");
            send(ex, 200, "application/pdf", pdf);
        } catch (Exception e) {
            log("report failed for " + reportId + "/" + facility + ": " + e);
            sendError(ex, 502, "Report generation failed");
        }
    }

    /** The requested source, or the report's first (default) source when none is given. */
    private static JsonObject findSource(JsonObject report, String sourceId) {
        JsonArray sources = report.getAsJsonArray("sources");
        if (sourceId == null) return sources.get(0).getAsJsonObject();
        for (JsonElement s : sources) {
            if (s.getAsJsonObject().get("id").getAsString().equals(sourceId)) return s.getAsJsonObject();
        }
        return null;
    }

    // ------------------------------------------------------------------ rendering

    private static synchronized byte[] renderCached(String reportId, JsonObject source, String facility) throws Exception {
        String sqlFile = source.get("sql").getAsString();
        String xslPath = compiledXsl(reportId);
        File sqlPath = new File(new File(reportsDir, reportId), sqlFile);
        // Template and SQL modification times are part of the key, so an edited report
        // renders fresh immediately instead of serving the cached PDF.
        String key = reportId + "|" + source.get("id").getAsString() + "|" + facility
            + "|" + xslCompiledFrom.get(reportId) + "|" + sqlPath.lastModified();
        Long at = pdfCacheAt.get(key);
        if (at != null && System.currentTimeMillis() - at < PDF_CACHE_MS) return pdfCache.get(key);

        long start = System.currentTimeMillis();
        String sql = new String(Files.readAllBytes(sqlPath.toPath()), StandardCharsets.UTF_8);
        byte[] xml = buildXml(sql, facility);
        ByteArrayOutputStream pdf = new ByteArrayOutputStream();
        FOProcessor fo = new FOProcessor();
        fo.setData(new ByteArrayInputStream(xml));
        fo.setTemplate(xslPath);
        fo.setOutput(pdf);
        fo.setOutputFormat(FOProcessor.FORMAT_PDF);
        fo.generate();

        byte[] bytes = pdf.toByteArray();
        String prefix = reportId + "|" + source.get("id").getAsString() + "|" + facility + "|";
        pdfCache.keySet().removeIf(k -> k.startsWith(prefix));   // drop renders of older versions
        pdfCacheAt.keySet().removeIf(k -> k.startsWith(prefix));
        pdfCache.put(key, bytes);
        pdfCacheAt.put(key, System.currentTimeMillis());
        log("rendered " + key + " (" + xml.length + " B xml -> " + bytes.length + " B pdf) in "
            + (System.currentTimeMillis() - start) + " ms");
        return bytes;
    }

    /**
     * Runs a report's SQL and writes <DATA>/<DATA_RECORD> XML, one element per column
     * (null columns are omitted), matching Template Builder's sample XML.
     *
     * The SQL file is written the way a BI Publisher data model is: one SELECT, with
     * :P_FACILITY bind variables. Each is bound to the chosen facility. Comment-only
     * lines and a trailing ';' are dropped so a file pasted from DBeaver works as-is.
     */
    private static byte[] buildXml(String sqlText, String facility) throws Exception {
        StringBuilder sql = new StringBuilder();
        for (String line : sqlText.split("\\r?\\n")) {
            if (!line.trim().startsWith("--")) sql.append(line).append('\n');
        }
        String statement = sql.toString().trim();
        if (statement.endsWith(";")) statement = statement.substring(0, statement.length() - 1);

        List<String> binds = new ArrayList<>();
        Matcher m = BIND_PARAM.matcher(statement);
        StringBuffer jdbcSql = new StringBuffer();
        while (m.find()) {
            if (!m.group().equals(":P_FACILITY")) throw new IOException("unsupported bind variable " + m.group());
            binds.add(facility);
            m.appendReplacement(jdbcSql, "?");
        }
        m.appendTail(jdbcSql);

        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<DATA>\n");
        try (Connection c = connect(); PreparedStatement ps = c.prepareStatement(jdbcSql.toString())) {
            for (int i = 0; i < binds.size(); i++) ps.setString(i + 1, binds.get(i));
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

    // ------------------------------------------------------------------ helpers

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

    private static void sendError(HttpExchange ex, int status, String detail) throws IOException {
        send(ex, status, "application/json", ("{\"detail\":\"" + jsonEscape(detail) + "\"}").getBytes(StandardCharsets.UTF_8));
    }

    private static void send(HttpExchange ex, int status, String type, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.getResponseHeaders().set("Cache-Control", "no-store");
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(body);
        }
    }

    private static int intOr(JsonObject o, String key, int fallback) {
        return o.has(key) ? o.get(key).getAsInt() : fallback;
    }

    private static String orDefault(String v, String fallback) {
        return v == null || v.isEmpty() ? fallback : v;
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
