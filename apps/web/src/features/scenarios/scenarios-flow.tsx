"use client";

import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";

import { AppIcon, ThumbnailArtwork } from "@/components/app-graphics";
import { StartSessionErrorBanner } from "@/components/start-session-error-banner";
import {
  attitudeLabel,
  difficultyStars,
  scenarioArtVariant,
  subskillLabel,
} from "@/lib/mr-ui";
import {
  installOrgSkill,
  readOptionalProgressSnapshot,
  readRuntimeJson,
  startRuntimeSession,
  type ProgressSnapshotResponse,
  type ScenarioListResponse,
  type ScenarioSummary,
} from "@/lib/runtime-api";
import {
  canManageSkillInstall,
  parseStartSessionError,
  type StartSessionErrorDetails,
} from "@/lib/start-session-error";
import { useAuth } from "@/lib/auth-context";

const DEFAULT_LEARNER_ID = "learner_demo_001";

const PAGE_SIZE = 8;

function scenarioCopy(scenario: ScenarioSummary, t: (key: string, options?: Record<string, unknown>) => string): string {
  const focus = scenario.focus_subskills
    .slice(0, 2)
    .map((item) => subskillLabel(item))
    .join("、");
  
  const _key = scenario.persona_attitude as keyof Record<string, unknown>;
  const translation = t(`scenarios.attitudes.${scenario.persona_attitude}`, { defaultValue: "" });
  
  if (translation) return translation;

  return t("scenarios.defaultCopy", { 
    specialty: scenario.persona_specialty, 
    focus: focus || t("scenarios.allSkills") 
  });
}

