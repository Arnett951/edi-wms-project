// Power BI Desktop > Get data > Blank query > Advanced Editor. Paste one query each.
// Auth: Microsoft account (your Entra user) for the Azure SQL source.
// Both steps fold to SQL (check: right-click the last step > View Native Query).

// ---- Query 1: InventoryAging (fact, lot level, all facilities) ----
let
    Source = Sql.Database("sql-lab-data-eng-baby.database.windows.net", "free-sql-db-5402162"),
    Aging = Source{[Schema = "wmslab", Item = "vw_InventoryAging"]}[Data],
    Typed = Table.TransformColumnTypes(Aging, {
        {"WAREHOUSE_CODE", type text}, {"WAREHOUSE_NAME", type text},
        {"SKU", type text}, {"DESCRIPTION", type text}, {"TIRE_SIZE", type text},
        {"LOCATION_CODE", type text}, {"ZONE", type text}, {"LOT_NUMBER", type text},
        {"DOT_CODE", type text}, {"MFG_WEEK", Int64.Type}, {"MFG_YEAR", Int64.Type},
        {"MFG_DATE", type date}, {"RECEIVED_DATE", type date}, {"OLDEST_RECEIVED_DATE", type date},
        {"WAREHOUSE_AGE_DAYS", Int64.Type}, {"TIRE_AGE_DAYS", Int64.Type},
        {"STOCK_STATUS", type text}, {"ON_HAND_QTY", Int64.Type}, {"RESERVED_QTY", Int64.Type},
        {"AVAILABLE_QTY", Int64.Type}, {"INVENTORY_VALUE", Currency.Type}
    })
in
    Typed

// ---- Query 2: LoadInfo (one row: when the Db2 copy last ran) ----
let
    Source = Sql.Database("sql-lab-data-eng-baby.database.windows.net", "free-sql-db-5402162"),
    Log = Source{[Schema = "wmslab", Item = "LOAD_LOG"]}[Data],
    Latest = Table.FirstN(Table.Sort(Log, {{"LOADED_AT", Order.Descending}}), 1),
    Kept = Table.SelectColumns(Latest, {"LOADED_AT", "SOURCE", "ROW_COUNTS"}),
    Typed = Table.TransformColumnTypes(Kept, {{"LOADED_AT", type datetime}})
in
    Typed
