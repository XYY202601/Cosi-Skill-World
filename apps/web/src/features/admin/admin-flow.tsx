"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { AppIcon } from "@/components/app-graphics";
import { formatTimestamp } from "@/lib/mr-ui";
import {
  readEvaluationGates,
  type EvaluationGateCheck,
  type EvaluationGatesResponse,
  type OfflineEvaluationGate,
  type OnlineEvaluationGate,
} from "@/lib/runtime-api";

function statusTone(status: string | null | undefined): "success" | "warn" | "danger" | "info" {
  switch (status) {
    case "active":
    case "promoted":
    case "pass":
      return "success";
    case "override_allowed":
    case "insufficient_data":
      return "warn";
    case "blocked":
    case "fail":
      return "danger";
    default:
      return "info";
  }
}

function statusLabel(status: string | null | undefined, t: (key: string) => unknown): string {
  switch (status) {
    case "active":
      return String(t("admin.statusActive"));
    case "promoted":
      return String(t("admin.statusPromoted"));
    case "blocked":
      return String(t("admin.statusBlocked"));
    case "override_allowed":
      return String(t("admin.statusOverrideAllowed"));
    case "pass":
      return String(t("admin.statusPass"));
    case "fail":
      return String(t("admin.statusFail"));
    case "insufficient_data":
      return String(t("admin.statusInsufficientData"));
    default:
      return String(t("admin.statusUnknown"));
  }
}

function formatRate(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

function formatMetric(value: unknown, digits = 2): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toFixed(digits);
  }
  return "-";
}

function gateCheckSummary(checks: EvaluationGateCheck[]): string {
  if (!checks.length) {
    return "0/0";
  }
  const passed = checks.filter((item) => item.passed).length;
  return `${passed}/${checks.length}`;
}

function keyValuePairs(values: Record<string, number>): string[] {
  return Object.entries(values)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}: v${value}`);
}

function countPairs(values: Record<string, number>): string[] {
  return Object.entries(values)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}: ${value}`);
}

