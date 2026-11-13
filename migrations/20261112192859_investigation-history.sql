CREATE TABLE public.investigation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL DEFAULT auth.uid()
        REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'error')),
    phase TEXT NOT NULL DEFAULT 'starting'
        CHECK (phase IN (
            'starting',
            'checking_pods',
            'reading_logs',
            'analyzing_events',
            'checking_networking',
            'inspecting_deployments',
            'ai_reasoning',
            'root_cause_found',
            'failed'
        )),
    root_cause TEXT,
    namespace TEXT,
    confidence INTEGER CHECK (confidence BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX investigation_history_user_created_idx
    ON public.investigation_history (user_id, created_at DESC);

ALTER TABLE public.investigation_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY investigation_history_select_own
    ON public.investigation_history
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY investigation_history_insert_own
    ON public.investigation_history
    FOR INSERT TO authenticated
    WITH CHECK (
        user_id = (SELECT auth.uid())
        AND status = 'running'
        AND phase = 'starting'
    );

CREATE POLICY investigation_history_update_own
    ON public.investigation_history
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

REVOKE ALL ON TABLE public.investigation_history FROM anon, authenticated;
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.investigation_history TO authenticated;

INSERT INTO realtime.channels (pattern, description, enabled)
VALUES (
    'investigation-history:%',
    'Per-user Kubernetes investigation progress and history',
    TRUE
)
ON CONFLICT (pattern) DO UPDATE
SET description = EXCLUDED.description,
    enabled = EXCLUDED.enabled;

ALTER TABLE realtime.channels ENABLE ROW LEVEL SECURITY;

CREATE POLICY investigation_history_channel_select_own
    ON realtime.channels
    FOR SELECT TO authenticated
    USING (
        pattern = 'investigation-history:%'
        AND realtime.channel_name() =
            'investigation-history:' || (SELECT auth.uid())::TEXT
    );

ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY investigation_history_message_publish_own
    ON realtime.messages
    FOR INSERT TO authenticated
    WITH CHECK (
        channel_name LIKE 'investigation-history:%'
        AND split_part(channel_name, ':', 2) = (SELECT auth.uid())::TEXT
    );

CREATE OR REPLACE FUNCTION public.publish_investigation_history_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    PERFORM realtime.publish(
        'investigation-history:' || NEW.user_id::TEXT,
        'investigation_updated',
        jsonb_build_object(
            'id', NEW.id,
            'status', NEW.status,
            'phase', NEW.phase,
            'root_cause', NEW.root_cause,
            'namespace', NEW.namespace,
            'confidence', NEW.confidence,
            'created_at', NEW.created_at
        )
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER investigation_history_publish_insert
    AFTER INSERT ON public.investigation_history
    FOR EACH ROW
    EXECUTE FUNCTION public.publish_investigation_history_update();

CREATE TRIGGER investigation_history_publish_update
    AFTER UPDATE OF status, phase, root_cause, namespace, confidence
    ON public.investigation_history
    FOR EACH ROW
    WHEN (
        OLD.status IS DISTINCT FROM NEW.status
        OR OLD.phase IS DISTINCT FROM NEW.phase
        OR OLD.root_cause IS DISTINCT FROM NEW.root_cause
        OR OLD.namespace IS DISTINCT FROM NEW.namespace
        OR OLD.confidence IS DISTINCT FROM NEW.confidence
    )
    EXECUTE FUNCTION public.publish_investigation_history_update();