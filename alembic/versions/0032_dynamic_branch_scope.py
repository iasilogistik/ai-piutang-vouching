"""Allow active users to have global or optionally restricted branch scope.

Revision ID: 0032_dynamic_branch_scope
Revises: 0031_revision_helper_acl
Create Date: 2026-09-25

A NULL/blank application-user branch means global access across branch-owned
resources, while a non-null branch remains an exact restriction. Role gates are
preserved from the existing policies; only branch-scope predicates are replaced.
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa

revision = "0032_dynamic_branch_scope"
down_revision = "0031_revision_helper_acl"
branch_labels = None
depends_on = None


_POLICIES = (
    ("audit_closings", "app_insert_audit_closings", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_closings", "app_read_audit_closings", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_closings", "app_update_audit_closings", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))"),
    ("audit_engagement_assignments", "app_read_audit_engagement_assignments", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_engagements e\n  WHERE ((e.id = audit_engagement_assignments.engagement_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM e.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_engagements", "app_read_audit_engagements", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_engagements", "app_update_audit_engagements", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_engagements", "auditor_insert_audit_engagements", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_exceptions", "app_insert_audit_exceptions", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_exceptions", "app_read_audit_exceptions", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_exceptions", "app_update_audit_exceptions", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))"),
    ("audit_finding_evidence", "app_read_audit_finding_evidence", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_evidence.finding_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_finding_evidence", "auditor_manage_audit_finding_evidence", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_evidence.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_evidence.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_exceptions", "app_read_audit_finding_exceptions", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_exceptions.finding_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_finding_exceptions", "auditor_manage_audit_finding_exceptions", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_exceptions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_exceptions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_samples", "app_read_audit_finding_samples", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_samples.finding_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_finding_samples", "auditor_manage_audit_finding_samples", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_samples.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_samples.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_versions", "app_manage_audit_finding_versions", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_versions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_versions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_versions", "app_read_audit_finding_versions", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_versions.finding_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_finding_working_papers", "app_read_audit_finding_working_papers", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_working_papers.finding_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_finding_working_papers", "auditor_manage_audit_finding_working_papers", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_working_papers.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_working_papers.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_findings", "app_read_audit_findings", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_findings", "auditor_reviewer_manage_audit_findings", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_populations", "app_read_audit_populations", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_populations", "auditor_manage_audit_populations", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_reports", "app_insert_audit_reports", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_reports", "app_read_audit_reports", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_reports", "app_update_audit_reports", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))"),
    ("audit_samples", "app_read_audit_samples", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_samples", "auditor_manage_audit_samples", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_trail", "app_insert_audit_trail", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_trail", "app_read_audit_trail", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_workflow_cases", "app_read_audit_workflow_cases", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_workflow_cases", "app_update_audit_workflow_cases", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_workflow_cases", "auditor_insert_audit_workflow_cases", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_working_paper_evidence", "app_read_audit_working_paper_evidence", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_evidence.working_paper_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_working_paper_evidence", "auditor_manage_audit_working_paper_evidence", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_evidence.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_evidence.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_working_paper_exceptions", "app_read_audit_working_paper_exceptions", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_exceptions.working_paper_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_working_paper_exceptions", "auditor_manage_audit_working_paper_exceptions", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_exceptions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_exceptions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_working_paper_versions", "app_manage_audit_working_paper_versions", "ALL", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_versions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_versions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_working_paper_versions", "app_read_audit_working_paper_versions", "SELECT", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_versions.working_paper_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("audit_working_papers", "app_read_audit_working_papers", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("audit_working_papers", "auditor_manage_audit_working_papers", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("billing_reconciliation", "app_read_billing_reconciliation", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (EXISTS ( SELECT 1\n   FROM (sap_billing s\n     JOIN import_batches b ON ((b.id = s.import_batch_id)))\n  WHERE ((s.id = billing_reconciliation.sap_billing_id) AND (upper(TRIM(BOTH FROM b.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("billing_reconciliation", "auditor_insert_reconciliation", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM (sap_billing s\n     JOIN import_batches b ON ((b.id = s.import_batch_id)))\n  WHERE ((s.id = billing_reconciliation.sap_billing_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM b.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("billing_reconciliation", "auditor_update_reconciliation", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM (sap_billing s\n     JOIN import_batches b ON ((b.id = s.import_batch_id)))\n  WHERE ((s.id = billing_reconciliation.sap_billing_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM b.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM (sap_billing s\n     JOIN import_batches b ON ((b.id = s.import_batch_id)))\n  WHERE ((s.id = billing_reconciliation.sap_billing_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM b.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("branches", "app_read_branches", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((active = true) AND ((branch_code)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))", None),
    ("control_evidence_detections", "app_read_control_evidence_detections", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = control_evidence_detections.document_id) AND (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("control_evidence_detections", "auditor_insert_control_evidence_detections", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = control_evidence_detections.document_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("control_evidence_detections", "auditor_update_control_evidence_detections", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = control_evidence_detections.document_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = control_evidence_detections.document_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("corrective_action_evidence", "app_manage_corrective_action_evidence", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_evidence", "app_read_corrective_action_evidence", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("corrective_action_plan_history", "app_manage_corrective_action_plan_history", "ALL", "(EXISTS ( SELECT 1\n   FROM corrective_action_plans p\n  WHERE ((p.id = corrective_action_plan_history.action_plan_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM corrective_action_plans p\n  WHERE ((p.id = corrective_action_plan_history.action_plan_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("corrective_action_plan_history", "app_read_corrective_action_plan_history", "SELECT", "(EXISTS ( SELECT 1\n   FROM corrective_action_plans p\n  WHERE ((p.id = corrective_action_plan_history.action_plan_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("corrective_action_plans", "app_manage_corrective_action_plans", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_plans", "app_read_corrective_action_plans", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("corrective_action_progress_updates", "app_manage_corrective_action_progress_updates", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_progress_updates", "app_read_corrective_action_progress_updates", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("corrective_action_verifications", "app_manage_corrective_action_verifications", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_verifications", "app_read_corrective_action_verifications", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("document_control_evidence", "app_read_document_control_evidence", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = document_control_evidence.document_id) AND (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("documents", "app_read_documents", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("documents", "auditor_insert_documents", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("evidence_resource_links", "app_read_evidence_resource_links", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("evidence_resource_links", "auditor_manage_evidence_resource_links", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("import_batches", "app_read_import_batches", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("import_batches", "auditor_insert_import_batches", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("management_response_versions", "app_manage_management_response_versions", "ALL", "(EXISTS ( SELECT 1\n   FROM management_responses p\n  WHERE ((p.id = management_response_versions.response_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM management_responses p\n  WHERE ((p.id = management_response_versions.response_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("management_response_versions", "app_read_management_response_versions", "SELECT", "(EXISTS ( SELECT 1\n   FROM management_responses p\n  WHERE ((p.id = management_response_versions.response_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("management_responses", "app_manage_management_responses", "ALL", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("management_responses", "app_read_management_responses", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("physical_billing", "app_read_physical_billing", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = physical_billing.document_id) AND (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("physical_billing", "auditor_insert_physical_billing", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = physical_billing.document_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("review_workflows", "app_insert_review_workflows", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("review_workflows", "app_read_review_workflows", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))", None),
    ("review_workflows", "app_update_review_workflows", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR ((branch)::text = (( SELECT current_app_branch() AS current_app_branch))::text))"),
    ("sap_billing", "app_read_sap_billing", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (EXISTS ( SELECT 1\n   FROM import_batches b\n  WHERE ((b.id = sap_billing.import_batch_id) AND (upper(TRIM(BOTH FROM b.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("sap_billing", "auditor_insert_sap_billing", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM import_batches b\n  WHERE ((b.id = sap_billing.import_batch_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM b.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("spj", "app_read_spj", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = spj.document_id) AND (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("spj", "auditor_insert_spj", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND (EXISTS ( SELECT 1\n   FROM documents d\n  WHERE ((d.id = spj.document_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("vouching_result", "app_read_vouching_result", "SELECT", "((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (EXISTS ( SELECT 1\n   FROM (physical_billing pb\n     JOIN documents d ON ((d.id = pb.document_id)))\n  WHERE ((pb.id = vouching_result.billing_id) AND (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", None),
    ("vouching_result", "reviewer_insert_vouching", "INSERT", None, "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND (EXISTS ( SELECT 1\n   FROM (physical_billing pb\n     JOIN documents d ON ((d.id = pb.document_id)))\n  WHERE ((pb.id = vouching_result.billing_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
    ("vouching_result", "reviewer_update_vouching", "UPDATE", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND (EXISTS ( SELECT 1\n   FROM (physical_billing pb\n     JOIN documents d ON ((d.id = pb.document_id)))\n  WHERE ((pb.id = vouching_result.billing_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND (EXISTS ( SELECT 1\n   FROM (physical_billing pb\n     JOIN documents d ON ((d.id = pb.document_id)))\n  WHERE ((pb.id = vouching_result.billing_id) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM d.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text))))))"),
)

_BRANCH_PATTERNS = (
    re.compile(
        r"\(upper\(TRIM\(BOTH FROM ([A-Za-z_][A-Za-z0-9_.]*)\)\) = "
        r"\(\( SELECT current_app_branch\(\) AS current_app_branch\)\)::text\)"
    ),
    re.compile(
        r"\(\(([A-Za-z_][A-Za-z0-9_.]*)\)::text = "
        r"\(\( SELECT current_app_branch\(\) AS current_app_branch\)\)::text\)"
    ),
)


def _supabase_rbac_available() -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text(
                """
                select
                  exists (select 1 from pg_roles where rolname='authenticated')
                  and exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='auth' and p.proname='uid'
                  )
                  and exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_role'
                  )
                  and exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_branch'
                  )
              """
            )
        ).scalar()
    )


def _replace_branch_scope(expression: str | None) -> str | None:
    if expression is None:
        return None
    result = expression
    for pattern in _BRANCH_PATTERNS:
        result = pattern.sub(r"(public.branch_scope_allows(\1))", result)
    if "current_app_branch" in result:
        raise ValueError(f"Unconverted branch predicate: {result}")
    return result


def _create_policy(
    table: str,
    policy: str,
    command: str,
    using_expr: str | None,
    check_expr: str | None,
) -> None:
    sql = [
        f'create policy "{policy}"',
        f"on public.{table} for {command.lower()} to authenticated",
    ]
    if using_expr is not None:
        sql.append(f"using ({using_expr})")
    if check_expr is not None:
        sql.append(f"with check ({check_expr})")
    op.execute("\n".join(sql))


def _drop_policy(table: str, policy: str) -> None:
    op.execute(f'drop policy if exists "{policy}" on public.{table}')


def _install_scope_helper() -> None:
    op.execute(
        """
        create or replace function public.branch_scope_allows(resource_branch text)
        returns boolean
        language sql
        stable
        security definer
        set search_path = ''
        as $function$
          select exists (
            select 1
            from public.user_roles ur
            where ur.user_id::text = (select auth.uid())::text
              and coalesce(ur.is_active, true)
              and (
                ur.branch is null
                or trim(ur.branch) = ''
                or upper(trim(ur.branch)) = upper(trim(resource_branch))
              )
          )
        $function$;
        """
    )
    op.execute("revoke all on function public.branch_scope_allows(text) from public")
    op.execute("grant execute on function public.branch_scope_allows(text) to authenticated")


def upgrade() -> None:
    if not _supabase_rbac_available():
        return

    _install_scope_helper()
    for table, policy, command, using_expr, check_expr in _POLICIES:
        _drop_policy(table, policy)
        _create_policy(
            table,
            policy,
            command,
            _replace_branch_scope(using_expr),
            _replace_branch_scope(check_expr),
        )


def downgrade() -> None:
    if not _supabase_rbac_available():
        return

    for table, policy, command, using_expr, check_expr in reversed(_POLICIES):
        _drop_policy(table, policy)
        _create_policy(table, policy, command, using_expr, check_expr)

    op.execute("drop function if exists public.branch_scope_allows(text)")
