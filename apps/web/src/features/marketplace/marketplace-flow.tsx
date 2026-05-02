"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";

import {
  AppIcon,
  ThumbnailArtwork,
  type IllustrationVariant,
} from "@/components/app-graphics";
import { useAuth } from "@/lib/auth-context";
import { subskillLabel } from "@/lib/mr-ui";
import {
  installOrgSkill,
  listMarketplaceSkills,
  removeOrgSkill,
  setOrgSkillState,
  type MarketplaceListResponse,
  type MarketplaceSkillItem,
} from "@/lib/runtime-api";

type SkillTab = "all" | "installed" | "available" | "disabled";

function maturityLabel(maturity: string): string {
  switch (maturity) {
    case "stable":
      return "Stable";
    case "beta":
      return "Beta";
    case "alpha":
      return "Alpha";
    case "spike":
      return "Spike";
    case "deprecated":
      return "Deprecated";
    default:
      return maturity || "Unknown";
  }
}

function modalityLabel(modality: string): string {
  switch (modality) {
    case "text":
      return "Text";
    case "voice":
      return "Voice";
    case "video":
      return "Video";
    case "mixed":
      return "Mixed";
    default:
      return modality || "Unknown";
  }
}

function stateTone(state: string): "brand" | "success" | "warn" | "error" {
  switch (state) {
    case "installed":
      return "success";
    case "disabled":
      return "warn";
    case "blocked":
      return "error";
    default:
      return "brand";
  }
}

function skillArtworkVariant(skillId: string): IllustrationVariant {
  switch (skillId) {
    case "mr_visit_jp":
      return "presentation";
    case "gp_visit_jp":
      return "conversation";
    default:
      return "report";
  }
}

function readableId(value: string): string {
  return value.replaceAll("_", " ").replaceAll("-", " ");
}

// ─── Skill detail modal ────────────────────────────────────────────────

