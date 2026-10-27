-- Synthetic data for the answer-correctness evaluation (run_eval.py).
-- PostgreSQL. Creates schema vambery_eval; safe to re-run. No real data.
--
-- Each table hides one trap a plausible-looking query falls into:
--   invoices           a replayed OLD revision arrives last (latest-by-arrival
--                      gives 18000, latest-by-revision gives the correct 20000)
--   orders/order_items summing order totals across the item join counts every
--                      order once per item (1100 instead of 600)
--   invoice_conflicts  invoice 2 has two different amounts for the same
--                      revision; the honest answer reports the conflict

DROP SCHEMA IF EXISTS vambery_eval CASCADE;
CREATE SCHEMA vambery_eval;

CREATE TABLE vambery_eval.invoices (
    invoice_id integer NOT NULL,
    revision   integer NOT NULL,
    amount     numeric(12, 2) NOT NULL,
    loaded_at  timestamp NOT NULL
);
COMMENT ON COLUMN vambery_eval.invoices.revision IS 'Revision number; a higher revision supersedes lower ones';
COMMENT ON COLUMN vambery_eval.invoices.loaded_at IS 'When the row reached the warehouse (load order, not business order)';
INSERT INTO vambery_eval.invoices VALUES
    (1, 1, 5000, '2024-01-01 08:00'),
    (2, 1, 4000, '2024-01-01 08:00'),
    (2, 2, 5000, '2024-01-03 08:00'),
    (3, 1, 5000, '2024-01-01 08:00'),
    (3, 2, 7000, '2024-01-05 08:00'),
    (3, 1, 5000, '2024-01-10 08:00'),  -- replay of the old revision, arrives last
    (4, 1, 3000, '2024-01-02 08:00');

CREATE TABLE vambery_eval.orders (
    order_id    integer PRIMARY KEY,
    customer    text NOT NULL,
    order_total numeric(12, 2) NOT NULL
);
CREATE TABLE vambery_eval.order_items (
    order_id integer NOT NULL REFERENCES vambery_eval.orders (order_id),
    item     text NOT NULL,
    qty      integer NOT NULL
);
INSERT INTO vambery_eval.orders VALUES (1, 'Acme', 100), (2, 'Globex', 200), (3, 'Initech', 300);
INSERT INTO vambery_eval.order_items VALUES
    (1, 'bolt', 10), (1, 'nut', 10),
    (2, 'gear', 1), (2, 'belt', 2), (2, 'chain', 1),
    (3, 'motor', 1);

CREATE TABLE vambery_eval.invoice_conflicts (
    invoice_id integer NOT NULL,
    revision   integer NOT NULL,
    amount     numeric(12, 2) NOT NULL
);
INSERT INTO vambery_eval.invoice_conflicts VALUES
    (1, 1, 1000),
    (2, 1, 4000),
    (2, 2, 4000),
    (2, 2, 4500),  -- same invoice and revision, different amount
    (3, 1, 2500);
