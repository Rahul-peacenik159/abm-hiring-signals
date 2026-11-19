-- 10_hiring_trends.sql
-- Hiring momentum per account from the shared `abm.signals` table
-- (load out/signals.jsonl each run:  bq load --source_format=NEWLINE_DELIMITED_JSON YOUR_PROJECT:abm.signals out/signals.jsonl)
-- Table schema: https://github.com/Rahul-peacenik159/abm-tech-footprint/blob/main/bigquery/00_schema.sql
-- Cheap: reads only your own signals table.

WITH roles AS (
  SELECT
    account_domain,
    category                         AS function,
    DATE_TRUNC(DATE(observed_at), WEEK(MONDAY)) AS week,
    COUNTIF(signal_type = 'new_role')        AS new_roles,
    COUNTIF(signal_type = 'leadership_hire') AS leadership_hires
  FROM `YOUR_PROJECT.abm.signals`
  WHERE pack = 'hiring-signals'
    AND observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 120 DAY)
  GROUP BY 1, 2, 3
),

trend AS (
  SELECT
    account_domain,
    function,
    SUM(IF(week >= DATE_SUB(CURRENT_DATE(), INTERVAL 28 DAY), new_roles, 0))                  AS new_roles_last_4w,
    SUM(IF(week <  DATE_SUB(CURRENT_DATE(), INTERVAL 28 DAY), new_roles, 0)) / 3              AS avg_per_4w_before,
    SUM(IF(week >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY), leadership_hires, 0))           AS leadership_hires_90d
  FROM roles
  GROUP BY 1, 2
)

SELECT
  account_domain,
  function,
  new_roles_last_4w,
  ROUND(avg_per_4w_before, 1) AS avg_per_4w_before,
  leadership_hires_90d,
  CASE
    WHEN leadership_hires_90d > 0 THEN 'new_leader_first_90_days'
    WHEN new_roles_last_4w >= 3 AND new_roles_last_4w >= 2 * GREATEST(avg_per_4w_before, 1) THEN 'team_buildout'
    WHEN new_roles_last_4w > 0 THEN 'role_based_outreach'
    ELSE ''
  END AS suggested_play
FROM trend
WHERE new_roles_last_4w > 0 OR leadership_hires_90d > 0
ORDER BY leadership_hires_90d DESC, new_roles_last_4w DESC;
