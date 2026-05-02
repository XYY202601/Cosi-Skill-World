export function difficultyLabel(value: string): string {
  if (value === "easy") return "初级";
  if (value === "medium") return "中级";
  if (value === "hard") return "高级";
  return value || "未知";
}

export function difficultyStars(value: string): string {
  const count = value === "easy" ? 2 : value === "hard" ? 4 : 3;
  return "★".repeat(count) + "☆".repeat(5 - count);
}

export const DEFAULT_SUBSKILL_ORDER = [
  "preparation",
  "opening",
  "profiling",
  "scientific_delivery",
  "need_discovery",
  "objection_handling",
  "closing_followup",
];

const SUBSKILL_LABELS: Record<string, string> = {
  preparation: "Preparation",
  opening: "Opening",
  profiling: "Profiling",
  scientific_delivery: "Scientific Delivery",
  need_discovery: "Need Discovery",
  objection_handling: "Objection Handling",
  closing_follow_up: "Closing & Follow-up",
  closing_followup: "Closing & Follow-up",
};

export function subskillLabel(value: string): string {
  return SUBSKILL_LABELS[value] ?? value.replaceAll("_", " ");
}

const ATTITUDE_LABELS: Record<string, string> = {
  skeptical: "质疑型",
  guarded: "谨慎型",
  dismissive: "低兴趣型",
  pragmatic: "务实型",
  concerned: "安全优先型",
  receptive: "开放型",
  loyal: "忠诚型",
};

export function attitudeLabel(value: string | null | undefined): string {
  if (!value) return "未标注";
  return ATTITUDE_LABELS[value] ?? value.replaceAll("_", " ");
}

const TIME_PRESSURE_LABELS: Record<string, string> = {
  high: "高时压",
  medium: "中等时压",
  low: "低时压",
};

export function timePressureLabel(value: string | null | undefined): string {
  if (!value) return "时压未知";
  return TIME_PRESSURE_LABELS[value] ?? value.replaceAll("_", " ");
}

export function statusLabel(value: string): string {
  if (value === "initialized") return "待开始";
  if (value === "running") return "进行中";
  if (value === "awaiting_finish") return "待结束";
  if (value === "finalized") return "已完成";
  return value || "未知";
}

export function phaseLabel(value: string): string {
  if (value === "opening") return "开场";
  if (value === "discovery") return "需求挖掘";
  if (value === "evidence") return "信息传递";
  if (value === "closing") return "收尾";
  if (value === "safety") return "安全处理";
  return value || "未知阶段";
}

const FINISH_REASON_LABELS: Record<string, string> = {
  manual_finish: "手动结束",
  learner_requested_finish: "主动结束",
  director_signaled_completion: "达到结束条件",
  max_turns_reached: "达到最大轮次",
};

export function finishReasonLabel(value: string | null | undefined): string {
  if (!value) return "未标注";
  return FINISH_REASON_LABELS[value] ?? value.replaceAll("_", " ");
}

const OVERALL_BAND_LABELS: Record<string, string> = {
  advanced: "高水平",
  proficient: "熟练",
  developing: "发展中",
  emerging: "起步中",
  excellent: "优秀",
  strong: "强",
  functional: "达标",
  critical_gap: "关键缺口",
};

export function overallBandLabel(value: string | null | undefined): string {
  if (!value) return "未标注";
  return OVERALL_BAND_LABELS[value] ?? value.replaceAll("_", " ");
}

const COMPLIANCE_SEVERITY_LABELS: Record<string, string> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
  positive: "正向",
};

export function complianceSeverityLabel(value: string | null | undefined): string {
  if (!value) return "未标注";
  return COMPLIANCE_SEVERITY_LABELS[value] ?? value.replaceAll("_", " ");
}

const ACTION_LABELS: Record<string, string> = {
  continue: "继续当前节奏",
  finish_session: "结束本轮会话",
  ask_one_targeted_discovery_question: "先问一个更具体的探查问题",
  shorten_opening_and_get_permission: "缩短开场并先取得医生许可",
  anchor_to_evidence_and_patient_segment: "用证据和患者分层重新锚定信息",
  cite_endpoint_safety_and_patient_segment: "补充终点、安全信息和患者分层",
  tie_message_to_current_patient_segment: "把信息拉回当前患者场景",
  state_concrete_next_step: "明确下一步行动和跟进方式",
  state_micro_commitment_and_followup: "给出一个更小的下一步和跟进安排",
  ask_about_formulary_barrier: "先确认真实的准入或流程障碍",
  ask_decision_criteria_before_comparison: "先确认决策标准，再做事实比较",
  acknowledge_prior_rejection_and_offer_update: "先回应上次拒绝，再给出新的相关性",
  switch_to_safety_followup: "立即切换到 AE / 安全跟进模式",
  state_reporting_process_and_followup: "说明 AE 报告流程和后续跟进",
  offer_low_risk_next_step: "提供一个更小、更低风险的下一步",
  reestablish_practical_need_before_pitch: "先重新建立临床需求和相关性",
};

