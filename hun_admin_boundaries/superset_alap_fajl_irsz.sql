-- =============================================
-- Superset Virtual Dataset: Partner Control cégek irányítószámonként
-- Chart típus: deck.gl Scatter Plot (vagy deck.gl Heatmap)
-- =============================================
-- Használat:
--   1. Futtasd a create_geo_telepules.sql-t a DB-ben (lookup tábla)
--   2. Másold be ezt a SQL-t Superset SQL Lab-ba
--   3. "Save as Dataset" -> "cegek_iranyitoszamonkent"
--   4. Új chart -> "deck.gl Scatterplot"
--      - Longitude: lon
--      - Latitude: lat
--      - Point Size: ceg_db
--      - Tooltip: irsz, telepules, megye, ceg_db
--   VAGY -> "deck.gl Heatmap" (sűrűségtérkép)
-- =============================================

SELECT
    g.lat,
    g.lon,
    g.irsz,
    g.telepules,
    g.megye,
    a.ceg_db,
    a.aktiv_ceg_db
FROM (
    SELECT
        bejegyzett_cim_irsz AS irsz,
        COUNT(*) AS ceg_db,
        SUM(CASE WHEN ceg_allapota = '0' THEN 1 ELSE 0 END) AS aktiv_ceg_db
    FROM [PARTNER_CONTROL_RAW_P].[dbo].[alap_fajl]
    WHERE bejegyzett_cim_irsz IS NOT NULL
        AND bejegyzett_cim_irsz != ''
    GROUP BY bejegyzett_cim_irsz
) a
JOIN (
    -- Egy koordináta per irányítószám (a legnagyobb település koordinátája)
    SELECT irsz, telepules, megye, lat, lon,
        ROW_NUMBER() OVER (PARTITION BY irsz ORDER BY telepules) AS rn
    FROM [PARTNER_CONTROL_RAW_P].[dbo].[x_ih_geo_telepules]
) g ON a.irsz = g.irsz AND g.rn = 1
