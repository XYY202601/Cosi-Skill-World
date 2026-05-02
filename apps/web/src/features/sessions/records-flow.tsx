"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "react-i18next";

import { AppIcon, ThumbnailArtwork } from "@/components/app-graphics";
import { StartSessionErrorBanner } from "@/components/start-session-error-banner";
import { MOCK_USERS } from "@/lib/mock-users";
import {
  clampPercent,
  complianceSeverityLabel,
  difficultyLabel,
  difficultyStars,
  finishReasonLabel,
  formatTimestamp,
  overallBandLabel,
  scenarioArtVariant,
  subskillLabel,
} from "@/lib/mr-ui";
import {
  fetchCrossSkillDashboard,
  installOrgSkill,
  type CrossSkillDashboardEntry,
  readOptionalProgressSnapshot,
  readRuntimeJson,
  startRuntimeSession,
  type ProgressHistoryItem,
  type ProgressSnapshotResponse,
  type ScenarioListResponse,
  type ScenarioSummary,
} from "@/lib/runtime-api";
import {
  canManageSkillInstall,
  parseStartSessionError,
  type StartSessionErrorDetails,
} from "@/lib/start-session-error";

// ── Role constants ──────────────────────────────────────────────────────
const LEARNER_DATA_ROLES = ["supervisor", "organization_admin", "platform_admin"] as const;

type RecordsFlowProps = {
  initialLearnerId: string;
  orgId?: string | null;
  viewerRole?: string | null;
  initialSearchParams?: {
    compliance_severity?: string;
    difficulty?: string;
    finish_reason?: string;
    learner?: string;
    org?: string;
    page?: string;
    persona?: string;
    prompt_profile?: string;
    q?: string;
    score_band?: string;
    scenario?: string;
    sort?: string;
    weak_skill?: string;
  };
};

type HistoryGroup = {
  dateKey: string;
  dateLabel: string;
  items: ProgressHistoryItem[];
};

type RecordsRouteState = {
  activeLearnerId: string;
  complianceSeverityFilter: string;
  currentPage: number;
  difficultyFilter: "all" | "easy" | "medium" | "hard";
  finishReasonFilter: string;
  personaFilter: string;
  promptProfileFilter: string;
  query: string;
  scoreBandFilter: string;
  scenarioFilter: string;
  sortMode: "newest" | "score_desc" | "score_asc";
  weakSkillFilter: string;
};

type RouteParamSource =
  | {
      get: (key: string) => string | null;
    }
  | null
  | Record<string, string | undefined>
  | undefined;

const DEFAULT_LEARNER_ID = "learner_demo_001";
const GROUPS_PER_PAGE = 7;
const COMPLIANCE_SEVERITY_RANK: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  positive: 0,
};

function formatDateLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  });
}