function SkillDetailModal({
  skill,
  isAdmin,
  orgId: _orgId,
  actionLoading,
  onInstall,
  onDisable,
  onEnable,
  onUninstall,
  onClose,
  t,
}: {
  skill: MarketplaceSkillItem;
  isAdmin: boolean;
  orgId: string;
  actionLoading: string | null;
  onInstall: (skillId: string) => void;
  onDisable: (skillId: string) => void;
  onEnable: (skillId: string) => void;
  onUninstall: (skillId: string) => void;
  onClose: () => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  const mk = skill.marketplace || {};
  const inst = skill.installation;
  const state = inst?.state || "available";
  const busy = actionLoading === skill.id;

  const actionsById = useMemo(() => {
    if (!skill.actions?.length) return new Map<string, string>();
    return new Map(
      skill.actions.map((action) => [action.id, action.description || readableId(action.id)])
    );
  }, [skill.actions]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-panel marketplace-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={mk.title || skill.name}
      >
        <button className="modal-close" onClick={onClose} type="button" aria-label="Close">
          &times;
        </button>

        <div className="modal-header">
          <ThumbnailArtwork
            className="marketplace-card-thumb"
            variant={skillArtworkVariant(skill.id)}
          />
          <div>
            <h2>{mk.title || skill.name}</h2>
            <p className="marketplace-card-id">{skill.id}</p>
            <span className={`status-badge ${stateTone(state)}`}>
              {state === "installed" && t("marketplace.installed")}
              {state === "available" && t("marketplace.available")}
              {state === "disabled" && t("marketplace.disabled")}
              {state === "blocked" && t("marketplace.blocked")}
            </span>
          </div>
        </div>

        <div className="modal-body">
          <div className="marketplace-preview-block">
            <strong>{t("marketplace.trainingFocus")}</strong>
            <p>{mk.summary || "-"}</p>
          </div>

          <div className="marketplace-meta">
            {mk.maturity ? <span>{maturityLabel(mk.maturity)}</span> : null}
            {mk.modality ? <span>{modalityLabel(mk.modality)}</span> : null}
            {mk.locales && mk.locales.length > 0 ? <span>{mk.locales.join(", ").toUpperCase()}</span> : null}
            <span>v{skill.version}</span>
          </div>

          {mk.provider ? (
            <p className="marketplace-provider">
              {t("marketplace.provider")}: {mk.provider}
            </p>
          ) : null}

          {(skill.capabilities || []).length > 0 ? (
            <div className="marketplace-preview-block">
              <strong>{t("marketplace.goal")}</strong>
              <ul className="marketplace-preview-list">
                {(skill.capabilities ?? []).map((capability) => (
                  <li key={capability.id}>
                    <span>{capability.name || readableId(capability.id)}</span>
                    {capability.description ? <small>{capability.description}</small> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {(skill.subskills ?? []).length > 0 ? (
            <div className="marketplace-preview-block">
              <strong>{t("marketplace.subskillsTitle")}</strong>
              <div className="marketplace-meta">
                {(skill.subskills ?? []).map((subskill) => (
                  <span key={`${skill.id}-${subskill}`}>{subskillLabel(subskill)}</span>
                ))}
              </div>
            </div>
          ) : null}

          {skill.capabilities?.some((c) => (c.actions || []).length > 0) ? (
            <div className="marketplace-preview-block">
              <strong>{t("marketplace.actionExamples")}</strong>
              <ul className="marketplace-preview-list">
                {(skill.capabilities ?? []).flatMap((capability) =>
                  (capability.actions || []).slice(0, 3).map((actionId) => (
                    <li key={`${capability.id}-${actionId}`}>
                      <span>{readableId(actionId)}</span>
                      <small>{actionsById.get(actionId) || readableId(actionId)}</small>
                    </li>
                  ))
                )}
              </ul>
            </div>
          ) : null}

          {mk.privacy?.data_notes ? (
            <div className="marketplace-preview-block">
              <strong>{t("marketplace.privacyNotes")}</strong>
              <p>{mk.privacy.data_notes}</p>
            </div>
          ) : null}

          {inst?.installed_version && state === "installed" ? (
            <p className="marketplace-provider">
              {t("marketplace.version")}: {inst.installed_version}
              {inst.installed_at ? ` · ${new Date(inst.installed_at).toLocaleDateString()}` : ""}
            </p>
          ) : null}
        </div>

        {isAdmin ? (
          <div className="modal-actions">
            {state === "available" ? (
              <button
                className="primary-button"
                disabled={busy}
                onClick={() => onInstall(skill.id)}
                type="button"
              >
                {busy ? "..." : t("marketplace.install")}
              </button>
            ) : null}
            {state === "installed" ? (
              <>
                <button
                  className="ghost-button"
                  disabled={busy}
                  onClick={() => onDisable(skill.id)}
                  type="button"
                >
                  {busy ? "..." : t("marketplace.disable")}
                </button>
                <button
                  className="ghost-button danger"
                  disabled={busy}
                  onClick={() => onUninstall(skill.id)}
                  type="button"
                >
                  {busy ? "..." : t("marketplace.uninstall")}
                </button>
              </>
            ) : null}
            {state === "disabled" ? (
              <button
                className="primary-button"
                disabled={busy}
                onClick={() => onEnable(skill.id)}
                type="button"
              >
                {busy ? "..." : t("marketplace.enable")}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>,
    document.body
  );
}

// ─── Main marketplace flow ─────────────────────────────────────────────

export function MarketplaceFlow() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isAdmin = user?.role === "organization_admin" || user?.role === "platform_admin";
  const orgId = user?.org_id || "local";

  const [data, setData] = useState<MarketplaceListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SkillTab>("all");
  const [message, setMessage] = useState<string | null>(null);
  const [modalSkill, setModalSkill] = useState<MarketplaceSkillItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listMarketplaceSkills();
      setData(result);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load marketplace");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInstall = useCallback(async (skillId: string) => {
    setActionLoading(skillId);
    setMessage(null);
    try {
      await installOrgSkill(orgId, skillId, {
        version: "",
        installed_by: user?.learner_id || "",
      });
      setMessage(t("marketplace.installSuccess"));
      await load();
    } catch (installError) {
      const detail = installError instanceof Error ? installError.message : "";
      setMessage(`${t("marketplace.installFailed")}${detail ? `: ${detail}` : ""}`);
    } finally {
      setActionLoading(null);
    }
  }, [load, orgId, t, user?.learner_id]);

  const handleDisable = useCallback(async (skillId: string) => {
    if (!confirm(t("marketplace.confirmDisable"))) {
      return;
    }
    setActionLoading(skillId);
    setMessage(null);
    try {
      await setOrgSkillState(orgId, skillId, "disabled", "disabled by admin");
      setMessage(t("marketplace.stateChanged"));
      await load();
    } catch (disableError) {
      setMessage(disableError instanceof Error ? disableError.message : "Failed to disable skill");
    } finally {
      setActionLoading(null);
    }
  }, [load, orgId, t]);

  const handleEnable = useCallback(async (skillId: string) => {
    setActionLoading(skillId);
    setMessage(null);
    try {
      await setOrgSkillState(orgId, skillId, "installed", "enabled by admin");
      setMessage(t("marketplace.stateChanged"));
      await load();
    } catch (enableError) {
      setMessage(enableError instanceof Error ? enableError.message : "Failed to enable skill");
    } finally {
      setActionLoading(null);
    }
  }, [load, orgId, t]);

  const handleUninstall = useCallback(async (skillId: string) => {
    if (!confirm(t("marketplace.confirmUninstall"))) {
      return;
    }
    setActionLoading(skillId);
    setMessage(null);
    try {
      await removeOrgSkill(orgId, skillId);
      setMessage(t("marketplace.stateChanged"));
      await load();
    } catch (removeError) {
      setMessage(removeError instanceof Error ? removeError.message : "Failed to remove skill");
    } finally {
      setActionLoading(null);
    }
  }, [load, orgId, t]);

  const installedCount = data?.items?.filter((item) => item.installation?.state === "installed").length || 0;
  const availableCount = data?.items?.filter((item) => (item.installation?.state || "available") === "available").length || 0;
  const disabledCount = data?.items?.filter((item) => {
    const state = item.installation?.state || "available";
    return state === "disabled" || state === "blocked";
  }).length || 0;

  const filteredItems: MarketplaceSkillItem[] = useMemo(() => {
    const source = data?.items || [];
    return source.filter((item) => {
      const state = item.installation?.state || "available";
      if (activeTab === "installed") return state === "installed";
      if (activeTab === "available") return state === "available";
      if (activeTab === "disabled") return state === "disabled" || state === "blocked";
      return true;
    });
  }, [activeTab, data?.items]);

  return (
    <section className="dashboard-page marketplace-page">
      <section className="hero-panel surface-card">
        <div className="hero-panel-main">
          <div className="hero-icon-tile">
            <AppIcon className="icon-hero" name="grid" />
          </div>
          <div className="hero-panel-copy">
            <h1>{t("marketplace.title")}</h1>
            <p>{t("marketplace.subtitle")}</p>
          </div>
        </div>
        <button className="ghost-button" onClick={() => void load()} type="button">
          <AppIcon className="icon-sm" name="refresh" />
          <span>{t("marketplace.refresh")}</span>
        </button>
      </section>

      {message ? <div className="surface-card panel">{message}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}
      {!isAdmin ? <div className="surface-card panel">{t("marketplace.adminOnly")}</div> : null}

      <section className="panel surface-card marketplace-summary">
        <article>
          <span>{t("marketplace.installed")}</span>
          <strong>{installedCount}</strong>
        </article>
        <article>
          <span>{t("marketplace.available")}</span>
          <strong>{availableCount}</strong>
        </article>
        <article>
          <span>{t("marketplace.disabled")}</span>
          <strong>{disabledCount}</strong>
        </article>
        <article>
          <span>Org</span>
          <strong>{orgId}</strong>
        </article>
      </section>

      <section className="panel surface-card marketplace-tab-row">
        {(["all", "installed", "available", "disabled"] as SkillTab[]).map((tab) => (
          <button
            key={tab}
            className={`filter-chip${activeTab === tab ? " is-active" : ""}`}
            onClick={() => setActiveTab(tab)}
            type="button"
          >
            {tab === "all" && `${t("marketplace.all")} (${data?.items?.length || 0})`}
            {tab === "installed" && `${t("marketplace.installed")} (${installedCount})`}
            {tab === "available" && `${t("marketplace.available")} (${availableCount})`}
            {tab === "disabled" && `${t("marketplace.disabled")} (${disabledCount})`}
          </button>
        ))}
      </section>

      {loading ? (
        <div className="placeholder-block surface-card">
          <strong>{t("marketplace.loading")}</strong>
          <p>{t("marketplace.loadingDesc")}</p>
        </div>
      ) : null}

      {!loading && filteredItems.length === 0 ? (
        <div className="placeholder-block surface-card">
          <strong>{t("marketplace.emptyFiltered")}</strong>
          <p>{t("marketplace.noSkills")}</p>
          {activeTab !== "all" ? (
            <div className="placeholder-actions">
              <button className="ghost-button" onClick={() => setActiveTab("all")} type="button">
                {t("marketplace.clearFilter")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {!loading && filteredItems.length > 0 ? (
        <section className="marketplace-grid">
          {filteredItems.map((item) => {
            const mk = item.marketplace || {};
            const inst = item.installation;
            const state = inst?.state || "available";
            const busy = actionLoading === item.id;
            return (
              <article
                className={`panel surface-card marketplace-card${state === "disabled" || state === "blocked" ? " is-muted" : ""}`}
                key={item.id}
                onClick={() => setModalSkill(item)}
              >
                <div className="marketplace-card-head">
                  <ThumbnailArtwork className="marketplace-card-thumb" variant={skillArtworkVariant(item.id)} />
                  <div className="marketplace-card-copy">
                    <div className="marketplace-card-title">
                      <h3>{mk.title || item.name}</h3>
                      <span className={`status-badge compact ${stateTone(state)}`}>
                        {state === "installed" && t("marketplace.installed")}
                        {state === "available" && t("marketplace.available")}
                        {state === "disabled" && t("marketplace.disabled")}
                        {state === "blocked" && t("marketplace.blocked")}
                      </span>
                    </div>
                    <p className="marketplace-card-id">{item.id}</p>
                  </div>
                </div>

                <p className="marketplace-card-summary">{mk.summary || "-"}</p>

                <div className="marketplace-meta">
                  {mk.maturity ? <span>{maturityLabel(mk.maturity)}</span> : null}
                  {mk.modality ? <span>{modalityLabel(mk.modality)}</span> : null}
                  {mk.locales && mk.locales.length > 0 ? <span>{mk.locales.join(", ").toUpperCase()}</span> : null}
                  <span>v{item.version}</span>
                </div>

                <div className="marketplace-actions">
                  {isAdmin && state === "available" ? (
                    <button
                      className="primary-button marketplace-action-btn"
                      disabled={busy}
                      onClick={(e) => { e.stopPropagation(); void handleInstall(item.id); }}
                      type="button"
                    >
                      {busy ? "..." : t("marketplace.install")}
                    </button>
                  ) : null}
                  {isAdmin && state === "installed" ? (
                    <>
                      <button
                        className="ghost-button marketplace-action-btn"
                        disabled={busy}
                        onClick={(e) => { e.stopPropagation(); void handleDisable(item.id); }}
                        type="button"
                      >
                        {busy ? "..." : t("marketplace.disable")}
                      </button>
                      <button
                        className="ghost-button marketplace-action-btn danger"
                        disabled={busy}
                        onClick={(e) => { e.stopPropagation(); void handleUninstall(item.id); }}
                        type="button"
                      >
                        {busy ? "..." : t("marketplace.uninstall")}
                      </button>
                    </>
                  ) : null}
                  {isAdmin && state === "disabled" ? (
                    <button
                      className="primary-button marketplace-action-btn"
                      disabled={busy}
                      onClick={(e) => { e.stopPropagation(); void handleEnable(item.id); }}
                      type="button"
                    >
                      {busy ? "..." : t("marketplace.enable")}
                    </button>
                  ) : null}
                </div>

                {inst?.installed_version && state === "installed" ? (
                  <small className="marketplace-provider">
                    {t("marketplace.version")}: {inst.installed_version}
                    {inst.installed_at ? ` · ${new Date(inst.installed_at).toLocaleDateString()}` : ""}
                  </small>
                ) : null}
              </article>
            );
          })}
        </section>
      ) : null}

      {/* Skill detail modal */}
      {modalSkill ? (
        <SkillDetailModal
          skill={modalSkill}
          isAdmin={isAdmin}
          orgId={orgId}
          actionLoading={actionLoading}
          onInstall={(id) => { void handleInstall(id); }}
          onDisable={(id) => { void handleDisable(id); }}
          onEnable={(id) => { void handleEnable(id); }}
          onUninstall={(id) => { void handleUninstall(id); }}
          onClose={() => setModalSkill(null)}
          t={t}
        />
      ) : null}
    </section>
  );
}