export function actionLabel(value: string | null | undefined): string {
  if (!value) return "保持当前节奏";
  return ACTION_LABELS[value] ?? value.replaceAll("_", " ");
}

const EVENT_LABELS: Record<string, string> = {
  opening_overlong: "开场过长",
  low_information_turn: "本轮信息量不足",
  patient_segment_not_specified: "没有明确患者分层",
  opening_missing_permission: "未先取得医生许可",
  evidence_not_addressed: "没有正面回应证据要求",
  evidence_detail_missing: "证据缺少终点 / 安全 / 用药场景细节",
  evidence_dump_without_use_case: "只在堆证据，没有连接患者使用场景",
  unsupported_claim_without_evidence: "给出了没有证据支撑的临床主张",
  patient_use_case_not_defined: "没有把证据落到明确患者场景",
  safety_first_context: "医生处于安全优先场景",
  safety_reporting_not_started: "还没有进入 AE / 报告流程",
  followup_process_not_stated: "没有说明 AE 跟进和上报路径",
  practical_relevance_not_established: "尚未建立临床相关性",
  need_signal_not_established: "还没有建立真实需求信号",
  prior_rejection_not_acknowledged: "没有承接上次拒绝背景",
  no_new_relevance_after_rejection: "没有说明这次新的相关性",
  formulary_barrier_not_explored: "尚未探查准入 / 流程障碍",
  decision_criteria_not_explored: "还没有先问清医生的决策标准",
  unsupported_competitor_comparison: "做了缺少依据的竞品比较",
  commitment_too_large_for_cautious_persona: "对谨慎型医生推进过大",
  unrealistic_adoption_request: "提出了不符合当前系统约束的采用要求",
  closing_next_step_missing: "收尾时缺少明确下一步",
  micro_commitment_missing: "收尾时缺少一个足够小、可执行的微承诺",
  carryover_opening_gap: "仍然暴露上轮开场问题",
  time_pressure_not_respected: "没有体现医生时间压力",
  carryover_need_discovery_gap: "仍然暴露上轮需求挖掘问题",
  weak_profiling_signal: "没有探出关键需求或决策信号",
  discovery_question_missing: "缺少探查性问题",
  carryover_evidence_gap: "仍然暴露上轮证据传递问题",
  carryover_followup_gap: "仍然暴露上轮收尾跟进问题",
  max_turns_reached: "达到最大轮次",
};

export function eventLabel(value: string): string {
  return EVENT_LABELS[value] ?? value.replaceAll("_", " ");
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatClock(value: string | null | undefined): string {
  if (!value) return "--:--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleTimeString("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(start: string | null | undefined, end: string | null | undefined): string {
  if (!start || !end) return "-";
  const startedAt = new Date(start);
  const endedAt = new Date(end);
  if (Number.isNaN(startedAt.getTime()) || Number.isNaN(endedAt.getTime())) {
    return "-";
  }
  const minutes = Math.max(1, Math.round((endedAt.getTime() - startedAt.getTime()) / 60000));
  return `${minutes} 分钟`;
}

export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function scorePercent(score: number | null | undefined, maxScore = 5): number {
  if (typeof score !== "number" || !Number.isFinite(score) || maxScore <= 0) {
    return 0;
  }
  return clampPercent((score / maxScore) * 100);
}

export function turnProgressPercent(turnCount: number, maxTurns: number): number {
  if (!Number.isFinite(turnCount) || !Number.isFinite(maxTurns) || maxTurns <= 0) {
    return 0;
  }
  return clampPercent((turnCount / maxTurns) * 100);
}

export function sparklinePoints(values: number[], width: number, height: number): string {
  if (values.length === 0) {
    return "";
  }
  const max = Math.max(...values, 100);
  const min = Math.min(...values, 0);
  const range = Math.max(1, max - min);

  return values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function scenarioArtVariant(
  scenarioId: string,
  focusSubskills: string[] = []
): "meeting" | "presentation" | "analysis" | "conversation" | "growth" | "report" {
  const key = [scenarioId, ...focusSubskills].join(" ").toLowerCase();
  if (key.includes("objection") || key.includes("competitor") || key.includes("rejection")) {
    return "conversation";
  }
  if (key.includes("scientific") || key.includes("evidence")) {
    return "analysis";
  }
  if (key.includes("closing") || key.includes("follow")) {
    return "report";
  }
  if (key.includes("profiling") || key.includes("need")) {
    return "meeting";
  }
  if (key.includes("opening")) {
    return "presentation";
  }
  return "growth";
}
