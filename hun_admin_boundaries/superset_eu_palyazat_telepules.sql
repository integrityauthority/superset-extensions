-- =============================================
-- Superset Virtual Dataset: EU Pályázatok település szinten
-- Chart típus: deck.gl Scatter Plot
-- =============================================
-- Használat:
--   1. Futtasd a create_geo_telepules.sql-t a DB-ben (lookup tábla)
--   2. Másold be ezt a SQL-t Superset SQL Lab-ba
--   3. "Save as Dataset" -> "eu_palyazat_telepulesenkent"
--   4. Új chart -> "deck.gl Scatterplot"
--      - Longitude: lon
--      - Latitude: lat
--      - Point Size: palyazat_db vagy megitelt_mrd_ft
--      - Tooltip: telepules, megye, palyazat_db, ceg_db, megitelt_mrd_ft
-- =============================================

SELECT
    g.lat,
    g.lon,
    g.telepules,
    g.megye,
    e.palyazat_db,
    e.ceg_db,
    e.megitelt_mrd_ft
FROM (
    SELECT
        varos,
        COUNT(*) AS palyazat_db,
        COUNT(DISTINCT d_b_belso_azonosito) AS ceg_db,
        CAST(SUM(ISNULL(megitelt_osszeg, 0)) / 1000000000 AS DECIMAL(18,1)) AS megitelt_mrd_ft
    FROM [PARTNER_CONTROL_RAW_P].[dbo].[nyertes_eu_palyazatok]
    WHERE varos IS NOT NULL AND varos != ''
    GROUP BY varos
) e
JOIN (
    -- Distinct település + koordináta (egy irányítószám per település elég)
    SELECT telepules, megye, lat, lon,
        ROW_NUMBER() OVER (PARTITION BY telepules ORDER BY irsz) AS rn
    FROM [PARTNER_CONTROL_RAW_P].[dbo].[x_ih_geo_telepules]
) g ON e.varos COLLATE Latin1_General_CI_AI = g.telepules COLLATE Latin1_General_CI_AI
    AND g.rn = 1
