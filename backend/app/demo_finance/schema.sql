-- Synthetic finance only. Safe to install in a dedicated database: no DROP, TRUNCATE or DELETE.
CREATE SCHEMA IF NOT EXISTS demo_finance;

CREATE TABLE IF NOT EXISTS demo_finance.dataset (
    dataset_id text PRIMARY KEY,
    version text NOT NULL,
    company_name_fa text NOT NULL,
    synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
    base_unit text NOT NULL CHECK (base_unit = 'TOMAN_SYNTHETIC'),
    seed_sha256 char(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_finance.category (
    category_id text PRIMARY KEY,
    bucket text NOT NULL CHECK (bucket IN ('REVENUE', 'COGS', 'OPEX')),
    name_fa text NOT NULL,
    UNIQUE (category_id, bucket)
);

CREATE TABLE IF NOT EXISTS demo_finance.cost_center (
    cost_center_id text PRIMARY KEY,
    name_fa text NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_finance.period_coverage (
    dataset_id text NOT NULL REFERENCES demo_finance.dataset(dataset_id),
    month_start date NOT NULL CHECK (EXTRACT(DAY FROM month_start) = 1),
    bucket text NOT NULL CHECK (bucket IN ('REVENUE', 'COGS', 'OPEX')),
    coverage_status text NOT NULL CHECK (coverage_status IN ('complete', 'incomplete')),
    verified_at timestamptz,
    PRIMARY KEY (dataset_id, month_start, bucket),
    CHECK (coverage_status <> 'complete' OR verified_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS demo_finance.document (
    document_id text PRIMARY KEY,
    dataset_id text NOT NULL REFERENCES demo_finance.dataset(dataset_id),
    kind text NOT NULL CHECK (kind IN ('SALE', 'RETURN', 'EXPENSE', 'ADJUSTMENT')),
    status text NOT NULL CHECK (status IN ('draft', 'posted', 'cancelled')),
    occurred_at timestamptz NOT NULL,
    posted_at timestamptz,
    reason_code text,
    CHECK ((status = 'posted') = (posted_at IS NOT NULL)),
    CHECK (kind NOT IN ('RETURN', 'ADJUSTMENT') OR reason_code IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS demo_finance.line (
    line_id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES demo_finance.document(document_id),
    line_no integer NOT NULL CHECK (line_no > 0),
    bucket text NOT NULL CHECK (bucket IN ('REVENUE', 'COGS', 'OPEX')),
    category_id text NOT NULL,
    cost_center_id text NOT NULL REFERENCES demo_finance.cost_center(cost_center_id),
    amount_toman numeric(22, 0) NOT NULL CHECK (amount_toman <> 0),
    item_key text,
    quantity_delta numeric(18, 0),
    unit_amount_toman numeric(22, 0),
    source_line_id text REFERENCES demo_finance.line(line_id),
    UNIQUE (document_id, line_no),
    FOREIGN KEY (category_id, bucket) REFERENCES demo_finance.category(category_id, bucket),
    CHECK (
        (quantity_delta IS NULL AND unit_amount_toman IS NULL)
        OR (
            quantity_delta IS NOT NULL AND quantity_delta <> 0
            AND unit_amount_toman IS NOT NULL AND unit_amount_toman > 0
            AND amount_toman = quantity_delta * unit_amount_toman
            AND item_key IS NOT NULL
            AND bucket IN ('REVENUE', 'COGS')
        )
    ),
    CHECK (bucket <> 'OPEX' OR quantity_delta IS NULL)
);

CREATE INDEX IF NOT EXISTS finance_document_period_idx
    ON demo_finance.document(dataset_id, posted_at) WHERE status = 'posted';
CREATE INDEX IF NOT EXISTS finance_line_document_idx
    ON demo_finance.line(document_id, bucket, category_id, cost_center_id);
CREATE INDEX IF NOT EXISTS finance_line_source_idx
    ON demo_finance.line(source_line_id) WHERE source_line_id IS NOT NULL;

CREATE OR REPLACE FUNCTION demo_finance.guard_line() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_kind text;
    parent_status text;
    parent_dataset text;
    source_row record;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT status INTO parent_status
        FROM demo_finance.document WHERE document_id = OLD.document_id FOR UPDATE;
        IF parent_status = 'posted' THEN
            RAISE EXCEPTION 'posted finance lines are immutable' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        IF NEW.line_id <> OLD.line_id OR NEW.document_id <> OLD.document_id THEN
            RAISE EXCEPTION 'line identity and parent are immutable' USING ERRCODE = '23514';
        END IF;
    END IF;

    SELECT kind, status, dataset_id INTO parent_kind, parent_status, parent_dataset
    FROM demo_finance.document WHERE document_id = NEW.document_id FOR UPDATE;
    IF parent_status <> 'draft' THEN
        RAISE EXCEPTION 'finance lines can only be edited in a draft document' USING ERRCODE = '23514';
    END IF;

    IF parent_kind = 'SALE' THEN
        IF NEW.bucket NOT IN ('REVENUE', 'COGS') OR NEW.quantity_delta <= 0
           OR NEW.quantity_delta IS NULL OR NEW.source_line_id IS NOT NULL THEN
            RAISE EXCEPTION 'sale lines require positive paired quantities' USING ERRCODE = '23514';
        END IF;
    ELSIF parent_kind = 'EXPENSE' THEN
        IF NEW.bucket <> 'OPEX' OR NEW.quantity_delta IS NOT NULL
           OR NEW.source_line_id IS NOT NULL OR NEW.amount_toman <= 0 THEN
            RAISE EXCEPTION 'expense lines require positive OPEX amounts' USING ERRCODE = '23514';
        END IF;
    ELSIF parent_kind = 'RETURN' THEN
        IF NEW.bucket NOT IN ('REVENUE', 'COGS') OR NEW.quantity_delta >= 0
           OR NEW.quantity_delta IS NULL OR NEW.source_line_id IS NULL THEN
            RAISE EXCEPTION 'return lines require negative quantities and sources' USING ERRCODE = '23514';
        END IF;
    ELSIF parent_kind = 'ADJUSTMENT' THEN
        IF NEW.quantity_delta IS NOT NULL OR NEW.unit_amount_toman IS NOT NULL
           OR NEW.source_line_id IS NULL THEN
            RAISE EXCEPTION 'adjustments are monetary deltas with sources' USING ERRCODE = '23514';
        END IF;
    END IF;

    IF NEW.source_line_id IS NOT NULL THEN
        SELECT s.bucket, s.category_id, s.cost_center_id, s.item_key,
               s.quantity_delta, s.unit_amount_toman,
               d.dataset_id, d.kind, d.status
        INTO source_row
        FROM demo_finance.line s
        JOIN demo_finance.document d ON d.document_id = s.document_id
        WHERE s.line_id = NEW.source_line_id;

        IF NOT FOUND OR source_row.dataset_id <> parent_dataset
           OR source_row.status <> 'posted' OR source_row.kind NOT IN ('SALE', 'EXPENSE')
           OR source_row.bucket <> NEW.bucket
           OR source_row.category_id <> NEW.category_id
           OR source_row.cost_center_id <> NEW.cost_center_id
           OR source_row.item_key IS DISTINCT FROM NEW.item_key THEN
            RAISE EXCEPTION 'invalid source finance line' USING ERRCODE = '23514';
        END IF;
        IF parent_kind = 'RETURN' AND (
            source_row.kind <> 'SALE'
            OR source_row.unit_amount_toman <> NEW.unit_amount_toman
        ) THEN
            RAISE EXCEPTION 'return must reverse the original unit amount' USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION demo_finance.guard_document() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    pair_row record;
    return_row record;
    original_quantity numeric;
    prior_returned numeric;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' THEN
            RAISE EXCEPTION 'finance documents must begin as drafts' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status <> 'draft' THEN
        RAISE EXCEPTION 'posted or cancelled finance documents are immutable' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NEW.document_id <> OLD.document_id OR NEW.dataset_id <> OLD.dataset_id
       OR NEW.kind <> OLD.kind OR NEW.occurred_at <> OLD.occurred_at
       OR NEW.reason_code IS DISTINCT FROM OLD.reason_code THEN
        RAISE EXCEPTION 'only draft status and posting time may change' USING ERRCODE = '23514';
    END IF;
    IF NEW.status NOT IN ('posted', 'cancelled') THEN
        RAISE EXCEPTION 'invalid document status transition' USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'cancelled' THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM demo_finance.line WHERE document_id = NEW.document_id) THEN
        RAISE EXCEPTION 'cannot post an empty finance document' USING ERRCODE = '23514';
    END IF;

    IF NEW.kind IN ('SALE', 'RETURN') THEN
        FOR pair_row IN
            SELECT item_key,
                   COUNT(*) FILTER (WHERE bucket = 'REVENUE') AS revenue_count,
                   COUNT(*) FILTER (WHERE bucket = 'COGS') AS cogs_count,
                   MAX(quantity_delta) FILTER (WHERE bucket = 'REVENUE') AS revenue_quantity,
                   MAX(quantity_delta) FILTER (WHERE bucket = 'COGS') AS cogs_quantity
            FROM demo_finance.line WHERE document_id = NEW.document_id
            GROUP BY item_key
        LOOP
            IF pair_row.revenue_count <> 1 OR pair_row.cogs_count <> 1
               OR pair_row.revenue_quantity <> pair_row.cogs_quantity THEN
                RAISE EXCEPTION 'each sale or return item requires one revenue and one COGS line'
                    USING ERRCODE = '23514';
            END IF;
        END LOOP;
    END IF;

    IF NEW.kind = 'RETURN' THEN
        FOR return_row IN
            SELECT source_line_id, SUM(-quantity_delta) AS returned_quantity
            FROM demo_finance.line WHERE document_id = NEW.document_id
            GROUP BY source_line_id
        LOOP
            SELECT quantity_delta INTO original_quantity
            FROM demo_finance.line WHERE line_id = return_row.source_line_id FOR UPDATE;
            SELECT COALESCE(SUM(-l.quantity_delta), 0) INTO prior_returned
            FROM demo_finance.line l
            JOIN demo_finance.document d ON d.document_id = l.document_id
            WHERE l.source_line_id = return_row.source_line_id
              AND d.kind = 'RETURN' AND d.status = 'posted';
            IF prior_returned + return_row.returned_quantity > original_quantity THEN
                RAISE EXCEPTION 'return quantity exceeds original sale quantity'
                    USING ERRCODE = '23514';
            END IF;
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'finance_guard_line' AND tgrelid = 'demo_finance.line'::regclass
    ) THEN
        CREATE TRIGGER finance_guard_line
        BEFORE INSERT OR UPDATE OR DELETE ON demo_finance.line
        FOR EACH ROW EXECUTE FUNCTION demo_finance.guard_line();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'finance_guard_document' AND tgrelid = 'demo_finance.document'::regclass
    ) THEN
        CREATE TRIGGER finance_guard_document
        BEFORE INSERT OR UPDATE OR DELETE ON demo_finance.document
        FOR EACH ROW EXECUTE FUNCTION demo_finance.guard_document();
    END IF;
END;
$$;