function formatDateKey(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function visiblePageNumbers(currentPage: number, totalPages: number): number[] {
  const pages = new Set<number>([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
  return [...pages].filter((page) => page >= 1 && page <= totalPages).sort((left, right) => left - right);
}

function fallbackOverallBand(score: number): string {
  if (score >= 85) {
    return "advanced";
  }
  if (score >= 72) {
    return "proficient";
  }
  if (score >= 58) {
    return "developing";
  }
  return "emerging";
}

function resolveOverallBand(item: ProgressHistoryItem): string {
  if (typeof item.overall_band === "string" && item.overall_band.trim()) {
    return item.overall_band;
  }
  return fallbackOverallBand(item.overall_score);
}

function resolveComplianceSeverity(item: ProgressHistoryItem): string | null {
  if (typeof item.max_compliance_severity === "string" && item.max_compliance_severity.trim()) {
    return item.max_compliance_severity;
  }
  if (!Array.isArray(item.compliance_severities) || item.compliance_severities.length === 0) {
    return null;
  }
  const validSeverities = item.compliance_severities.filter(
    (value): value is string => typeof value === "string" && value.trim().length > 0
  );
  if (validSeverities.length === 0) {
    return null;
  }
  return [...validSeverities].sort(
    (left, right) =>
      (COMPLIANCE_SEVERITY_RANK[right] ?? -1) - (COMPLIANCE_SEVERITY_RANK[left] ?? -1) ||
      left.localeCompare(right)
  )[0] ?? null;
}

function sortHistoryItems(
  items: ProgressHistoryItem[],
  sortMode: "newest" | "score_desc" | "score_asc"
): ProgressHistoryItem[] {
  const sorted = [...items];
  sorted.sort((left, right) => {
    if (sortMode === "score_desc") {
      return right.overall_score - left.overall_score || new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime();
    }
    if (sortMode === "score_asc") {
      return left.overall_score - right.overall_score || new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime();
    }
    return new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime();
  });
  return sorted;
}

function hasRouteGetter(input: RouteParamSource): input is { get: (key: string) => string | null } {
  return Boolean(input && typeof input === "object" && "get" in input && typeof input.get === "function");
}

function readRouteParam(input: RouteParamSource, key: string): string | null {
  if (!input) {
    return null;
  }
  if (hasRouteGetter(input)) {
    return input.get(key);
  }
  const value = input[key];
  return typeof value === "string" ? value : null;
}

function parseRecordsRouteState(
  input: RouteParamSource,
  fallbackLearnerId: string
): RecordsRouteState {
  const learner = readRouteParam(input, "learner")?.trim() || fallbackLearnerId;
  const query = readRouteParam(input, "q")?.trim() ?? "";
  const difficulty = readRouteParam(input, "difficulty");
  const sort = readRouteParam(input, "sort");
  const page = readRouteParam(input, "page");

  return {
    activeLearnerId: learner,
    complianceSeverityFilter: readRouteParam(input, "compliance_severity") ?? "all",
    currentPage:
      page && Number.isFinite(Number.parseInt(page, 10)) && Number.parseInt(page, 10) > 0
        ? Number.parseInt(page, 10)
        : 1,
    difficultyFilter:
      difficulty === "easy" || difficulty === "medium" || difficulty === "hard"
        ? difficulty
        : "all",
    finishReasonFilter: readRouteParam(input, "finish_reason") ?? "all",
    personaFilter: readRouteParam(input, "persona") ?? "all",
    promptProfileFilter: readRouteParam(input, "prompt_profile") ?? "all",
    query,
    scoreBandFilter: readRouteParam(input, "score_band") ?? "all",
    scenarioFilter: readRouteParam(input, "scenario") ?? "all",
    sortMode:
      sort === "score_desc" || sort === "score_asc"
        ? sort
        : "newest",
    weakSkillFilter: readRouteParam(input, "weak_skill") ?? "all",
  };
}

function buildRecordsQueryString(state: RecordsRouteState): string {
  const params = new URLSearchParams();
  if (state.activeLearnerId && state.activeLearnerId !== DEFAULT_LEARNER_ID) {
    params.set("learner", state.activeLearnerId);
  }
  if (state.query) {
    params.set("q", state.query);
  }
  if (state.scoreBandFilter !== "all") {
    params.set("score_band", state.scoreBandFilter);
  }
  if (state.difficultyFilter !== "all") {
    params.set("difficulty", state.difficultyFilter);
  }
  if (state.scenarioFilter !== "all") {
    params.set("scenario", state.scenarioFilter);
  }
  if (state.personaFilter !== "all") {
    params.set("persona", state.personaFilter);
  }
  if (state.finishReasonFilter !== "all") {
    params.set("finish_reason", state.finishReasonFilter);
  }
  if (state.complianceSeverityFilter !== "all") {
    params.set("compliance_severity", state.complianceSeverityFilter);
  }
  if (state.promptProfileFilter !== "all") {
    params.set("prompt_profile", state.promptProfileFilter);
  }
  if (state.weakSkillFilter !== "all") {
    params.set("weak_skill", state.weakSkillFilter);
  }
  if (state.sortMode !== "newest") {
    params.set("sort", state.sortMode);
  }
  if (state.currentPage > 1) {
    params.set("page", String(state.currentPage));
  }
  return params.toString();
}

export function RecordsFlow({
  initialLearnerId,
  orgId,
  viewerRole,
  initialSearchParams,
}: RecordsFlowProps) {
  const router = useRouter();
  const pathname = usePathname() ?? "/records";
  const searchParams = useSearchParams();
  const [isRoutePending, startRouteTransition] = useTransition();
  const { t, i18n } = useTranslation();
  const initialRouteState = useMemo(
    () => parseRecordsRouteState(initialSearchParams, initialLearnerId),
    [initialLearnerId, initialSearchParams]
  );

  const [learnerId, setLearnerId] = useState(initialRouteState.activeLearnerId);
  const [activeLearnerId, setActiveLearnerId] = useState(initialRouteState.activeLearnerId);
  const [snapshot, setSnapshot] = useState<ProgressSnapshotResponse | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [query, setQuery] = useState(initialRouteState.query);
  const [scoreBandFilter, setScoreBandFilter] = useState(initialRouteState.scoreBandFilter);
  const [difficultyFilter, setDifficultyFilter] = useState<"all" | "easy" | "medium" | "hard">(initialRouteState.difficultyFilter);
  const [scenarioFilter, setScenarioFilter] = useState(initialRouteState.scenarioFilter);
  const [personaFilter, setPersonaFilter] = useState(initialRouteState.personaFilter);
  const [finishReasonFilter, setFinishReasonFilter] = useState(initialRouteState.finishReasonFilter);
  const [complianceSeverityFilter, setComplianceSeverityFilter] = useState(initialRouteState.complianceSeverityFilter);
  const [promptProfileFilter, setPromptProfileFilter] = useState(initialRouteState.promptProfileFilter);
  const [weakSkillFilter, setWeakSkillFilter] = useState(initialRouteState.weakSkillFilter);
  const [sortMode, setSortMode] = useState<"newest" | "score_desc" | "score_asc">(initialRouteState.sortMode);
  const [currentPage, setCurrentPage] = useState(initialRouteState.currentPage);
  const [crossSkills, setCrossSkills] = useState<CrossSkillDashboardEntry[]>([]);
  const [skillFilter, setSkillFilter] = useState("all");
  const [startingScenarioId, setStartingScenarioId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startError, setStartError] = useState<StartSessionErrorDetails | null>(null);
  const [installingSkill, setInstallingSkill] = useState(false);

  const loadRecords = useCallback(async (targetLearnerId: string) => {
    const normalizedLearnerId = targetLearnerId.trim();
    if (!normalizedLearnerId) {
      return;
    }
    setActiveLearnerId(normalizedLearnerId);
    setLearnerId(normalizedLearnerId);
    setLoading(true);
    setError(null);
    setStartError(null);

    const [scenarioResult, progressResult, crossSkillResult] = await Promise.allSettled([
      readRuntimeJson<ScenarioListResponse>("/api/runtime/scenarios"),
      readOptionalProgressSnapshot(normalizedLearnerId, {
        orgId,
        viewerRole,
      }),
      fetchCrossSkillDashboard(orgId || "local", normalizedLearnerId),
    ]);

    if (scenarioResult.status === "fulfilled") {
      setScenarios(Array.isArray(scenarioResult.value.scenarios) ? scenarioResult.value.scenarios : []);
    } else {
      setScenarios([]);
    }

    if (progressResult.status === "fulfilled") {
      setSnapshot(progressResult.value);
    } else {
      setSnapshot(null);
    }

    if (crossSkillResult.status === "fulfilled") {
      setCrossSkills(crossSkillResult.value.skills);
    } else {
      setCrossSkills([]);
    }

    const failures = [scenarioResult, progressResult]
      .filter((item): item is PromiseRejectedResult => item.status === "rejected")
      .map((item) => item.reason)
      .filter((item): item is Error => item instanceof Error)
      .map((item) => item.message);

    setError(failures.length > 0 ? failures.join(" | ") : null);
    setLoading(false);
  }, [orgId, viewerRole]);

  useEffect(() => {
    void loadRecords(initialRouteState.activeLearnerId);
  }, [initialRouteState.activeLearnerId, loadRecords]);



  const scenarioLookup = useMemo(() => {
    return Object.fromEntries(scenarios.map((item) => [item.id, item]));
  }, [scenarios]);

  const personaOptions = useMemo(() => {
    return Array.from(
      new Set(
        (snapshot?.recent_history ?? [])
          .map((item) => item.persona_label)
          .filter((item): item is string => typeof item === "string" && item.length > 0)
      )
    );
  }, [snapshot]);

  const scenarioOptions = useMemo(() => {
    const options = new Map<string, string>();
    for (const item of snapshot?.recent_history ?? []) {
      const title = item.scenario_title ?? scenarioLookup[item.scenario_id]?.title ?? item.scenario_id;
      options.set(item.scenario_id, title);
    }
    return [...options.entries()].map(([id, title]) => ({ id, title }));
  }, [scenarioLookup, snapshot]);

  const finishReasonOptions = useMemo(() => {
    return Array.from(
      new Set(
        (snapshot?.recent_history ?? [])
          .map((item) => item.finish_reason)
          .filter((item): item is string => typeof item === "string" && item.length > 0)
      )
    );
  }, [snapshot]);

  const scoreBandOptions = useMemo(() => {
    return Array.from(new Set((snapshot?.recent_history ?? []).map((item) => resolveOverallBand(item))));
  }, [snapshot]);

  const complianceSeverityOptions = useMemo(() => {
    return Array.from(
      new Set(
        (snapshot?.recent_history ?? [])
          .map((item) => resolveComplianceSeverity(item))
          .filter((item): item is string => typeof item === "string" && item.length > 0)
      )
    ).sort(
      (left, right) =>
        (COMPLIANCE_SEVERITY_RANK[right] ?? -1) - (COMPLIANCE_SEVERITY_RANK[left] ?? -1) ||
        left.localeCompare(right)
    );
  }, [snapshot]);

  const promptProfileOptions = useMemo(() => {
    return Array.from(
      new Set(
        (snapshot?.recent_history ?? [])
          .map((item) => item.prompt_profile)
          .filter((item): item is string => typeof item === "string" && item.length > 0)
      )
    );
  }, [snapshot]);

  const weakSkillOptions = useMemo(() => {
    return Array.from(
      new Set(
        (snapshot?.recent_history ?? []).flatMap((item) => [
          ...(Array.isArray(item.weak_subskills) ? item.weak_subskills : []),
          ...(Array.isArray(item.priority_subskills) ? item.priority_subskills : []),
        ])
      )
    );
  }, [snapshot]);

  const skillOptions = useMemo(() => {
    const known = new Map(crossSkills.map((s) => [s.skill_id, s.skill_name]));
    const seen = new Set<string>();
    const result: { id: string; name: string }[] = [];
    for (const item of snapshot?.recent_history ?? []) {
      if (item.skill_id && !seen.has(item.skill_id)) {
        seen.add(item.skill_id);
        result.push({ id: item.skill_id, name: known.get(item.skill_id) ?? item.skill_id });
      }
    }
    return result;
  }, [crossSkills, snapshot]);

  const filteredHistory = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return (snapshot?.recent_history ?? []).filter((item) => {
      const scenario = scenarioLookup[item.scenario_id];
      const difficulty = item.difficulty ?? scenario?.difficulty ?? "";
      const searchBlob = [
        item.scenario_title,
        scenario?.title,
        item.persona_label,
        ...(item.diagnosis_summaries ?? []),
      ]
        .filter((value): value is string => typeof value === "string" && value.length > 0)
        .join(" ")
        .toLowerCase();

      if (normalizedQuery && !searchBlob.includes(normalizedQuery)) {
        return false;
      }
      if (scoreBandFilter !== "all" && resolveOverallBand(item) !== scoreBandFilter) {
        return false;
      }
      if (difficultyFilter !== "all" && difficulty !== difficultyFilter) {
        return false;
      }
      if (scenarioFilter !== "all" && item.scenario_id !== scenarioFilter) {
        return false;
      }
      if (personaFilter !== "all" && item.persona_label !== personaFilter) {
        return false;
      }
      if (finishReasonFilter !== "all" && item.finish_reason !== finishReasonFilter) {
        return false;
      }
      if (
        complianceSeverityFilter !== "all" &&
        resolveComplianceSeverity(item) !== complianceSeverityFilter
      ) {
        return false;
      }
      if (promptProfileFilter !== "all" && item.prompt_profile !== promptProfileFilter) {
        return false;
      }
      if (skillFilter !== "all" && item.skill_id !== skillFilter) {
        return false;
      }
      if (
        weakSkillFilter !== "all" &&
        !(item.weak_subskills ?? []).includes(weakSkillFilter) &&
        !(item.priority_subskills ?? []).includes(weakSkillFilter)
      ) {
        return false;
      }
      return true;
    });
  }, [
    complianceSeverityFilter,
    difficultyFilter,
    finishReasonFilter,
    personaFilter,
    promptProfileFilter,
    query,
    scenarioFilter,
    scenarioLookup,
    scoreBandFilter,
    skillFilter,
    snapshot,
    weakSkillFilter,
  ]);

  const historyGroups = useMemo<HistoryGroup[]>(() => {
    const groups = new Map<string, ProgressHistoryItem[]>();
    const orderedKeys: string[] = [];
    const dateOrderedItems = [...filteredHistory].sort(
      (left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime()
    );

    for (const item of dateOrderedItems) {
      const key = formatDateKey(item.timestamp);
      if (!groups.has(key)) {
        groups.set(key, []);
        orderedKeys.push(key);
      }
      groups.get(key)?.push(item);
    }

    return orderedKeys.map((dateKey) => {
      const items = sortHistoryItems(groups.get(dateKey) ?? [], sortMode);
      return {
        dateKey,
        dateLabel: formatDateLabel(items[0]?.timestamp ?? dateKey),
        items,
      };
    });
  }, [filteredHistory, sortMode]);

  const pagedGroups = useMemo(() => {
    const startIndex = (currentPage - 1) * GROUPS_PER_PAGE;
    return historyGroups.slice(startIndex, startIndex + GROUPS_PER_PAGE);
  }, [currentPage, historyGroups]);

  const totalPages = Math.max(1, Math.ceil(historyGroups.length / GROUPS_PER_PAGE));
  const pageNumbers = visiblePageNumbers(currentPage, totalPages);
  const lastVisiblePage = pageNumbers.length > 0 ? pageNumbers[pageNumbers.length - 1] : 1;

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const currentRouteState = useMemo<RecordsRouteState>(() => {
    return {
      activeLearnerId,
      complianceSeverityFilter,
      currentPage,
      difficultyFilter,
      finishReasonFilter,
      personaFilter,
      promptProfileFilter,
      query,
      scoreBandFilter,
      scenarioFilter,
      sortMode,
      weakSkillFilter,
    };
  }, [
    activeLearnerId,
    complianceSeverityFilter,
    currentPage,
    difficultyFilter,
    finishReasonFilter,
    personaFilter,
    promptProfileFilter,
    query,
    scoreBandFilter,
    scenarioFilter,
    sortMode,
    weakSkillFilter,
  ]);

  const currentQueryString = searchParams?.toString() ?? "";
  const nextQueryString = useMemo(() => buildRecordsQueryString(currentRouteState), [currentRouteState]);

  useEffect(() => {
    if (nextQueryString === currentQueryString) {
      return;
    }
    router.replace(nextQueryString ? `${pathname}?${nextQueryString}` : pathname, { scroll: false });
  }, [currentQueryString, nextQueryString, pathname, router]);

  const averageScore = useMemo(() => {
    const records = snapshot?.recent_history ?? [];
    if (records.length === 0) {
      return 0;
    }
    return Math.round(records.reduce((sum, item) => sum + item.overall_score, 0) / records.length);
  }, [snapshot]);

  const bestRecord = useMemo(() => {
    const records = snapshot?.recent_history ?? [];
    if (records.length === 0) {
      return null;
    }
    return [...records].sort((left, right) => right.overall_score - left.overall_score)[0] ?? null;
  }, [snapshot]);

  const latestRecord = snapshot?.recent_history.at(-1) ?? null;
  const featuredRecommendation = snapshot?.practice_path?.[0] ?? snapshot?.latest_recommendations[0] ?? null;

  const buildRecordHref = (
    sessionId: string,
    overrides?: {
      complianceSeverity?: string | null;
      weakSkill?: string | null;
      finishReason?: string | null;
      promptProfile?: string | null;
      scoreBand?: string | null;
      scenarioId?: string | null;
    }
  ) => {
    const params = new URLSearchParams();
    const activeScenarioId =
      overrides?.scenarioId ??
      (scenarioFilter !== "all" ? scenarioFilter : null);
    if (activeScenarioId) {
      params.set("scenario", activeScenarioId);
      params.set("scenario_filter", activeScenarioId);
    }
    const activeWeakSkill =
      overrides?.weakSkill === null
        ? null
        : overrides?.weakSkill ?? (weakSkillFilter !== "all" ? weakSkillFilter : null);
    if (activeWeakSkill) {
      params.set("weak_skill", activeWeakSkill);
    }
    const activeFinishReason =
      overrides?.finishReason === null
        ? null
        : overrides?.finishReason ?? (finishReasonFilter !== "all" ? finishReasonFilter : null);
    if (activeFinishReason) {
      params.set("finish_reason", activeFinishReason);
    }
    const activeScoreBand =
      overrides?.scoreBand === null
        ? null
        : overrides?.scoreBand ?? (scoreBandFilter !== "all" ? scoreBandFilter : null);
    if (activeScoreBand) {
      params.set("score_band", activeScoreBand);
    }
    const activeComplianceSeverity =
      overrides?.complianceSeverity === null
        ? null
        : overrides?.complianceSeverity ??
          (complianceSeverityFilter !== "all" ? complianceSeverityFilter : null);
    if (activeComplianceSeverity) {
      params.set("compliance_severity", activeComplianceSeverity);
    }
    const activePromptProfile =
      overrides?.promptProfile === null
        ? null
        : overrides?.promptProfile ?? (promptProfileFilter !== "all" ? promptProfileFilter : null);
    if (activePromptProfile) {
      params.set("prompt_profile", activePromptProfile);
    }
    const queryString = params.toString();
    return queryString ? `/records/${sessionId}?${queryString}` : `/records/${sessionId}`;
  };

  const startScenario = async (scenarioId: string) => {
    const targetLearnerId = snapshot?.learner_id ?? learnerId.trim();
    const resolvedLearnerId = targetLearnerId || DEFAULT_LEARNER_ID;
    setStartingScenarioId(scenarioId);
    setError(null);
    setStartError(null);
    try {
      const data = await startRuntimeSession(
        resolvedLearnerId,
        scenarioId,
        {
          orgId,
          viewerRole,
        },
        i18n.language
      );
      startRouteTransition(() => {
        router.push(`/sessions/${data.session_id}?scenario=${scenarioId}`);
      });
    } catch (startError) {
      const parsed = parseStartSessionError(startError, "Unknown scenario start error");
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
    const targetOrgId = startError.orgId || orgId || "local";
    setInstallingSkill(true);
    setError(null);
    try {
      await installOrgSkill(targetOrgId, startError.skillId);
      setStartError(null);
      setError(t("marketplace.installSuccess"));
    } catch (installError) {
      const message = installError instanceof Error ? installError.message : t("marketplace.installFailed");
      setError(`${t("marketplace.installFailed")}: ${message}`);
    } finally {
      setInstallingSkill(false);
    }
  }, [orgId, startError, t]);

  return (
    <section className="dashboard-page">
      {/* ─── Hero section ─── */}
      <div className="records-hero">
        <div className="records-hero-left">
          <div className="records-hero-icon">
            <AppIcon className="icon-lg" name="clipboard" />
          </div>
          <div className="records-hero-copy">
            <h1>{t("records.heroTitle")}</h1>
            <p>{t("records.heroSubtitle")}</p>
          </div>
        </div>
        {viewerRole && (LEARNER_DATA_ROLES as readonly string[]).includes(viewerRole) && (
          <div className="records-hero-right">
            <select
              className="compact-select"
              onChange={(event) => {
                const selectedId = event.target.value;
                if (selectedId !== activeLearnerId) {
                  setCurrentPage(1);
                }
                setLearnerId(selectedId);
                void loadRecords(selectedId);
              }}
              value={learnerId}
            >
              {MOCK_USERS.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {startError ? (
        <StartSessionErrorBanner
          canInstall={canManageSkillInstall(viewerRole)}
          error={startError}
          installBusy={installingSkill}
          onInstall={() => {
            void installMissingSkill();
          }}
        />
      ) : error ? (
        <div className="error-banner">
          {/403|forbidden|restricted|denied/i.test(error)
            ? t("restricted.summaryOnly")
            : error}
        </div>
      ) : null}

      {snapshot ? (
        <>
          <section className="review-hero-card surface-card">
            <div className="review-hero-main">
              <div className="review-hero-icon">
                <AppIcon className="icon-xl icon-brand" name="doc" />
              </div>
              <div className="review-hero-copy">
                <h2>{snapshot.learner_id}</h2>
                <div className="review-meta-row">
                  <span>{t("records.lastUpdate")}{formatTimestamp(snapshot.updated_at)}</span>
                  <span>{t("records.recentScenario")}{latestRecord?.scenario_title ?? snapshot.coach_memory.last_session?.scenario_title ?? "-"}</span>
                </div>
              </div>
            </div>

            <div className="review-hero-stats">
              <article>
                <span>{t("records.totalSessions")}</span>
                <strong>{snapshot.total_sessions}</strong>
              </article>
              <article>
                <span>{t("records.averageScore")}</span>
                <strong>{averageScore} / 100</strong>
              </article>
              <article>
                <span>{t("records.bestScore")}</span>
                <strong>{bestRecord?.overall_score ?? "-"} / 100</strong>
              </article>
              <button
                className="primary-button hero-button"
                disabled={!featuredRecommendation || startingScenarioId !== null || isRoutePending}
                onClick={() =>
                  featuredRecommendation && void startScenario(featuredRecommendation.scenario_id)
                }
                type="button"
              >
                <AppIcon className="icon-sm" name="play" />
                <span>{startingScenarioId || isRoutePending ? t("records.starting") : t("records.startNew")}</span>
              </button>
            </div>
          </section>

          {latestRecord ? (
            <section className="record-spotlight-card surface-card">
              <ThumbnailArtwork
                className="record-spotlight-thumb"
                variant={scenarioArtVariant(latestRecord.scenario_id, latestRecord.priority_subskills ?? latestRecord.weak_subskills ?? [])}
              />
              <div className="record-spotlight-main">
                <div className="section-header">
                  <div className="section-title">
                    <AppIcon className="icon-md icon-brand" name="calendar" />
                    <span>{t("records.latestSummary")}</span>
                  </div>
                  <span className="section-chip">{formatTimestamp(latestRecord.timestamp)}</span>
                </div>
                <div className="record-spotlight-copy">
                  <h3>{latestRecord.scenario_title ?? latestRecord.scenario_id}</h3>
                  <div className="record-spotlight-meta">
                    <span>
                      <AppIcon className="icon-sm icon-brand" name="doctor" />
                      {latestRecord.persona_label ?? t("records.unlabeledPersona")}
                    </span>
                    <span>
                      <AppIcon className="icon-sm icon-brand" name="spark" />
                      {difficultyStars(latestRecord.difficulty ?? scenarioLookup[latestRecord.scenario_id]?.difficulty ?? "medium")}
                    </span>
                    <span>
                      <AppIcon className="icon-sm icon-brand" name="target" />
                      {latestRecord.overall_score} / 100
                    </span>
                    <span>
                      <AppIcon className="icon-sm icon-brand" name="flag" />
                      <Link
                        href={buildRecordHref(latestRecord.session_id, {
                          finishReason: latestRecord.finish_reason ?? null,
                          scenarioId: latestRecord.scenario_id,
                        })}
                      >
                        {finishReasonLabel(latestRecord.finish_reason)}
                      </Link>
                    </span>
                  </div>
                  <div className="record-spotlight-grid">
                    <div className="record-score-block">
                      <div className="record-score-line">
                        <strong>{latestRecord.overall_score}</strong>
                        <span>/ 100</span>
                      </div>
                      <div className={`progress-bar compact${latestRecord.overall_score < 55 ? " warn" : ""}`}>
                        <span style={{ width: `${clampPercent(latestRecord.overall_score)}%` }} />
                      </div>
                    </div>
                    <div className="record-copy-list">
                      <div className="record-label-row">
                        <span>{t("records.mainWeakness")}</span>
                        <div className="tag-list">
                          {(latestRecord.priority_subskills ?? latestRecord.weak_subskills ?? []).slice(0, 3).map((skill) => (
                            <Link
                              className="warning-tag"
                              href={buildRecordHref(latestRecord.session_id, {
                                weakSkill: skill,
                                scenarioId: latestRecord.scenario_id,
                              })}
                              key={`latest-${skill}`}
                            >
                              {subskillLabel(skill)}
                            </Link>
                          ))}
                        </div>
                      </div>
                      <div className="record-label-row">
                        <span>{t("records.sessionSignals")}</span>
                        <div className="tag-list">
                          <span className="mini-tag">{overallBandLabel(resolveOverallBand(latestRecord))}</span>
                          {resolveComplianceSeverity(latestRecord) ? (
                            <span className="mini-tag">
                              {complianceSeverityLabel(resolveComplianceSeverity(latestRecord))}
                            </span>
                          ) : null}
                          {latestRecord.prompt_profile ? (
                            <span className="mini-tag">{latestRecord.prompt_profile}</span>
                          ) : null}
                        </div>
                      </div>
                      <div className="record-diagnosis-list">
                        {(latestRecord.diagnosis_summaries ?? []).slice(0, 2).map((summary, index) => (
                          <p key={`latest-summary-${index}`}>{summary}</p>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="record-actions">
                <Link
                  className="ghost-button full-button"
                  href={buildRecordHref(latestRecord.session_id, { scenarioId: latestRecord.scenario_id })}
                >
                  {t("records.viewRecord")}
                </Link>
                <Link className="primary-button full-button" href={`/records/${latestRecord.session_id}/review`}>
                  {t("records.viewReview")}
                </Link>
              </div>
            </section>
          ) : null}

          <section className="panel surface-card records-filter-bar">
            <div className="records-filter-search">
              <AppIcon className="icon-sm filter-icon" name="search" />
              <input
                className="filter-input records-search-input"
                onChange={(event) => {
                  setCurrentPage(1);
                  setQuery(event.target.value);
                }}
                placeholder={t("records.searchPlaceholder")}
                value={query}
              />
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.difficultyFilter")}</span>
              <div className="chip-group">
                {[
                  { value: "all", label: t("records.all") },
                  { value: "easy", label: t("records.easy") },
                  { value: "medium", label: t("records.medium") },
                  { value: "hard", label: t("records.hard") },
                ].map((item) => (
                  <button
                    key={item.value}
                    className={`filter-chip${difficultyFilter === item.value ? " is-active" : ""}`}
                    onClick={() => {
                      setCurrentPage(1);
                      setDifficultyFilter(item.value as "all" | "easy" | "medium" | "hard");
                    }}
                    type="button"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.scenarioFilter")}</span>
              <div className="filter-select-wrap">
                <select
                  className="filter-select"
                  onChange={(event) => {
                    setCurrentPage(1);
                    setScenarioFilter(event.target.value);
                  }}
                  value={scenarioFilter}
                >
                  <option value="all">{t("records.allScenarios")}</option>
                  {scenarioOptions.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.personaFilter")}</span>
              <div className="filter-select-wrap">
                <select
                  className="filter-select"
                  onChange={(event) => {
                    setCurrentPage(1);
                    setPersonaFilter(event.target.value);
                  }}
                  value={personaFilter}
                >
                  <option value="all">{t("records.allPersonas")}</option>
                  {personaOptions.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.scoreBandFilter")}</span>
              <div className="filter-select-wrap">
                <select
                  className="filter-select"
                  onChange={(event) => {
                    setCurrentPage(1);
                    setScoreBandFilter(event.target.value);
                  }}
                  value={scoreBandFilter}
                >
                  <option value="all">{t("records.allScoreBands")}</option>
                  {scoreBandOptions.map((item) => (
                    <option key={item} value={item}>
                      {overallBandLabel(item)}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.finishReasonFilter")}</span>
              <div className="filter-select-wrap">
                <select
                  className="filter-select"
                  onChange={(event) => {
                    setCurrentPage(1);
                    setFinishReasonFilter(event.target.value);
                  }}
                  value={finishReasonFilter}
                >
                  <option value="all">{t("records.allFinishReasons")}</option>
                  {finishReasonOptions.map((item) => (
                    <option key={item} value={item}>
                      {finishReasonLabel(item)}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.complianceSeverityFilter")}</span>
              <div className="filter-select-wrap">
                <select
                  className="filter-select"
                  onChange={(event) => {
                    setCurrentPage(1);
                    setComplianceSeverityFilter(event.target.value);
                  }}
                  value={complianceSeverityFilter}
                >
                  <option value="all">{t("records.allComplianceLevels")}</option>
                  {complianceSeverityOptions.map((item) => (
                    <option key={item} value={item}>
                      {complianceSeverityLabel(item)}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.promptProfileFilter")}</span>
              <div className="filter-select-wrap">
                <select
                  className="filter-select"
                  onChange={(event) => {
                    setCurrentPage(1);
                    setPromptProfileFilter(event.target.value);
                  }}
                  value={promptProfileFilter}
                >
                  <option value="all">{t("records.allPromptProfiles")}</option>
                  {promptProfileOptions.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </div>

            <div className="records-filter-group">
              <span className="records-filter-label">{t("records.weakSkillFilter")}</span>
              <div className="filter-select-wrap">
                <select
                  className="filter-select"
                  onChange={(event) => {
                    setCurrentPage(1);
                    setWeakSkillFilter(event.target.value);
                  }}
                  value={weakSkillFilter}
                >
                  <option value="all">{t("records.allSkills")}</option>
                  {weakSkillOptions.map((item) => (
                    <option key={item} value={item}>
                      {subskillLabel(item)}
                    </option>
                  ))}
                </select>
                <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
              </div>
            </div>

            {skillOptions.length > 0 ? (
              <div className="records-filter-group">
                <span className="records-filter-label">{t("records.skillFilter")}</span>
                <div className="filter-select-wrap">
                  <select
                    className="filter-select"
                    onChange={(event) => {
                      setCurrentPage(1);
                      setSkillFilter(event.target.value);
                    }}
                    value={skillFilter}
                  >
                    <option value="all">{t("records.allSkills")}</option>
                    {skillOptions.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                  <AppIcon className="icon-sm filter-select-arrow" name="chevron-down" />
                </div>
              </div>
            ) : null}

            <button
              className="ghost-button records-clear-btn"
              onClick={() => {
                setCurrentPage(1);
                setQuery("");
                setScoreBandFilter("all");
                setDifficultyFilter("all");
                setScenarioFilter("all");
                setPersonaFilter("all");
                setFinishReasonFilter("all");
                setComplianceSeverityFilter("all");
                setPromptProfileFilter("all");
                setWeakSkillFilter("all");
                setSkillFilter("all");
                setSortMode("newest");
              }}
              type="button"
            >
              <AppIcon className="icon-sm" name="refresh" />
              <span>{t("records.clearFilters")}</span>
            </button>
          </section>

          <div className="catalog-toolbar">
            <strong>
              {t("records.totalRecords", { count: filteredHistory.length })}
              <span className="records-toolbar-subtle">{t("records.trainingDays", { count: historyGroups.length })}</span>
            </strong>
            <div className="catalog-toolbar-actions">
              <label className="catalog-sort">
                <span>{t("records.groupSort")}</span>
                <select
                  onChange={(event) => {
                    setCurrentPage(1);
                    setSortMode(event.target.value as "newest" | "score_desc" | "score_asc");
                  }}
                  value={sortMode}
                >
                  <option value="newest">{t("records.sortTime")}</option>
                  <option value="score_desc">{t("records.sortHigh")}</option>
                  <option value="score_asc">{t("records.sortLow")}</option>
                </select>
              </label>
              <span className="section-chip">
                {t("records.pageCount", { current: currentPage, total: totalPages })}
              </span>
            </div>
          </div>

          <div className="catalog-layout">
            <div className="records-list">
              {pagedGroups.length === 0 ? (
                <div className="placeholder-block surface-card">
                  <strong>{loading ? t("records.loadingRecords") : t("records.noRecordsMatch")}</strong>
                  <p>
                    {loading
                      ? t("records.syncingSnapshot")
                      : t("records.adjustFilters")}
                  </p>
                  <div className="placeholder-actions">
                    <Link className="primary-button" href="/scenarios">
                      {t("records.goTrain")}
                    </Link>
                    <Link className="ghost-button" href="/progress">
                      {t("records.viewProgress")}
                    </Link>
                  </div>
                </div>
              ) : (
                <>
                  {pagedGroups.map((group) => (
                    <section className="record-date-section" key={group.dateKey}>
                      <div className="record-date-divider">
                        <strong>{group.dateLabel}</strong>
                        <span>{group.items.length} 条记录</span>
                      </div>

                      <div className="records-list">
                        {group.items.map((item) => {
                          const scenario = scenarioLookup[item.scenario_id];
                          const difficulty = item.difficulty ?? scenario?.difficulty ?? "medium";
                          const overallBand = resolveOverallBand(item);
                          const complianceSeverity = resolveComplianceSeverity(item);
                          const focusSubskills = [
                            ...(item.priority_subskills ?? []),
                            ...(item.weak_subskills ?? []),
                            ...(scenario?.focus_subskills ?? []),
                          ];
                          const primaryTags = (item.priority_subskills ?? item.weak_subskills ?? []).slice(0, 3);

                          return (
                            <article className="record-card" key={item.session_id}>
                              <ThumbnailArtwork
                                className="record-thumb"
                                variant={scenarioArtVariant(item.scenario_id, focusSubskills)}
                              />

                              <div className="record-card-body">
                                <div className="record-card-head">
                                    <div className="record-card-title">
                                    <h3>
                                      <Link href={buildRecordHref(item.session_id, { scenarioId: item.scenario_id })}>
                                        {item.scenario_title ?? scenario?.title ?? item.scenario_id}
                                      </Link>
                                    </h3>
                                    <div className="record-meta-row">
                                      <span>
                                        <AppIcon className="icon-sm icon-brand" name="calendar" />
                                        {formatTimestamp(item.timestamp)}
                                      </span>
                                      <span>
                                        <AppIcon className="icon-sm icon-brand" name="doctor" />
                                        {item.persona_label ?? scenario?.persona_label ?? t("records.unlabeledPersona")}
                                      </span>
                                      <span>
                                        <AppIcon className="icon-sm icon-brand" name="spark" />
                                        {difficultyLabel(difficulty)}
                                      </span>
                                      <span>
                                        <AppIcon className="icon-sm icon-brand" name="flag" />
                                        <Link href={buildRecordHref(item.session_id, { finishReason: item.finish_reason ?? null, scenarioId: item.scenario_id })}>
                                          {finishReasonLabel(item.finish_reason)}
                                        </Link>
                                      </span>
                                    </div>
                                  </div>
                                  <span className="section-chip">+{item.exp_gain ?? 0} EXP</span>
                                </div>

                                <div className="record-card-grid">
                                  <div className="record-score-block">
                                    <div className="record-score-line">
                                      <strong>{item.overall_score}</strong>
                                      <span>/ 100</span>
                                    </div>
                                    <div className={`progress-bar compact${item.overall_score < 55 ? " warn" : ""}`}>
                                      <span style={{ width: `${clampPercent(item.overall_score)}%` }} />
                                    </div>
                                  </div>

                                  <div className="record-copy-list">
                                    <div className="record-label-row">
                                      <span>难度</span>
                                      <strong>{difficultyStars(difficulty)}</strong>
                                    </div>
                                    <div className="record-label-row">
                                      <span>{t("records.sessionSignals")}</span>
                                      <div className="tag-list">
                                        <span className="mini-tag">{overallBandLabel(overallBand)}</span>
                                        {complianceSeverity ? (
                                          <span className="mini-tag">
                                            {complianceSeverityLabel(complianceSeverity)}
                                          </span>
                                        ) : null}
                                        {item.prompt_profile ? (
                                          <span className="mini-tag">{item.prompt_profile}</span>
                                        ) : null}
                                      </div>
                                    </div>
                                    <div className="record-label-row">
                                      <span>{t("records.mainWeakness")}</span>
                                      <div className="tag-list">
                                        {primaryTags.length > 0 ? (
                                          primaryTags.map((skill) => (
                                            <Link
                                              className="warning-tag"
                                              href={buildRecordHref(item.session_id, {
                                                weakSkill: skill,
                                                scenarioId: item.scenario_id,
                                              })}
                                              key={`${item.session_id}-${skill}`}
                                            >
                                              {subskillLabel(skill)}
                                            </Link>
                                          ))
                                        ) : (
                                          <span className="mini-tag">{t("records.noWeakness")}</span>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                </div>

                                <div className="record-diagnosis-list">
                                  {(item.diagnosis_summaries ?? []).length > 0 ? (
                                    (item.diagnosis_summaries ?? []).slice(0, 2).map((summary, index) => (
                                      <p key={`${item.session_id}-${index}`}>{summary}</p>
                                    ))
                                  ) : (
                                    <p>{t("records.noDiagnosis")}</p>
                                  )}
                                </div>
                              </div>

                              <div className="record-actions">
                                <Link
                                  className="ghost-button full-button"
                                  href={buildRecordHref(item.session_id, { scenarioId: item.scenario_id })}
                                >
                                  {t("records.viewRecord")}
                                </Link>
                                <Link className="primary-button full-button" href={`/records/${item.session_id}/review`}>
                                  {t("records.viewReview")}
                                </Link>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  ))}

                  <div className="pagination-card">
                    <button
                      className="pager-button"
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage((value) => Math.max(1, value - 1))}
                      type="button"
                    >
                      {t("records.prevPage")}
                    </button>
                    <div className="pager-group">
                      {pageNumbers[0] > 1 ? <span className="pager-ellipsis">…</span> : null}
                      {pageNumbers.map((page) => (
                        <button
                          key={page}
                          className={`pager-chip${page === currentPage ? " is-active" : ""}`}
                          onClick={() => setCurrentPage(page)}
                          type="button"
                        >
                          {page}
                        </button>
                      ))}
                      {lastVisiblePage < totalPages ? <span className="pager-ellipsis">…</span> : null}
                    </div>
                    <button
                      className="pager-button"
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage((value) => Math.min(totalPages, value + 1))}
                      type="button"
                    >
                      {t("records.nextPage")}
                    </button>
                  </div>
                </>
              )}
            </div>

            <aside className="catalog-side-panel surface-card record-side-stack">
              <div className="section-header">
                <div className="section-title">
                  <AppIcon className="icon-md icon-brand" name="star" />
                  <span>{t("records.recordInsights")}</span>
                </div>
              </div>

              <div className="side-note-block">
                <strong>{t("records.recurringWeakness")}</strong>
                <div className="record-cluster-list">
                  {(snapshot.weakness_clusters ?? []).slice(0, 3).map((cluster) => (
                    <article className="record-cluster-row" key={cluster.cluster_id}>
                      <div className="tag-list">
                        {cluster.subskills.slice(0, 3).map((skill) => (
                          <span className="warning-tag" key={`${cluster.cluster_id}-${skill}`}>
                            {subskillLabel(skill)}
                          </span>
                        ))}
                      </div>
                      <small>{t("records.occurCount", { count: cluster.occurrences })}</small>
                    </article>
                  ))}
                  {(snapshot.weakness_clusters ?? []).length === 0 ? (
                    <div className="placeholder-inline">{t("records.noCluster")}</div>
                  ) : null}
                </div>
              </div>

              <div className="side-note-block">
                <strong>{t("records.suggestActions")}</strong>
                <ul className="side-bullet-list">
                  {(snapshot.coach_memory.next_actions ?? []).slice(0, 3).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                  {snapshot.coach_memory.summary ? <li>{snapshot.coach_memory.summary}</li> : null}
                </ul>
              </div>

              <div className="side-note-block">
                <strong>{t("records.nextRecommend")}</strong>
                {featuredRecommendation ? (
                  <>
                    <div className="side-featured-card">
                      <ThumbnailArtwork
                        className="side-featured-thumb"
                        variant={scenarioArtVariant(
                          featuredRecommendation.scenario_id,
                          featuredRecommendation.target_subskills
                        )}
                      />
                      <div className="side-featured-copy">
                        <h4>{featuredRecommendation.title}</h4>
                        <p>难度：{difficultyStars(featuredRecommendation.difficulty)}</p>
                        <small>
                          {t("records.focusTraining")}
                          {featuredRecommendation.target_subskills.map((item) => subskillLabel(item)).join("、")}
                        </small>
                      </div>
                    </div>
                    <button
                      className="primary-button full-button"
                      disabled={startingScenarioId === featuredRecommendation.scenario_id || isRoutePending}
                      onClick={() => void startScenario(featuredRecommendation.scenario_id)}
                      type="button"
                    >
                      <AppIcon className="icon-sm" name="play" />
                      <span>
                        {startingScenarioId === featuredRecommendation.scenario_id || isRoutePending
                          ? t("records.starting")
                          : t("records.startNew")}
                      </span>
                    </button>
                  </>
                ) : (
                  <div className="placeholder-inline">{t("records.noRecommend")}</div>
                )}
              </div>
            </aside>
          </div>
        </>
      ) : (
        <div className="placeholder-block surface-card">
          <strong>{loading ? t("records.loadingRecords") : t("records.noRecordsAvailable")}</strong>
          <p>{loading ? t("records.syncingSnapshot") : t("records.completeOneRound")}</p>
          <div className="placeholder-actions">
            <Link className="primary-button" href="/scenarios">
              {t("records.startNew")}
            </Link>
            <Link className="ghost-button" href="/progress">
              {t("records.viewProgress")}
            </Link>
          </div>
        </div>
      )}
    </section>
  );
}