export function ScenariosFlow() {
  const router = useRouter();
  const [isRoutePending, startRouteTransition] = useTransition();
  const { t, i18n } = useTranslation();
  const { user, authMode, isLoading: authLoading } = useAuth();
  const activeLearnerId = (authMode === "mock" || authMode === "oidc") && user ? user.learner_id : DEFAULT_LEARNER_ID;

  const [payload, setPayload] = useState<ScenarioListResponse | null>(null);
  const [progress, setProgress] = useState<ProgressSnapshotResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startError, setStartError] = useState<StartSessionErrorDetails | null>(null);
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null);
  const [installingSkill, setInstallingSkill] = useState(false);
  const [query, setQuery] = useState("");
  const [difficultyFilter, setDifficultyFilter] = useState<"all" | "easy" | "medium" | "hard">("all");
  const [personaFilter, setPersonaFilter] = useState("all");
  const [focusFilter, setFocusFilter] = useState("all");
  const [sortMode, setSortMode] = useState<"recommended" | "difficulty">("recommended");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [currentPage, setCurrentPage] = useState(1);

  const loadScenarios = useCallback((learnerId: string) => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      setStartError(null);
      const [scenarioResult, progressResult] = await Promise.allSettled([
        readRuntimeJson<ScenarioListResponse>("/api/runtime/scenarios"),
        readOptionalProgressSnapshot(learnerId),
      ]);

      if (!active) {
        return;
      }

      if (scenarioResult.status === "fulfilled") {
        setPayload(scenarioResult.value);
      } else {
        setPayload(null);
      }
      if (progressResult.status === "fulfilled") {
        setProgress(progressResult.value);
      } else {
        setProgress(null);
      }

      const failures = [scenarioResult, progressResult]
        .filter((item): item is PromiseRejectedResult => item.status === "rejected")
        .map((item) => item.reason)
        .filter((item): item is Error => item instanceof Error)
        .map((item) => item.message);
      setError(failures.length > 0 ? failures.join(" | ") : null);
      setLoading(false);
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if ((authMode === "mock" || authMode === "oidc") && !user) return;
    return loadScenarios(activeLearnerId);
  }, [activeLearnerId, authLoading, authMode, loadScenarios, user]);

  const recommendationRanks = useMemo(() => {
    const practicePath = progress?.practice_path ?? progress?.latest_recommendations ?? [];
    return new Map(practicePath.map((item, index) => [item.scenario_id, index]));
  }, [progress]);

  const personaOptions = useMemo(() => {
    return Array.from(new Set((payload?.scenarios ?? []).map((scenario) => scenario.persona_attitude)));
  }, [payload]);

  const focusOptions = useMemo(() => {
    return Array.from(new Set((payload?.scenarios ?? []).flatMap((scenario) => scenario.focus_subskills)));
  }, [payload]);

  const filteredScenarios = useMemo(() => {
    const source = payload?.scenarios ?? [];
    const normalizedQuery = query.trim().toLowerCase();
    const nextRows = source.filter((scenario) => {
      const matchQuery =
        normalizedQuery.length === 0 ||
        [scenario.title, scenario.persona_label, scenario.persona_specialty, ...scenario.focus_subskills]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      const matchDifficulty = difficultyFilter === "all" || scenario.difficulty === difficultyFilter;
      const matchPersona = personaFilter === "all" || scenario.persona_attitude === personaFilter;
      const matchFocus = focusFilter === "all" || scenario.focus_subskills.includes(focusFilter);
      return matchQuery && matchDifficulty && matchPersona && matchFocus;
    });

    nextRows.sort((left, right) => {
      if (sortMode === "difficulty") {
        const rank = { easy: 0, medium: 1, hard: 2 };
        return rank[left.difficulty] - rank[right.difficulty];
      }
      const leftRank = recommendationRanks.get(left.id) ?? Number.MAX_SAFE_INTEGER;
      const rightRank = recommendationRanks.get(right.id) ?? Number.MAX_SAFE_INTEGER;
      if (leftRank !== rightRank) return leftRank - rightRank;
      return left.title.localeCompare(right.title);
    });
    return nextRows;
  }, [difficultyFilter, focusFilter, payload, personaFilter, query, recommendationRanks, sortMode]);

  const totalPages = Math.max(1, Math.ceil(filteredScenarios.length / PAGE_SIZE));
  const pagedScenarios = filteredScenarios.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const featuredRecommendation = useMemo(() => {
    const practicePath = progress?.practice_path ?? progress?.latest_recommendations ?? [];
    if (!practicePath[0]) return null;
    const recommendation = practicePath[0];
    const scenario = payload?.scenarios.find((item) => item.id === recommendation.scenario_id) ?? null;
    return { recommendation, scenario };
  }, [payload, progress]);
  const activeTeachingPlan = progress?.coach_memory.teaching_plan ?? null;

  const clearFilters = () => {
    setQuery("");
    setDifficultyFilter("all");
    setPersonaFilter("all");
    setFocusFilter("all");
    setCurrentPage(1);
  };

  const startSession = async (scenarioId: string) => {
    setError(null);
    setStartError(null);
    setStartingScenarioId(scenarioId);
    try {
      const data = await startRuntimeSession(
        activeLearnerId,
        scenarioId,
        {
          orgId: user?.org_id ?? null,
          viewerRole: user?.role ?? null,
        },
        i18n.language
      );
      startRouteTransition(() => {
        router.push(`/sessions/${data.session_id}?scenario=${scenarioId}`);
      });
    } catch (startError) {
      const parsed = parseStartSessionError(startError, "Unknown start session error");
      setError(parsed.message);
      setStartError(parsed);
    } finally {
      setStartingScenarioId(null);
    }
  };

  const installMissingSkill = useCallback(async () => {
    if (!startError || startError.kind !== "skill_not_installed" || !startError.skillId) {
      return;
    }
    const orgId = startError.orgId || user?.org_id || "local";
    setInstallingSkill(true);
    setError(null);
    try {
      await installOrgSkill(orgId, startError.skillId, {
        ...(user?.learner_id ? { installed_by: user.learner_id } : {}),
      });
      setStartError(null);
      setError(t("marketplace.installSuccess"));
    } catch (installError) {
      const message = installError instanceof Error ? installError.message : t("marketplace.installFailed");
      setError(`${t("marketplace.installFailed")}: ${message}`);
    } finally {
      setInstallingSkill(false);
    }
  }, [startError, t, user?.learner_id, user?.org_id]);

  /* Pagination helpers */
  const pageNumbers = useMemo(() => {
    if (totalPages <= 5) return Array.from({ length: totalPages }, (_, i) => i + 1);
    if (currentPage <= 3) return [1, 2, 3, null, totalPages];
    if (currentPage >= totalPages - 2) return [1, null, totalPages - 2, totalPages - 1, totalPages];
    return [1, null, currentPage - 1, currentPage, currentPage + 1, null, totalPages];
  }, [currentPage, totalPages]);

  return (
    <section className="dashboard-page">
      {/* ─── Page hero ─── */}
      <div className="scenarios-hero">
        <div className="scenarios-hero-icon">
          <AppIcon className="icon-xl icon-brand" name="layers" />
        </div>
        <div className="scenarios-hero-copy">
          <h1>{t("scenarios.heroTitle")}</h1>
          <p>{t("scenarios.heroSubtitle")}</p>
        </div>
      </div>

      {/* ─── Filter bar ─── */}
      <section className="panel surface-card scenarios-filter-bar">
        <div className="scenarios-filter-search">
          <AppIcon className="icon-md filter-icon" name="search" />
          <input
            className="filter-input scenarios-search-input"
            onChange={(event) => { setQuery(event.target.value); setCurrentPage(1); }}
            placeholder={t("scenarios.searchPlaceholder")}
            value={query}
          />
        </div>

        <div className="scenarios-filter-group">
          <span className="scenarios-filter-label">{t("scenarios.filterDifficulty")}</span>
          <div className="chip-group">
            {(["all", "easy", "medium", "hard"] as const).map((val) => (
              <button
                key={val}
                className={`filter-chip${difficultyFilter === val ? " is-active" : ""}`}
                onClick={() => { setDifficultyFilter(val); setCurrentPage(1); }}
                type="button"
              >
                {{ all: t("scenarios.all"), easy: t("scenarios.easy"), medium: t("scenarios.medium"), hard: t("scenarios.hard") }[val]}
              </button>
            ))}
          </div>
        </div>

        <div className="scenarios-filter-group">
          <span className="scenarios-filter-label">{t("scenarios.filterType")}</span>
          <div className="chip-group">
            <button
              className={`filter-chip${personaFilter === "all" ? " is-active" : ""}`}
              onClick={() => { setPersonaFilter("all"); setCurrentPage(1); }}
              type="button"
            >
              {t("scenarios.all")}
            </button>
            {personaOptions.map((item) => (
              <button
                key={item}
                className={`filter-chip${personaFilter === item ? " is-active" : ""}`}
                onClick={() => { setPersonaFilter(item); setCurrentPage(1); }}
                type="button"
              >
                {attitudeLabel(item)}
              </button>
            ))}
          </div>
        </div>

        <div className="scenarios-filter-group">
          <span className="scenarios-filter-label">{t("scenarios.filterSkill")}</span>
          <div className="filter-select-wrap">
            <select
              className="filter-select"
              onChange={(event) => { setFocusFilter(event.target.value); setCurrentPage(1); }}
              value={focusFilter}
            >
              <option value="all">{t("scenarios.allSkills")}</option>
              {focusOptions.map((item) => (
                <option key={item} value={item}>{subskillLabel(item)}</option>
              ))}
            </select>
            <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
          </div>
        </div>

        <button className="ghost-button scenarios-clear-btn" onClick={clearFilters} type="button">
          <AppIcon className="icon-sm" name="refresh" />
          <span>{t("scenarios.clearFilter")}</span>
        </button>
      </section>

      {startError ? (
        <StartSessionErrorBanner
          canInstall={canManageSkillInstall(user?.role)}
          error={startError}
          installBusy={installingSkill}
          onInstall={() => {
            void installMissingSkill();
          }}
        />
      ) : error ? <div className="error-banner">{error}</div> : null}

      {/* ─── Toolbar ─── */}
      <div className="scenarios-catalog-toolbar">
        <strong>{t("scenarios.totalCount", { count: filteredScenarios.length })}</strong>
        <div className="catalog-toolbar-actions">
          <label className="catalog-sort">
            <span>{t("scenarios.sortBy")}</span>
            <div className="filter-select-wrap">
              <select
                className="filter-select catalog-sort-select"
                onChange={(event) => setSortMode(event.target.value as "recommended" | "difficulty")}
                value={sortMode}
              >
                <option value="recommended">{t("scenarios.sortRecommend")}</option>
                <option value="difficulty">{t("scenarios.sortDifficulty")}</option>
              </select>
              <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
            </div>
          </label>
          <div className="icon-toggle-group">
            <button
              className={`icon-toggle${viewMode === "grid" ? " is-active" : ""}`}
              onClick={() => setViewMode("grid")}
              type="button"
            >
              <AppIcon className="icon-sm" name="grid" />
            </button>
            <button
              className={`icon-toggle${viewMode === "list" ? " is-active" : ""}`}
              onClick={() => setViewMode("list")}
              type="button"
            >
              <AppIcon className="icon-sm" name="list" />
            </button>
          </div>
        </div>
      </div>

      {/* ─── Catalog layout: grid + sidebar ─── */}
      <div className="catalog-layout">
        <div>
          <div className={`scenario-grid${viewMode === "list" ? " is-list" : ""}`}>
            {loading ? (
              <div className="placeholder-block surface-card">
                <strong>{t("scenarios.loading")}</strong>
                <p>{t("scenarios.loadingDesc")}</p>
              </div>
            ) : pagedScenarios.length === 0 ? (
              <div className="placeholder-block surface-card">
                <strong>{t("scenarios.noMatch")}</strong>
                <p>{t("scenarios.noMatchDesc")}</p>
              </div>
            ) : (
              pagedScenarios.map((scenario) => {
                const isStarting = startingScenarioId === scenario.id || isRoutePending;
                return (
                  <article className="scenario-card-v2" key={scenario.id}>
                    <ThumbnailArtwork
                      className="scenario-card-thumb"
                      variant={scenarioArtVariant(scenario.id, scenario.focus_subskills)}
                    />
                    <div className="scenario-card-copy">
                      <h3>{scenario.title}</h3>
                      <p>{scenarioCopy(scenario, t)}</p>
                      <div className="scenario-card-line">
                        <span>{t("scenarios.difficulty")}</span>
                        <strong>{difficultyStars(scenario.difficulty)}</strong>
                      </div>
                      <div className="scenario-card-line">
                        <span>{t("scenarios.doctorType")}</span>
                        <span className="mini-tag">{attitudeLabel(scenario.persona_attitude)}</span>
                      </div>
                      <div className="scenario-card-line">
                        <span>{t("scenarios.focusTraining")}</span>
                        <div className="tag-list">
                          {scenario.focus_subskills.slice(0, 2).map((skill) => (
                            <span className="mini-tag" key={skill}>{subskillLabel(skill)}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <button
                      className="primary-button full-button"
                      disabled={isStarting}
                      onClick={() => void startSession(scenario.id)}
                      type="button"
                    >
                      <AppIcon className="icon-sm" name="play" />
                      <span>{isStarting ? t("scenarios.starting") : t("scenarios.startTraining")}</span>
                    </button>
                  </article>
                );
              })
            )}
          </div>

          {/* ─── Pagination ─── */}
          {!loading && filteredScenarios.length > PAGE_SIZE && (
            <div className="pagination-card surface-card">
              <button
                className="pager-button"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                type="button"
              >
                {t("scenarios.prevPage")}
              </button>
              <div className="pager-group">
                {pageNumbers.map((num, idx) =>
                  num === null ? (
                    <span className="pager-ellipsis" key={`ellipsis-${idx}`}>…</span>
                  ) : (
                    <button
                      key={num}
                      className={`pager-chip${currentPage === num ? " is-active" : ""}`}
                      onClick={() => setCurrentPage(num)}
                      type="button"
                    >
                      {num}
                    </button>
                  )
                )}
              </div>
              <button
                className="pager-button"
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                type="button"
              >
                {t("scenarios.nextPage")}
              </button>
              <div className="pager-page-size">
                <span>{t("scenarios.perPage", { count: PAGE_SIZE })}</span>
                <AppIcon className="icon-sm" name="chevron-down" />
              </div>
            </div>
          )}
        </div>

        {/* ─── Right sidebar ─── */}
        <aside className="catalog-side-panel surface-card">
          <div className="section-header">
            <div className="section-title">
              <AppIcon className="icon-md icon-brand" name="star" />
              <span>{t("scenarios.recommendBasedOn")}</span>
            </div>
          </div>

          <div className="side-note-block">
            <strong>{t("scenarios.reason")}</strong>
            <ul className="side-bullet-list">
              {(progress?.coach_memory.next_actions ?? []).slice(0, 2).map((item) => (
                <li key={item}>{item}</li>
              ))}
              {(progress?.coach_memory.next_actions ?? []).length === 0 && (
                <>
                  <li>{t("scenarios.defaultReason1")}</li>
                  <li>{t("scenarios.defaultReason2")}</li>
                </>
              )}
            </ul>
          </div>

          {activeTeachingPlan ? (
            <div className="side-note-block">
              <strong>{t("progress.activeTeachingPlan")}</strong>
              <p>{t("progress.targetBehavior")}{activeTeachingPlan.target_behavior}</p>
              <p>{t("progress.successCriterion")}{activeTeachingPlan.success_criterion}</p>
              <div className="tag-list">
                {activeTeachingPlan.focus_subskills.slice(0, 2).map((skill) => (
                  <span className="mini-tag" key={skill}>{subskillLabel(skill)}</span>
                ))}
              </div>
              {Array.isArray(activeTeachingPlan.prior_evidence) && activeTeachingPlan.prior_evidence.length > 0 ? (
                <ul className="side-bullet-list">
                  {activeTeachingPlan.prior_evidence.slice(0, 2).map((item) => (
                    <li key={`${item.summary}-${item.turn_index ?? "na"}`}>
                      {item.summary}
                      {item.scenario_title ? ` · ${item.scenario_title}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          <div className="side-note-block">
            <strong>{t("scenarios.priorityScenario")}</strong>
            {featuredRecommendation ? (
              <>
                <div className="side-featured-card">
                  <ThumbnailArtwork
                    className="side-featured-thumb"
                    variant={scenarioArtVariant(
                      featuredRecommendation.recommendation.scenario_id,
                      featuredRecommendation.recommendation.target_subskills
                    )}
                  />
                  <div className="side-featured-copy">
                    <h4>{featuredRecommendation.recommendation.title}</h4>
                    <span className="mini-tag">
                      {attitudeLabel(featuredRecommendation.scenario?.persona_attitude)}
                    </span>
                    <p>{t("scenarios.difficulty")}{difficultyStars(featuredRecommendation.recommendation.difficulty)}</p>
                  </div>
                </div>
                <button
                  className="primary-button full-button scenarios-start-now-btn"
                  disabled={startingScenarioId === featuredRecommendation.recommendation.scenario_id}
                  onClick={() => void startSession(featuredRecommendation.recommendation.scenario_id)}
                  type="button"
                >
                  <AppIcon className="icon-sm" name="play" />
                  <span>{t("scenarios.startNow")}</span>
                </button>
              </>
            ) : (
              <div className="placeholder-inline">{t("scenarios.noRecommendYet")}</div>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