function thresholdPairs(values: Record<string, unknown>): string[] {
  return Object.entries(values)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}: ${typeof value === "number" ? value : String(value)}`);
}

function joinOrDash(values: string[]): string {
  return values.length > 0 ? values.join(" · ") : "-";
}

function resolveCurrentOnlineGate(
  payload: EvaluationGatesResponse | null
): OnlineEvaluationGate | null {
  if (!payload) {
    return null;
  }
  const effectiveProfile = payload.rollout.effective.profile_id;
  const effectiveExperiment = payload.rollout.effective.experiment_id ?? null;
  return (
    payload.online_gates.find(
      (item) =>
        item.profile_id === effectiveProfile &&
        (item.experiment_id ?? null) === effectiveExperiment
    ) ??
    payload.online_gates.find(
      (item) => item.profile_id === effectiveProfile && (item.experiment_id ?? null) === null
    ) ??
    null
  );
}

function resolveCurrentOfflineGate(
  payload: EvaluationGatesResponse | null
): OfflineEvaluationGate | null {
  if (!payload) {
    return null;
  }
  return (
    payload.offline_gates.find(
      (item) => item.profile_id === payload.rollout.effective.profile_id
    ) ?? null
  );
}

export function AdminFlow() {
  const { t } = useTranslation();
  const [payload, setPayload] = useState<EvaluationGatesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const loadAdminData = async () => {
      setLoading(true);
      setError(null);
      try {
        const nextPayload = await readEvaluationGates();
        if (active) {
          setPayload(nextPayload);
        }
      } catch (loadError) {
        if (active) {
          setPayload(null);
          setError(loadError instanceof Error ? loadError.message : "Unknown admin loading error");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void loadAdminData();
    return () => {
      active = false;
    };
  }, []);

  const currentOfflineGate = useMemo(() => resolveCurrentOfflineGate(payload), [payload]);
  const currentOnlineGate = useMemo(() => resolveCurrentOnlineGate(payload), [payload]);

  if (loading) {
    return (
      <section className="dashboard-page">
        <div className="placeholder-block surface-card">
          <strong>{t("admin.loading")}</strong>
          <p>{t("admin.loadingDesc")}</p>
        </div>
      </section>
    );
  }

  if (!payload) {
    return (
      <section className="dashboard-page">
        {error ? <div className="error-banner">{error}</div> : null}
        <div className="placeholder-block surface-card">
          <strong>{t("admin.noData")}</strong>
          <p>{t("admin.noDataDesc")}</p>
          <div className="placeholder-actions">
            <Link className="primary-button" href="/admin">
              {t("admin.refresh")}
            </Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-page">
      <section className="hero-panel surface-card">
        <div className="hero-panel-main">
          <div className="hero-icon-tile">
            <AppIcon className="icon-xl icon-brand" name="settings" />
          </div>
          <div className="hero-panel-copy">
            <h1>{t("admin.pageTitle")}</h1>
            <p>{t("admin.pageSubtitle")}</p>
            <div className="admin-hero-meta">
              <span className="section-chip">{payload.domain_id}</span>
              <span className="section-chip">
                {t("admin.activeProfile")}: {payload.rollout.effective.profile_id}
              </span>
              <span className="section-chip">
                {t("admin.updatedAt")} {formatTimestamp(currentOnlineGate?.updated_at ?? "")}
              </span>
            </div>
          </div>
        </div>
        <Link className="primary-button hero-button" href="/admin">
          <AppIcon className="icon-sm" name="refresh" />
          <span>{t("admin.refresh")}</span>
        </Link>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="admin-summary-grid">
        <article className="admin-summary-card surface-card">
          <span>{t("admin.activeProfile")}</span>
          <strong>{payload.rollout.effective.profile_id}</strong>
          <small>
            {t("admin.requestedProfile")}: {payload.rollout.requested.profile_id}
          </small>
        </article>
        <article className={`admin-summary-card surface-card ${statusTone(payload.rollout.status)}`}>
          <span>{t("admin.rolloutDecision")}</span>
          <strong>{statusLabel(payload.rollout.status, t)}</strong>
          <small>
            {t("admin.stableProfile")}: {payload.rollout.stable_profile_id}
          </small>
        </article>
        <article className="admin-summary-card surface-card">
          <span>{t("admin.fixturePassRate")}</span>
          <strong>{formatRate(currentOfflineGate?.fixture_pass_rate)}</strong>
          <small>
            {t("admin.gateChecks")}: {gateCheckSummary(currentOfflineGate?.checks ?? [])}
          </small>
        </article>
        <article className="admin-summary-card surface-card">
          <span>{t("admin.sampleSize")}</span>
          <strong>{currentOnlineGate?.sample_size ?? 0}</strong>
          <small>
            {currentOnlineGate?.updated_at
              ? `${t("admin.updatedAt")} ${formatTimestamp(currentOnlineGate.updated_at)}`
              : t("admin.noOnlineMetrics")}
          </small>
        </article>
      </section>

      <section className="panel surface-card">
        <div className="section-header">
          <div className="section-title">
            <AppIcon className="icon-md icon-brand" name="flag" />
            <span>{t("admin.rolloutDecision")}</span>
          </div>
        </div>
        <div className="admin-rollout-grid">
          <article className="admin-rollout-card">
            <span>{t("admin.requestedProfile")}</span>
            <strong>{payload.rollout.requested.profile_id}</strong>
            <small>{payload.rollout.requested.experiment_id ?? t("admin.defaultExperiment")}</small>
          </article>
          <article className="admin-rollout-card">
            <span>{t("admin.effectiveProfile")}</span>
            <strong>{payload.rollout.effective.profile_id}</strong>
            <small>{payload.rollout.effective.experiment_id ?? t("admin.defaultExperiment")}</small>
          </article>
          <article className="admin-rollout-card">
            <span>{t("admin.allowBlocked")}</span>
            <strong>
              {payload.rollout.allow_blocked_rollout
                ? t("admin.flagEnabled")
                : t("admin.flagDisabled")}
            </strong>
            <small>{t("admin.stableProfile")}: {payload.rollout.stable_profile_id}</small>
          </article>
        </div>
        <div className="admin-check-list">
          {payload.rollout.checks.map((check) => (
            <article className="admin-check-row" key={check.name}>
              <div className={`admin-status-pill ${statusTone(check.passed ? "pass" : "fail")}`}>
                {check.passed ? t("admin.checkPassed") : t("admin.checkFailed")}
              </div>
              <div className="admin-check-copy">
                <strong>{check.name}</strong>
                <p>{check.detail}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className="review-grid-two">
        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="clipboard" />
              <span>{t("admin.offlineGates")}</span>
            </div>
          </div>
          <div className="admin-gate-list">
            {payload.offline_gates.map((gate) => {
              const isActiveProfile = gate.profile_id === payload.rollout.effective.profile_id;
              return (
                <article
                  className={`admin-gate-card ${isActiveProfile ? "is-active" : ""}`}
                  key={gate.profile_id}
                >
                  <div className="admin-gate-head">
                    <div>
                      <h3>{gate.profile_id}</h3>
                      <p>
                        {t("admin.fixturePassRate")}: {formatRate(gate.fixture_pass_rate)}
                      </p>
                    </div>
                    <span className={`admin-status-pill ${statusTone(gate.status)}`}>
                      {statusLabel(gate.status, t)}
                    </span>
                  </div>
                  <div className="admin-meta-list">
                    <span>{t("admin.contractVersions")}: {joinOrDash(keyValuePairs(gate.contract_versions))}</span>
                    <span>{t("admin.outputRequirements")}: {joinOrDash(countPairs(gate.output_requirement_counts))}</span>
                    <span>{t("admin.gateChecks")}: {gateCheckSummary(gate.checks)}</span>
                  </div>
                  <div className="admin-fixture-list">
                    {gate.fixture_results.map((fixture) => (
                      <div className="admin-fixture-row" key={`${gate.profile_id}-${fixture.fixture_name}`}>
                        <span>{fixture.fixture_name}</span>
                        <small>
                          {fixture.passed ? t("admin.checkPassed") : t("admin.checkFailed")} ·{" "}
                          {fixture.overall_score} / 100 · {fixture.overall_band}
                        </small>
                      </div>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="trend" />
              <span>{t("admin.onlineGates")}</span>
            </div>
          </div>
          <div className="admin-gate-list">
            {payload.online_gates.map((gate) => {
              const isActiveGate =
                gate.profile_id === payload.rollout.effective.profile_id &&
                (gate.experiment_id ?? null) === (payload.rollout.effective.experiment_id ?? null);
              const metrics = gate.metrics ?? {};
              return (
                <article
                  className={`admin-gate-card ${isActiveGate ? "is-active" : ""}`}
                  key={`${gate.profile_id}:${gate.experiment_id ?? "default"}`}
                >
                  <div className="admin-gate-head">
                    <div>
                      <h3>{gate.profile_id}</h3>
                      <p>{gate.experiment_id ?? t("admin.defaultExperiment")}</p>
                    </div>
                    <span className={`admin-status-pill ${statusTone(gate.status)}`}>
                      {statusLabel(gate.status, t)}
                    </span>
                  </div>
                  <div className="admin-metric-grid">
                    <div>
                      <span>{t("admin.sampleSize")}</span>
                      <strong>{gate.sample_size}</strong>
                    </div>
                    <div>
                      <span>{t("admin.metricAverageScore")}</span>
                      <strong>{formatMetric(metrics.average_overall_score)}</strong>
                    </div>
                    <div>
                      <span>{t("admin.metricHighRiskRate")}</span>
                      <strong>{formatRate(typeof metrics.high_risk_rate === "number" ? metrics.high_risk_rate : null)}</strong>
                    </div>
                    <div>
                      <span>{t("admin.metricFallbackRate")}</span>
                      <strong>{formatRate(typeof metrics.fallback_rate === "number" ? metrics.fallback_rate : null)}</strong>
                    </div>
                  </div>
                  <div className="admin-meta-list">
                    <span>{t("admin.updatedAt")}: {gate.updated_at ? formatTimestamp(gate.updated_at) : "-"}</span>
                    <span>{t("admin.thresholds")}: {joinOrDash(thresholdPairs(gate.thresholds))}</span>
                    <span>{t("admin.gateChecks")}: {gateCheckSummary(gate.checks)}</span>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <section className="panel surface-card admin-command-panel">
        <div className="section-header">
          <div className="section-title">
            <AppIcon className="icon-md icon-brand" name="shield" />
            <span>{t("admin.commandTitle")}</span>
          </div>
        </div>
        <p>{t("admin.commandDesc")}</p>
        <code className="admin-inline-code">make validate-content</code>
      </section>
    </section>
  );
}
