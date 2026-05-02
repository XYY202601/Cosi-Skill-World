from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
import random
from typing import Any

from event_taxonomy import (
    analyze_turn_message,
    build_session_finalized_content,
    build_session_started_content,
    build_turn_event_content,
)
from persistence.interfaces import EventStore, ProgressStore, SessionStore
from providers import summarize_prompt_context
from runtime_context import DomainSessionContext, build_turn_id
from scenarios.asset_loader import DomainBundle, ScenarioRecord
from session_events import build_session_event_envelope
from services.progress_tracker import ProgressTracker, RECENT_HISTORY_LIMIT

DEMO_SEED_GENERATOR = "demo_seed_v3"
COMPREHENSIVE_TODAY_BATCH_GENERATOR = "demo_today_batch_v1"

@dataclass(frozen=True)
class DemoLearnerSpec:
    learner_id: str
    session_count: int
    active_day_span: int
    base_score: float
    growth_bias: float
    persistent_weaknesses: tuple[str, ...]
    strengths: tuple[str, ...]


@dataclass(frozen=True)
class CuratedSessionPlan:
    scenario_id: str
    overall_score: int
    weak_subskills: tuple[str, ...]
    strong_subskills: tuple[str, ...]
    finish_reason: str


DEMO_LEARNER_SPECS = (
    DemoLearnerSpec(
        learner_id="learner_demo_001",
        session_count=100,
        active_day_span=84,
        base_score=2.35,
        growth_bias=1.15,
        persistent_weaknesses=("need_discovery", "objection_handling", "opening"),
        strengths=("scientific_delivery", "closing_followup"),
    ),
    DemoLearnerSpec(
        learner_id="learner_demo_300",
        session_count=300,
        active_day_span=180,
        base_score=2.55,
        growth_bias=1.3,
        persistent_weaknesses=("profiling", "objection_handling"),
        strengths=("scientific_delivery", "opening"),
    ),
    DemoLearnerSpec(
        learner_id="learner_demo_1000",
        session_count=1000,
        active_day_span=420,
        base_score=2.75,
        growth_bias=1.45,
        persistent_weaknesses=("need_discovery", "closing_followup"),
        strengths=("scientific_delivery", "profiling"),
    ),
)

SCENARIO_TITLE_JA: dict[str, str] = {
    "adverse_event_followup_required": "有害事象報告後のフォローアップ面談",
    "busy_doctor_short_visit": "多忙な医師への短時間面談",
    "cautious_doctor_evidence_check": "慎重な医師へのエビデンス確認対応",
    "formulary_restriction_negotiation": "院内採用・フォーミュラリー制約への対応",
    "low_interest_doctor_intro_fail": "関心が薄い医師への導入立て直し",
    "new_product_adoption_barrier": "新製品導入に慎重な医師との面談",
    "revisit_after_prior_rejection": "前回見送り後の再提案面談",
    "skeptical_doctor_competitor_pressure": "競合比較を持ち出す医師への対応",
}

PERSONA_LABEL_JA: dict[str, str] = {
    "busy_clinician_neutral": "忙しい総合内科医",
    "evidence_first_specialist": "エビデンス重視の専門医",
    "low_interest_generalist": "関心が低い一般内科医",
    "competitor_loyal_specialist": "競合製品に忠実な専門医",
    "conservative_prescriber": "導入に慎重な処方医",
    "guarded_prior_rejection_doctor": "前回見送り経験のある警戒的な医師",
    "formulary_constrained_prescriber": "院内採用制約の強い処方医",
    "concerned_adverse_event_reporter": "有害事象を懸念する処方医",
}

SPECIALTY_LABEL_JA: dict[str, str] = {
    "general_internal_medicine": "総合内科",
    "specialist_outpatient": "専門外来",
    "general_practice": "一般内科",
    "specialist_prescriber": "専門医外来",
    "chronic_care_prescriber": "慢性疾患外来",
    "established_prescriber": "基幹病院外来",
    "institution_based_prescriber": "大学病院・院内採用管理",
    "active_prescriber": "外来処方医",
}

SUBSKILL_ACTIONS_JA: dict[str, str] = {
    "preparation": "面談前に訪問目的・患者像・使う根拠を1セットで整理して入る。",
    "opening": "冒頭10秒で面談許可と訪問目的を明確に伝える。",
    "profiling": "施設方針・患者背景・処方判断基準を1問で深掘りする。",
    "scientific_delivery": "患者像に結び付けて主要データを1点に絞って提示する。",
    "need_discovery": "未充足ニーズを確認してから製品価値に接続する。",
    "objection_handling": "懸念を先に受け止め、根拠を添えて具体的に返答する。",
    "closing_followup": "次回アクションとフォロー日時を具体化して締める。",
}

DIAGNOSIS_TEMPLATES_JA: dict[str, str] = {
    "preparation": "面談前提の整理が甘く、何を確認し何を持ち帰るかの設計がやや曖昧でした。",
    "opening": "導入時の許可取りと目的提示がやや曖昧で、面談の入り口に改善余地がありました。",
    "profiling": "医師の施設事情や処方背景の確認が浅く、判断基準の把握が十分ではありませんでした。",
    "scientific_delivery": "データ提示はあったものの、患者像との結び付けが弱く臨床的な納得感が不足しました。",
    "need_discovery": "未充足ニーズの確認が不足し、提案の必然性が十分に伝わっていませんでした。",
    "objection_handling": "異議への返答が総論寄りで、根拠を用いた具体的な応答まで届きませんでした。",
    "closing_followup": "次回アクションとフォローの約束が曖昧で、面談の収束が弱くなりました。",
}

STRENGTH_TEMPLATES_JA: dict[str, str] = {
    "preparation": "面談前提の整理ができており、会話の着地点がぶれませんでした。",
    "opening": "冒頭の導入が簡潔で、面談の目的が伝わりやすくなっていました。",
    "profiling": "医師の背景確認が的確で、会話の軸を早い段階で合わせられていました。",
    "scientific_delivery": "主要データの示し方が整理されており、要点が伝わりやすい構成でした。",
    "need_discovery": "医師の臨床課題を言語化できており、提案との接続が自然でした。",
    "objection_handling": "懸念に対する受け止め方が落ち着いており、対話が崩れませんでした。",
    "closing_followup": "次のアクションが具体的で、面談後の動きが明確でした。",
}

SCENARIO_OPENING_JA: dict[str, str] = {
    "adverse_event_followup_required": "先日の症例について、報告手順と確認事項を2点だけ整理したく伺いました。",
    "busy_doctor_short_visit": "本日は30秒だけお時間ください。先生の外来で該当しやすい患者像に絞ってお伝えします。",
    "cautious_doctor_evidence_check": "新しい追加データについて、先生が判断しやすいよう主要結果だけ端的に共有します。",
    "formulary_restriction_negotiation": "院内採用の条件を踏まえた上で、現実的な使い方をご相談したく伺いました。",
    "low_interest_doctor_intro_fail": "先生の診療で関係しそうな患者像に絞って、短く1点だけ確認させてください。",
    "new_product_adoption_barrier": "切り替えではなく、適した患者層を一緒に整理したく伺いました。",
    "revisit_after_prior_rejection": "前回のご意見を踏まえて、今回は新しいデータの部分だけ短く共有します。",
    "skeptical_doctor_competitor_pressure": "競合比較ではなく、先生が重視される判断基準を先に確認したいと思っています。",
}

SCENARIO_CHALLENGE_JA: dict[str, str] = {
    "adverse_event_followup_required": "まず必要情報と社内連携の流れを明確にしてください。",
    "busy_doctor_short_visit": "それはどの患者さんに関係する話ですか。",
    "cautious_doctor_evidence_check": "その差を示す主要エンドポイントは何ですか。",
    "formulary_restriction_negotiation": "採用条件や運用負荷も含めて現実的に説明できますか。",
    "low_interest_doctor_intro_fail": "正直、今の診療でそこまで困っていないのですが。",
    "new_product_adoption_barrier": "実際に切り替えるなら、どの患者層から考えるべきですか。",
    "revisit_after_prior_rejection": "前回との違いがどこにあるのか、そこを聞きたいです。",
    "skeptical_doctor_competitor_pressure": "現行治療と比べて、何が実務上の違いになるのでしょうか。",
}

SCENARIO_FOLLOWUP_JA: dict[str, str] = {
    "adverse_event_followup_required": "必要な確認項目を順に教えてください。対応の優先順位を合わせたいです。",
    "busy_doctor_short_visit": "その患者像で、先生は何を最も気にされますか。",
    "cautious_doctor_evidence_check": "有効性だけでなく、安全性と使い分けの視点も知りたいです。",
    "formulary_restriction_negotiation": "採用条件に照らすと、どの点が一番ハードルになりますか。",
    "low_interest_doctor_intro_fail": "もし関連するなら、どの患者さんからなら話を聞く価値がありますか。",
    "new_product_adoption_barrier": "導入を考えるなら、まずどの患者層から検討するのが現実的ですか。",
    "revisit_after_prior_rejection": "今回は前回より何が具体的に変わったのか、そこを整理したいです。",
    "skeptical_doctor_competitor_pressure": "比較するなら、先生は効果と運用のどちらを重視されますか。",
}

SCENARIO_CLOSE_JA: dict[str, str] = {
    "adverse_event_followup_required": "必要資料があれば送ってください。まずは報告を優先します。",
    "busy_doctor_short_visit": "要点は分かりました。資料だけ置いていってください。",
    "cautious_doctor_evidence_check": "詳細データを確認した上で、次回また議論しましょう。",
    "formulary_restriction_negotiation": "院内の条件を確認しつつ、次回もう一段具体化したいです。",
    "low_interest_doctor_intro_fail": "関連症例があれば、その時にもう一度聞かせてください。",
    "new_product_adoption_barrier": "対象患者が見えれば検討しやすいので、追加情報をお願いします。",
    "revisit_after_prior_rejection": "今回は以前より整理されていました。次回もう少し詳しく見ます。",
    "skeptical_doctor_competitor_pressure": "比較軸は分かりました。実データを確認しておきます。",
}

PATIENT_SEGMENTS = (
    "一次治療で導入可否を検討している患者さん",
    "副作用マネジメントに課題がある患者さん",
    "既存治療で十分な反応が得られていない患者さん",
    "高齢で合併症を抱える患者さん",
    "院内採用の条件に合致しやすい患者さん",
)

EVIDENCE_SNIPPETS = (
    "主要評価項目で一貫した改善傾向が示されました",
    "安全性プロファイルは既存治療と大きく乖離しませんでした",
    "実臨床に近い患者層でも使い分けの示唆が得られました",
    "サブグループ解析でも同方向の結果が確認されました",
)

NEXT_STEP_SNIPPETS = (
    "該当患者が出た時点で短い再面談をお願いする",
    "院内採用条件に沿って追加資料を共有する",
    "先生が重視される比較軸でデータを整理して持参する",
    "安全性データの要点を1枚にまとめて再確認する",
)

USER_OPENING_STRONG_JA = (
    "本日は30秒だけお時間ください。{patient_segment}に絞って1点だけ共有します。",
    "短く1点だけです。先生の外来で該当しやすい {patient_segment} について確認させてください。",
)

USER_OPENING_WEAK_JA = (
    "本日は新しい情報をご紹介したく伺いました。{patient_segment} にも関係すると思います。",
    "学会の話題も含めて共有です。{patient_segment} で使える可能性があります。",
)

USER_DISCOVERY_STRONG_JA = (
    "先生の施設では {patient_segment} で何を最も重視されますか。その前提で、{evidence}。",
    "まず判断基準を1点だけ伺いたいです。{patient_segment} ではどこが一番ハードルになりますか。",
)

USER_DISCOVERY_WEAK_JA = (
    "{evidence}。この患者層にも広く使えると思っています。",
    "データとしては良い結果が出ています。{patient_segment} でも前向きに検討できるはずです。",
)

USER_EVIDENCE_STRONG_JA = (
    "ご懸念は理解しています。{evidence} を踏まえると、特に {patient_segment} で位置づけが見えやすいです。",
    "数字だけでなく実臨床での使い分けも意識すると、{patient_segment} での判断材料として整理しやすいです。{evidence}。",
)

USER_EVIDENCE_WEAK_JA = (
    "全体として結果は良好でしたので、幅広い患者さんで使えると思います。",
    "細かい条件はありますが、基本的には有効性が期待できるデータでした。",
)

USER_OBJECTION_STRONG_JA = (
    "その懸念はもっともです。まず先生が気にされる点を受け止めた上で、{evidence} という事実だけ整理させてください。",
    "前回のご判断を踏まえると慎重になるのは自然です。その上で今回は {evidence} が追加され、判断材料が増えています。",
)

USER_OBJECTION_WEAK_JA = (
    "その点も問題ないと思います。データ自体は良かったので前向きに見ていただければと思います。",
    "大きな問題ではないと考えています。まずは有効性の部分を見ていただければ十分です。",
)

USER_SAFETY_STRONG_JA = (
    "まず販促ではなく報告手順を優先します。必要情報を漏れなく確認した上で、社内連携の流れだけ共有します。",
    "安全性対応を最優先で進めます。患者背景と発現タイミングを整理し、報告フローを一緒に確認させてください。",
)

USER_SAFETY_WEAK_JA = (
    "安全性の話もありますが、あわせて製品の良さもお伝えできればと思います。",
    "副作用の件は理解していますが、まずは関連データも含めて全体像をご紹介します。",
)

USER_CLOSING_STRONG_JA = (
    "では次回は {next_step} という形でいかがでしょうか。先生の負担が少ない形で進めます。",
    "本日の結論としては大きな切り替えではなく、まず {next_step} を次の一手にできればと思います。",
)

USER_CLOSING_WEAK_JA = (
    "また改めて伺います。資料も置いていきますのでご確認ください。",
    "ひとまず今日はここまでにして、またタイミングを見てご説明します。",
)

DOCTOR_DISCOVERY_REPLY_JA = (
    "その患者像なら、実際には何を起点に使い分けるべきでしょうか。",
    "施設運用も含めると、どの場面なら現実的に検討できますか。",
)

DOCTOR_EVIDENCE_REPLY_JA = (
    "その結果は理解しましたが、実臨床ではどの程度意味がある差と見ればよいですか。",
    "数字だけでなく、既存治療とどう使い分けるのかをもう少し具体的に教えてください。",
)

DOCTOR_OBJECTION_REPLY_JA = (
    "懸念には触れていただきましたが、まだ判断材料としては少し粗い印象です。",
    "その説明だと一般論に聞こえます。先生方が迷う場面に即してもう一段具体化できますか。",
)

DOCTOR_CLOSING_REPLY_JA = (
    "方向性は分かりました。次回はもう少し患者像を絞って確認したいです。",
    "今日はここまでで十分です。次は判断材料がそろった段階で短くお願いします。",
)


def ensure_demo_runtime_data(
    *,
    bundle: DomainBundle,
    progress_tracker: ProgressTracker,
    progress_store: ProgressStore,
    session_store: SessionStore,
    event_store: EventStore,
    prompt_context: dict[str, Any],
    specs: tuple[DemoLearnerSpec, ...] | None = None,
) -> None:
    target_specs = specs or DEMO_LEARNER_SPECS
    for spec in target_specs:
        existing = progress_store.get(spec.learner_id)
        total_sessions = int(existing.get("total_sessions", 0)) if isinstance(existing, dict) else 0
        history_count = (
            len(existing.get("recent_history", []))
            if isinstance(existing, dict) and isinstance(existing.get("recent_history"), list)
            else 0
        )
        required_history = min(spec.session_count, RECENT_HISTORY_LIMIT)
        if (
            total_sessions >= spec.session_count
            and history_count >= required_history
            and _existing_demo_seed_is_current(existing, session_store)
        ):
            continue
        _seed_demo_learner(
            spec=spec,
            bundle=bundle,
            progress_tracker=progress_tracker,
            session_store=session_store,
            event_store=event_store,
            prompt_context=prompt_context,
        )


def append_comprehensive_today_sessions(
    *,
    learner_id: str,
    session_count: int,
    min_turns: int = 4,
    max_turns: int = 6,
    bundle: DomainBundle,
    progress_tracker: ProgressTracker,
    session_store: SessionStore,
    event_store: EventStore,
    prompt_context: dict[str, Any],
    anchor_now: datetime | None = None,
) -> list[str]:
    normalized_learner_id = learner_id.strip()
    if not normalized_learner_id:
        raise ValueError("learner_id must not be empty")
    if session_count <= 0:
        raise ValueError("session_count must be greater than 0")
    if min_turns <= 0:
        raise ValueError("min_turns must be greater than 0")
    if max_turns < min_turns:
        raise ValueError("max_turns must be greater than or equal to min_turns")

    local_now = (
        anchor_now.astimezone().replace(second=0, microsecond=0)
        if anchor_now is not None
        else datetime.now().astimezone().replace(second=0, microsecond=0)
    )
    local_day_key = local_now.strftime("%Y%m%d")
    plans = _build_curated_today_session_plans(
        scenario_ids=sorted(bundle.scenarios.keys()),
        session_count=session_count,
    )
    created_session_ids: list[str] = []

    for session_index, plan in enumerate(plans, start=1):
        scenario = bundle.scenarios[plan.scenario_id]
        persona = bundle.personas[scenario.doctor_persona_id]
        rng = random.Random(_stable_seed(f"{normalized_learner_id}:{local_day_key}:{session_index}"))
        started_at = _today_batch_started_at(
            local_now=local_now,
            session_index=session_index - 1,
            session_count=len(plans),
        )
        review, score_map = _build_curated_review(
            bundle=bundle,
            scenario=scenario,
            persona=persona,
            plan=plan,
            rng=rng,
        )
        continuity_context = _build_continuity_context(
            scenario=scenario,
            persona=persona,
            review=review,
        )
        session_id = (
            f"demo_{normalized_learner_id}_today_{local_day_key}_{session_index:02d}"
        )
        session_context = DomainSessionContext.from_session_seed(
            skill_id=str(bundle.manifest.get("id", "mr_visit_jp")),
            session_id=session_id,
            learner_id=normalized_learner_id,
            scenario_id=scenario.id,
            persona_id=scenario.doctor_persona_id,
            prompt_context=prompt_context,
            continuity_context=continuity_context,
        )
        turns, events, updated_at, finish_reason = _build_turns_and_events(
            session_id=session_id,
            scenario=scenario,
            review=review,
            started_at=started_at,
            rng=rng,
            prompt_context=prompt_context,
            session_context=session_context,
            finish_reason_override=plan.finish_reason,
            min_turns=min_turns,
            max_turns=max_turns,
        )
        session_store.upsert(
            session_id,
            {
                "session_id": session_id,
                "scenario_id": scenario.id,
                "learner_id": normalized_learner_id,
                "prompt_context": prompt_context,
                "continuity_context": continuity_context,
                "context": session_context.to_dict(),
                "status": "finalized",
                "started_at": started_at,
                "updated_at": updated_at,
                "turn_count": len(turns),
                "finish_reason": finish_reason,
                "turns": turns,
                "review": review,
            },
        )
        event_store.replace(session_id, events)
        progress_tracker.apply_session_result(
            scenario_title=SCENARIO_TITLE_JA.get(scenario.id, scenario.title),
            scenario_difficulty=scenario.difficulty,
            focus_subskills=list(scenario.focus_subskills),
            persona_id=scenario.doctor_persona_id,
            persona_label=PERSONA_LABEL_JA.get(
                scenario.doctor_persona_id,
                str(persona.get("label", scenario.doctor_persona_id)),
            ),
            finish_reason=finish_reason,
            review=review,
            session_context=session_context.for_action("finish_session"),
        )
        created_session_ids.append(session_id)

    return created_session_ids


def _existing_demo_seed_is_current(
    existing: dict[str, Any] | None,
    session_store: SessionStore,
) -> bool:
    if not isinstance(existing, dict):
        return False
    recent_history = existing.get("recent_history", [])
    if not isinstance(recent_history, list) or not recent_history:
        return False
    latest_history = recent_history[-1]
    if not isinstance(latest_history, dict):
        return False
    latest_session_id = latest_history.get("session_id")
    if not isinstance(latest_session_id, str) or not latest_session_id:
        return False
    latest_session = session_store.get(latest_session_id)
    if not isinstance(latest_session, dict):
        return False
    review = latest_session.get("review", {})
    if not isinstance(review, dict):
        return False
    meta = review.get("meta", {})
    return isinstance(meta, dict) and meta.get("generator") == DEMO_SEED_GENERATOR


def _seed_demo_learner(
    *,
    spec: DemoLearnerSpec,
    bundle: DomainBundle,
    progress_tracker: ProgressTracker,
    session_store: SessionStore,
    event_store: EventStore,
    prompt_context: dict[str, Any],
) -> None:
    rng = random.Random(_stable_seed(spec.learner_id))
    scenario_ids = sorted(bundle.scenarios.keys())
    now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0) - timedelta(hours=1)

    baseline_by_skill = _build_skill_baselines(spec, list(bundle.manifest["subskills"]), rng)
    target_by_skill = _build_skill_targets(spec, list(bundle.manifest["subskills"]), rng)

    for session_index in range(spec.session_count):
        maturity = session_index / max(1, spec.session_count - 1)
        weakest_skills = _project_weak_skills(
            subskill_ids=list(bundle.manifest["subskills"]),
            baseline_by_skill=baseline_by_skill,
            target_by_skill=target_by_skill,
            maturity=maturity,
            persistent_weaknesses=spec.persistent_weaknesses,
            rng=rng,
        )
        scenario = _select_scenario(
            scenario_ids=scenario_ids,
            bundle=bundle,
            weakest_skills=weakest_skills,
            session_index=session_index,
            rng=rng,
        )
        persona = bundle.personas[scenario.doctor_persona_id]
        started_at = _session_started_at(now=now, spec=spec, session_index=session_index)
        review, score_map = _build_review(
            bundle=bundle,
            scenario=scenario,
            persona=persona,
            spec=spec,
            maturity=maturity,
            baseline_by_skill=baseline_by_skill,
            target_by_skill=target_by_skill,
            rng=rng,
        )
        continuity_context = _build_continuity_context(
            scenario=scenario,
            persona=persona,
            review=review,
        )
        session_id = f"demo_{spec.learner_id}_{session_index + 1:04d}"
        session_context = DomainSessionContext.from_session_seed(
            skill_id=str(bundle.manifest.get("id", "mr_visit_jp")),
            session_id=session_id,
            learner_id=spec.learner_id,
            scenario_id=scenario.id,
            persona_id=scenario.doctor_persona_id,
            prompt_context=prompt_context,
            continuity_context=continuity_context,
        )
        turns, events, updated_at, finish_reason = _build_turns_and_events(
            session_id=session_id,
            scenario=scenario,
            review=review,
            started_at=started_at,
            rng=rng,
            prompt_context=prompt_context,
            session_context=session_context,
        )

        session_store.upsert(
            session_id,
            {
                "session_id": session_id,
                "scenario_id": scenario.id,
                "learner_id": spec.learner_id,
                "prompt_context": prompt_context,
                "continuity_context": continuity_context,
                "context": session_context.to_dict(),
                "status": "finalized",
                "started_at": started_at,
                "updated_at": updated_at,
                "turn_count": len(turns),
                "finish_reason": finish_reason,
                "turns": turns,
                "review": review,
            },
        )
        event_store.replace(session_id, events)

        progress_tracker.apply_session_result(
            scenario_title=SCENARIO_TITLE_JA.get(scenario.id, scenario.title),
            scenario_difficulty=scenario.difficulty,
            focus_subskills=list(scenario.focus_subskills),
            persona_id=scenario.doctor_persona_id,
            persona_label=PERSONA_LABEL_JA.get(scenario.doctor_persona_id, str(persona.get("label", scenario.doctor_persona_id))),
            finish_reason=finish_reason,
            review=review,
            session_context=session_context.for_action("finish_session"),
        )

        for subskill_id, score in score_map.items():
            current = baseline_by_skill[subskill_id]
            target = target_by_skill[subskill_id]
            drift = (target - current) * 0.05
            reinforcement = (score - current) * 0.18
            baseline_by_skill[subskill_id] = max(1.2, min(4.85, round(current + drift + reinforcement, 2)))


def _stable_seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16)


def _build_skill_baselines(
    spec: DemoLearnerSpec,
    subskill_ids: list[str],
    rng: random.Random,
) -> dict[str, float]:
    baseline: dict[str, float] = {}
    for subskill_id in subskill_ids:
        score = spec.base_score + rng.uniform(-0.22, 0.22)
        if subskill_id in spec.strengths:
            score += 0.28
        if subskill_id in spec.persistent_weaknesses:
            score -= 0.24
        baseline[subskill_id] = round(max(1.5, min(3.5, score)), 2)
    return baseline


def _build_skill_targets(
    spec: DemoLearnerSpec,
    subskill_ids: list[str],
    rng: random.Random,
) -> dict[str, float]:
    targets: dict[str, float] = {}
    for subskill_id in subskill_ids:
        score = spec.base_score + spec.growth_bias + rng.uniform(0.25, 0.65)
        if subskill_id in spec.strengths:
            score += 0.24
        if subskill_id in spec.persistent_weaknesses:
            score -= 0.38
        targets[subskill_id] = round(max(2.4, min(4.8, score)), 2)
    return targets


def _project_weak_skills(
    *,
    subskill_ids: list[str],
    baseline_by_skill: dict[str, float],
    target_by_skill: dict[str, float],
    maturity: float,
    persistent_weaknesses: tuple[str, ...],
    rng: random.Random,
) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for subskill_id in subskill_ids:
        projected = baseline_by_skill[subskill_id] + (target_by_skill[subskill_id] - baseline_by_skill[subskill_id]) * math.sqrt(
            max(0.0, maturity)
        )
        if subskill_id in persistent_weaknesses:
            projected -= 0.18
        projected += rng.uniform(-0.08, 0.08)
        ranked.append((projected, subskill_id))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [subskill_id for _, subskill_id in ranked[:3]]


def _select_scenario(
    *,
    scenario_ids: list[str],
    bundle: DomainBundle,
    weakest_skills: list[str],
    session_index: int,
    rng: random.Random,
) -> ScenarioRecord:
    scored: list[tuple[int, int, str]] = []
    for offset, scenario_id in enumerate(scenario_ids):
        scenario = bundle.scenarios[scenario_id]
        overlap = len(set(weakest_skills) & set(scenario.focus_subskills))
        scored.append((-overlap, (session_index + offset) % len(scenario_ids), scenario_id))
    scored.sort()
    top_candidates = [scenario_id for _, _, scenario_id in scored[: max(3, min(5, len(scored)))]]
    return bundle.scenarios[rng.choice(top_candidates)]


def _session_started_at(*, now: datetime, spec: DemoLearnerSpec, session_index: int) -> str:
    day_offset = int(round((spec.session_count - session_index - 1) * spec.active_day_span / max(1, spec.session_count)))
    minute_offset = (session_index * 37) % 540
    session_time = now - timedelta(days=day_offset, minutes=minute_offset)
    return session_time.isoformat()


def _build_curated_today_session_plans(
    *,
    scenario_ids: list[str],
    session_count: int,
) -> list[CuratedSessionPlan]:
    if not scenario_ids:
        raise ValueError("scenario_ids must not be empty")
    weakness_rotation: tuple[tuple[str, ...], ...] = (
        ("opening", "profiling", "closing_followup"),
        ("need_discovery", "scientific_delivery", "closing_followup"),
        ("objection_handling", "scientific_delivery", "opening"),
        ("profiling", "need_discovery", "objection_handling"),
        ("scientific_delivery", "closing_followup", "opening"),
        ("need_discovery", "opening", "profiling"),
        ("closing_followup", "objection_handling", "scientific_delivery"),
    )
    strength_rotation: tuple[tuple[str, ...], ...] = (
        ("scientific_delivery", "closing_followup", "preparation"),
        ("opening", "profiling", "scientific_delivery"),
        ("need_discovery", "opening", "closing_followup"),
        ("profiling", "scientific_delivery", "objection_handling"),
        ("closing_followup", "need_discovery", "opening"),
        ("preparation", "scientific_delivery", "profiling"),
        ("objection_handling", "closing_followup", "preparation"),
    )
    score_sequence = (93, 88, 82, 76, 69, 63, 57, 52, 85, 74)

    plans: list[CuratedSessionPlan] = []
    for index in range(session_count):
        scenario_id = scenario_ids[index % len(scenario_ids)]
        overall_score = score_sequence[index % len(score_sequence)]
        scenario_cycle_index = index // len(scenario_ids)
        if scenario_id == "cautious_doctor_evidence_check" and scenario_cycle_index == 0:
            overall_score = 64
        elif scenario_id == "new_product_adoption_barrier" and scenario_cycle_index == 0:
            overall_score = 58
        elif scenario_id == "busy_doctor_short_visit" and scenario_cycle_index >= 2:
            overall_score = 60
        weak_subskills = weakness_rotation[index % len(weakness_rotation)]
        strong_subskills = strength_rotation[index % len(strength_rotation)]
        if scenario_id == "adverse_event_followup_required":
            finish_reason = (
                "director_signaled_completion" if overall_score >= 72 else "manual_finish"
            )
        elif scenario_id in {"busy_doctor_short_visit", "low_interest_doctor_intro_fail"} and overall_score <= 63:
            finish_reason = "learner_requested_finish"
        elif overall_score <= 57 or (index % 6 == 5 and overall_score <= 69):
            finish_reason = "max_turns_reached"
        elif overall_score >= 85:
            finish_reason = "director_signaled_completion"
        else:
            finish_reason = "manual_finish"
        plans.append(
            CuratedSessionPlan(
                scenario_id=scenario_id,
                overall_score=overall_score,
                weak_subskills=weak_subskills,
                strong_subskills=strong_subskills,
                finish_reason=finish_reason,
            )
        )
    return plans


def _today_batch_started_at(
    *,
    local_now: datetime,
    session_index: int,
    session_count: int,
) -> str:
    start_of_day = local_now.replace(hour=0, minute=5, second=0, microsecond=0)
    total_minutes = max(
        0,
        int((local_now - start_of_day).total_seconds() // 60),
    )
    if session_count <= 1:
        offset_minutes = total_minutes
    else:
        offset_minutes = round((session_index / max(1, session_count - 1)) * total_minutes)
    return (start_of_day + timedelta(minutes=offset_minutes)).isoformat()


def _build_curated_review(
    *,
    bundle: DomainBundle,
    scenario: ScenarioRecord,
    persona: dict[str, Any],
    plan: CuratedSessionPlan,
    rng: random.Random,
) -> tuple[dict[str, Any], dict[str, float]]:
    base_score = max(1.4, min(4.75, round(plan.overall_score / 20, 2)))
    subskill_ids = [str(item) for item in bundle.manifest["subskills"]]
    scenario_focus = set(scenario.focus_subskills)
    weak_set = set(plan.weak_subskills)
    strong_set = set(plan.strong_subskills)

    score_map: dict[str, float] = {}
    for index, subskill_id in enumerate(subskill_ids):
        score = base_score
        if subskill_id in weak_set:
            score -= 1.25 + (0.1 * (index % 2))
        elif subskill_id in strong_set:
            score += 0.75 - (0.05 * (index % 2))
        elif subskill_id in scenario_focus:
            score += 0.28
        else:
            score += 0.05 * ((index % 3) - 1)
        score += rng.uniform(-0.18, 0.18)
        score_map[subskill_id] = round(max(1.0, min(4.9, score)), 1)

    weakest = list(plan.weak_subskills[:3])
    strongest = [
        subskill_id
        for subskill_id in plan.strong_subskills
        if subskill_id not in weakest
    ][:3]
    if len(strongest) < 3:
        strongest.extend(
            [
                subskill_id
                for subskill_id in sorted(score_map, key=lambda key: (-score_map[key], key))
                if subskill_id not in strongest and subskill_id not in weakest
            ][: 3 - len(strongest)]
        )

    diagnosis_primary = []
    for subskill_id in weakest[:3]:
        diagnosis_primary.append(
            {
                "id": f"today_batch_{subskill_id}",
                "kind": "skill_gap",
                "severity": "high" if score_map[subskill_id] < 2.3 else "medium",
                "summary": DIAGNOSIS_TEMPLATES_JA[subskill_id],
                "related_subskills": [subskill_id],
                "recommendation_focus": [subskill_id],
            }
        )

    display_title = SCENARIO_TITLE_JA.get(scenario.id, scenario.title)
    persona_label = PERSONA_LABEL_JA.get(
        scenario.doctor_persona_id,
        str(persona.get("label", scenario.doctor_persona_id)),
    )
    return (
        {
            "display_title": display_title,
            "persona_label_override": persona_label,
            "overall_score": plan.overall_score,
            "overall_band": _overall_band(plan.overall_score),
            "strengths": [STRENGTH_TEMPLATES_JA[subskill_id] for subskill_id in strongest[:3]],
            "priority_subskills": weakest,
            "subskills": {
                subskill_id: {
                    "score": score,
                    "evidence": [f"本日の再現データでは {subskill_id} の挙動差を重点観察しました。"],
                }
                for subskill_id, score in score_map.items()
            },
            "diagnosis": {
                "primary": diagnosis_primary,
                "selection_basis": COMPREHENSIVE_TODAY_BATCH_GENERATOR,
            },
            "coaching_feedback": {
                "version": 1,
                "focus_subskills": weakest,
                "next_actions": [SUBSKILL_ACTIONS_JA[subskill_id] for subskill_id in weakest[:3]],
            },
            "compliance_flags": _curated_compliance_flags(
                scenario_id=scenario.id,
                overall_score=plan.overall_score,
                finish_reason=plan.finish_reason,
            ),
            "meta": {
                "generator": COMPREHENSIVE_TODAY_BATCH_GENERATOR,
                "locale": "ja-JP",
                "persona_label": persona_label,
                "scenario_title": display_title,
            },
        },
        score_map,
    )


def _curated_compliance_flags(
    *,
    scenario_id: str,
    overall_score: int,
    finish_reason: str,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if scenario_id == "adverse_event_followup_required" and (
        overall_score <= 70 or finish_reason == "learner_requested_finish"
    ):
        flags.append(
            {
                "rule_id": "adverse_event_reporting_failure",
                "tag": "adverse_event_reporting_failure",
                "severity": "critical" if overall_score <= 60 else "high",
                "summary": "有害事象の基本情報取得と SOP に沿った連携を先に明示する必要があります。",
                "related_diagnosis_types": ["adverse_event_escalation_miss"],
            }
        )
    if scenario_id == "skeptical_doctor_competitor_pressure" and overall_score <= 68:
        flags.append(
            {
                "rule_id": "unsubstantiated_competitor_comparison",
                "tag": "unsubstantiated_competitor_comparison",
                "severity": "high",
                "summary": "競合比較では断定や攻撃表現を避け、確認可能な差分だけに限定する必要があります。",
                "related_diagnosis_types": ["objection_response_gap"],
            }
        )
    if scenario_id == "cautious_doctor_evidence_check" and overall_score <= 66:
        flags.append(
            {
                "rule_id": "fair_balance_omission",
                "tag": "fair_balance_omission",
                "severity": "high",
                "summary": "有効性を述べる際は、制約や安全性文脈も同時に示してフェアバランスを保つ必要があります。",
                "related_diagnosis_types": ["fair_balance_omission"],
            }
        )
    if scenario_id == "new_product_adoption_barrier" and overall_score <= 58:
        flags.append(
            {
                "rule_id": "off_label_or_unapproved_indication",
                "tag": "off_label_risk",
                "severity": "critical",
                "summary": "承認範囲を超える含意に聞こえないよう、適応境界を明確に保つ必要があります。",
                "related_diagnosis_types": ["overclaim_or_off_label_risk"],
            }
        )
    if scenario_id == "busy_doctor_short_visit" and overall_score <= 60:
        flags.append(
            {
                "rule_id": "unsupported_outcome_promise",
                "tag": "unsupported_promise",
                "severity": "high",
                "summary": "短時間面談ほど断定表現を避け、エビデンスで限定した言い方に徹する必要があります。",
                "related_diagnosis_types": ["overclaim_or_off_label_risk"],
            }
        )
    return flags[:3]


def _build_review(
    *,
    bundle: DomainBundle,
    scenario: ScenarioRecord,
    persona: dict[str, Any],
    spec: DemoLearnerSpec,
    maturity: float,
    baseline_by_skill: dict[str, float],
    target_by_skill: dict[str, float],
    rng: random.Random,
) -> tuple[dict[str, Any], dict[str, float]]:
    score_map: dict[str, float] = {}
    for subskill_id in bundle.manifest["subskills"]:
        projected = baseline_by_skill[subskill_id] + (target_by_skill[subskill_id] - baseline_by_skill[subskill_id]) * math.sqrt(
            max(0.0, maturity)
        )
        if subskill_id in scenario.focus_subskills:
            projected += 0.16
        if subskill_id in spec.persistent_weaknesses:
            projected -= 0.14
        projected += math.sin((maturity * 8.5) + len(subskill_id)) * 0.08
        projected += rng.uniform(-0.24, 0.24)
        score_map[subskill_id] = round(max(1.0, min(4.9, projected)), 1)

    weakest = sorted(score_map, key=lambda item: (score_map[item], item))[:3]
    strongest = sorted(score_map, key=lambda item: (-score_map[item], item))[:3]
    overall_score = int(
        max(
            38,
            min(
                96,
                round((sum(score_map.values()) / max(1, len(score_map))) * 20 + rng.uniform(-2.5, 2.5)),
            ),
        )
    )

    diagnosis_primary = []
    for subskill_id in weakest[:2]:
        diagnosis_primary.append(
            {
                "id": f"seeded_{subskill_id}",
                "kind": "skill_gap",
                "severity": "high" if score_map[subskill_id] < 2.4 else "medium",
                "summary": DIAGNOSIS_TEMPLATES_JA[subskill_id],
                "related_subskills": [subskill_id],
                "recommendation_focus": [subskill_id],
            }
        )

    strengths = [STRENGTH_TEMPLATES_JA[subskill_id] for subskill_id in strongest[:3]]
    next_actions = [SUBSKILL_ACTIONS_JA[subskill_id] for subskill_id in weakest[:3]]

    compliance_flags: list[dict[str, str]] = []
    if scenario.id == "adverse_event_followup_required":
        compliance_flags.append({"summary": "有害事象対応では販促表現よりも報告フローの明確化を優先してください。"})
    elif scenario.id == "skeptical_doctor_competitor_pressure" and rng.random() < 0.45:
        compliance_flags.append({"summary": "競合比較では断定表現を避け、確認可能な差分に限定して説明してください。"})

    display_title = SCENARIO_TITLE_JA.get(scenario.id, scenario.title)
    persona_label = PERSONA_LABEL_JA.get(scenario.doctor_persona_id, str(persona.get("label", scenario.doctor_persona_id)))
    return (
        {
            "display_title": display_title,
            "persona_label_override": persona_label,
            "overall_score": overall_score,
            "overall_band": _overall_band(overall_score),
            "strengths": strengths,
            "priority_subskills": weakest,
            "subskills": {
                subskill_id: {
                    "score": score,
                    "evidence": [f"学習ログ上の {subskill_id} 行動をもとに評価しました。"],
                }
                for subskill_id, score in score_map.items()
            },
            "diagnosis": {
                "primary": diagnosis_primary,
                "selection_basis": DEMO_SEED_GENERATOR,
            },
            "coaching_feedback": {
                "version": 1,
                "focus_subskills": weakest,
                "next_actions": next_actions,
            },
            "compliance_flags": compliance_flags,
            "meta": {
                "generator": DEMO_SEED_GENERATOR,
                "locale": "ja-JP",
                "persona_label": persona_label,
                "scenario_title": display_title,
            },
        },
        score_map,
    )


def _overall_band(score: int) -> str:
    if score >= 85:
        return "advanced"
    if score >= 72:
        return "proficient"
    if score >= 58:
        return "developing"
    return "emerging"


def _build_continuity_context(
    *,
    scenario: ScenarioRecord,
    persona: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    persona_label = PERSONA_LABEL_JA.get(scenario.doctor_persona_id, str(persona.get("label", scenario.doctor_persona_id)))
    summary_title = SCENARIO_TITLE_JA.get(scenario.id, scenario.title)
    recommended_focus = [
        item for item in review.get("priority_subskills", []) if isinstance(item, str)
    ][:3]
    next_actions = [
        item for item in review.get("coaching_feedback", {}).get("next_actions", []) if isinstance(item, str)
    ][:4]
    
    teaching_plan = {
        "focus_subskills": list(recommended_focus[:2]),
        "reason": "Recurring pattern in recent sessions." if len(recommended_focus) > 1 else "Area for improvement from last session.",
        "target_behavior": next_actions[0] if next_actions else "Focus on core subskill delivery.",
        "success_criterion": f"Achieve a score of 4.0 or higher in {', '.join(recommended_focus[:2])}",
        "score_threshold": 4.0
    }

    return {
        "version": 1,
        "summary": f"{summary_title} を想定した記録です。{persona_label}には要点を絞り、短い往復で価値と次の一手を示すことが重要です。",
        "scenario_title_override": summary_title,
        "carryover_focus_subskills": list(recommended_focus[:2]),
        "scenario_focus_subskills": list(scenario.focus_subskills),
        "suggested_focus_subskills": list(dict.fromkeys([*recommended_focus, *scenario.focus_subskills]))[:4],
        "next_actions": next_actions,
        "teaching_plan": teaching_plan,
        "recent_personas": [persona_label],
        "last_diagnosis_summaries": [
            item.get("summary")
            for item in review.get("diagnosis", {}).get("primary", [])
            if isinstance(item, dict) and isinstance(item.get("summary"), str)
        ][:3],
        "persona": {
            "id": scenario.doctor_persona_id,
            "label": persona_label,
            "specialty": SPECIALTY_LABEL_JA.get(str(persona.get("specialty", "")), str(persona.get("specialty", ""))),
            "attitude": str(persona.get("attitude", "")),
            "time_pressure": str(persona.get("time_pressure", "")),
            "decision_style": str(persona.get("decision_style", "")),
            "more_receptive_when": [
                "患者像に結び付けて短く話すとき。",
                "懸念に対して具体的な根拠で返答するとき。",
            ],
            "less_receptive_when": [
                "長い製品説明から入るとき。",
                "前回の懸念を無視して同じ話を繰り返すとき。",
            ],
        },
        "success_criteria": list(scenario.success_criteria),
        "failure_patterns": list(scenario.failure_patterns),
    }


def _build_turns_and_events(
    *,
    session_id: str,
    scenario: ScenarioRecord,
    review: dict[str, Any],
    started_at: str,
    rng: random.Random,
    prompt_context: dict[str, Any],
    session_context: DomainSessionContext,
    finish_reason_override: str | None = None,
    min_turns: int = 4,
    max_turns: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    started = datetime.fromisoformat(started_at)
    priority = [
        item for item in review.get("priority_subskills", []) if isinstance(item, str)
    ]
    patient_segment = rng.choice(PATIENT_SEGMENTS)
    evidence = rng.choice(EVIDENCE_SNIPPETS)
    next_step = rng.choice(NEXT_STEP_SNIPPETS)
    overall_score = int(review.get("overall_score", 60))
    turn_blueprints = _build_turn_blueprints(
        scenario_id=scenario.id,
        priority=priority,
        overall_score=overall_score,
        rng=rng,
        min_turns=min_turns,
        max_turns=max_turns,
    )
    finish_reason = finish_reason_override or _finish_reason_for_session(
        scenario_id=scenario.id,
        overall_score=overall_score,
        turn_count=len(turn_blueprints),
        rng=rng,
    )

    turns: list[dict[str, Any]] = []
    started_context = session_context.for_action("start_session")
    events: list[dict[str, Any]] = [
        build_session_event_envelope(
            event_type="session_started",
            timestamp=started_at,
            session_context=started_context,
            stage="opening",
            content=build_session_started_content(
                experiment_context=summarize_prompt_context(prompt_context),
                coach_continuity={
                    "summary": str(session_context.continuity_context.get("summary", "")),
                    "suggested_focus_subskills": list(
                        session_context.continuity_context.get("suggested_focus_subskills", [])
                    ),
                },
            ),
            seq=1,
        ).to_dict()
    ]
    updated_at = started
    elapsed_minutes = 0
    for turn_index, (phase, focus_skill) in enumerate(turn_blueprints, start=1):
        if turn_index > 1:
            elapsed_minutes += 2 if scenario.id == "busy_doctor_short_visit" else 3
            elapsed_minutes += rng.randint(0, 1 if overall_score >= 72 else 2)
        created_at = started + timedelta(minutes=elapsed_minutes)
        updated_at = created_at
        user_message = _user_message_for_turn(
            scenario_id=scenario.id,
            phase=phase,
            focus_skill=focus_skill,
            priority=priority,
            patient_segment=patient_segment,
            evidence=evidence,
            next_step=next_step,
            overall_score=overall_score,
            rng=rng,
        )
        doctor_reply = _doctor_reply_for_turn(
            scenario_id=scenario.id,
            phase=phase,
            focus_skill=focus_skill,
            turn_index=turn_index,
            total_turns=len(turn_blueprints),
            finish_reason=finish_reason,
            overall_score=overall_score,
            rng=rng,
        )
        director_events = _director_events_for_turn(
            scenario_id=scenario.id,
            phase=phase,
            focus_skill=focus_skill,
            turn_index=turn_index,
            total_turns=len(turn_blueprints),
            overall_score=overall_score,
        )
        action = _action_for_turn(
            scenario_id=scenario.id,
            phase=phase,
            focus_skill=focus_skill,
        )
        turns.append(
            {
                "turn_index": turn_index,
                "user_message": user_message,
                "doctor_reply": doctor_reply,
                "director_phase": phase,
                "director_events": director_events,
                "created_at": created_at.isoformat(),
            }
        )
        turn_context = session_context.for_action(
            "send_turn",
            turn_id=build_turn_id(session_id, turn_index),
        )
        turn_content = build_turn_event_content(
            turn_index=turn_index,
            phase=phase,
            event_codes=director_events,
            recommended_action=action,
            should_finish=(
                finish_reason == "max_turns_reached" and turn_index == len(turn_blueprints)
            ),
            turn_signals=analyze_turn_message(user_message),
        )
        turn_content["status"] = "awaiting_finish" if turn_index == len(turn_blueprints) else "running"
        events.append(
            build_session_event_envelope(
                event_type="turn_processed",
                timestamp=created_at.isoformat(),
                session_context=turn_context,
                stage=phase,
                content=turn_content,
                seq=turn_index + 1,
            ).to_dict()
        )

    finalized_at = updated_at + timedelta(minutes=2)
    final_turn_id = build_turn_id(session_id, len(turn_blueprints)) if turn_blueprints else None
    final_content = build_session_finalized_content(
        finish_reason=finish_reason,
        overall_score=int(review.get("overall_score", 0)),
        experiment_context=summarize_prompt_context(prompt_context),
    )
    final_content["turn_count"] = len(turn_blueprints)
    events.append(
        build_session_event_envelope(
            event_type="session_finalized",
            timestamp=finalized_at.isoformat(),
            session_context=session_context.for_action(
                "finish_session",
                turn_id=final_turn_id,
            ),
            stage="completion",
            content=final_content,
            seq=len(turn_blueprints) + 2,
        ).to_dict()
    )
    return turns, events, finalized_at.isoformat(), finish_reason


def _build_turn_blueprints(
    *,
    scenario_id: str,
    priority: list[str],
    overall_score: int,
    rng: random.Random,
    min_turns: int = 4,
    max_turns: int = 6,
) -> list[tuple[str, str]]:
    if min_turns <= 0:
        raise ValueError("min_turns must be greater than 0")
    if max_turns < min_turns:
        raise ValueError("max_turns must be greater than or equal to min_turns")

    resolved_max_turns = max_turns
    opening_focus = "opening" if "opening" in priority[:2] or overall_score < 70 else (priority[0] if priority else "opening")
    discovery_focus = "profiling" if "profiling" in priority else "need_discovery"
    evidence_focus = (
        "objection_handling"
        if scenario_id in {"revisit_after_prior_rejection", "skeptical_doctor_competitor_pressure"} or "objection_handling" in priority[:2]
        else "scientific_delivery"
    )
    closing_focus = "closing_followup"

    if scenario_id == "adverse_event_followup_required":
        blueprints: list[tuple[str, str]] = [
            ("opening", opening_focus),
            ("safety", "objection_handling"),
            ("discovery", discovery_focus),
            ("closing", closing_focus),
        ]
    else:
        blueprints = [
            ("opening", opening_focus),
            ("discovery", discovery_focus),
            ("evidence", evidence_focus),
            ("closing", closing_focus),
        ]

    if scenario_id in {"cautious_doctor_evidence_check", "skeptical_doctor_competitor_pressure"} and overall_score < 82:
        blueprints.insert(2, ("evidence", "scientific_delivery"))

    if scenario_id in {"formulary_restriction_negotiation", "revisit_after_prior_rejection"} and overall_score < 78:
        blueprints.insert(len(blueprints) - 1, ("discovery", discovery_focus))

    if overall_score < 58:
        blueprints.insert(len(blueprints) - 1, ("evidence", evidence_focus))
    elif overall_score < 70 and rng.random() < 0.45:
        blueprints.insert(len(blueprints) - 1, ("closing", closing_focus))

    target_turn_count = min_turns
    if max_turns > min_turns:
        dynamic_lower = min_turns
        if overall_score < 58:
            dynamic_lower = min(max_turns, min_turns + 3)
        elif overall_score < 70:
            dynamic_lower = min(max_turns, min_turns + 2)
        elif overall_score < 82:
            dynamic_lower = min(max_turns, min_turns + 1)
        if dynamic_lower < max_turns:
            target_turn_count = rng.randint(dynamic_lower, max_turns)
        else:
            target_turn_count = dynamic_lower

    growth_path: list[tuple[str, str]] = [
        ("discovery", discovery_focus),
        ("evidence", evidence_focus),
        ("discovery", "need_discovery"),
        ("evidence", "scientific_delivery"),
        ("closing", closing_focus),
    ]
    if scenario_id == "adverse_event_followup_required":
        growth_path = [
            ("discovery", discovery_focus),
            ("safety", "objection_handling"),
            ("evidence", evidence_focus),
            ("closing", closing_focus),
        ]

    growth_index = 0
    while len(blueprints) < min_turns:
        insert_at = max(0, len(blueprints) - 1)
        candidate = growth_path[growth_index % len(growth_path)]
        blueprints.insert(insert_at, candidate)
        growth_index += 1

    while len(blueprints) < target_turn_count:
        insert_at = max(0, len(blueprints) - 1)
        candidate = growth_path[growth_index % len(growth_path)]
        blueprints.insert(insert_at, candidate)
        growth_index += 1

    if len(blueprints) > target_turn_count:
        blueprints = blueprints[:target_turn_count]
    if len(blueprints) > resolved_max_turns:
        blueprints = blueprints[:resolved_max_turns]

    if blueprints:
        blueprints[-1] = ("closing", closing_focus)

    return blueprints


def _finish_reason_for_session(
    *,
    scenario_id: str,
    overall_score: int,
    turn_count: int,
    rng: random.Random,
) -> str:
    if scenario_id == "adverse_event_followup_required" and overall_score >= 68:
        return "director_signaled_completion"
    if scenario_id in {"busy_doctor_short_visit", "low_interest_doctor_intro_fail"} and overall_score < 56:
        return "learner_requested_finish"
    if overall_score < 52 or (turn_count >= 6 and overall_score < 64):
        return "max_turns_reached"
    if overall_score >= 86:
        return "director_signaled_completion" if rng.random() < 0.7 else "manual_finish"
    if overall_score >= 72 and rng.random() < 0.35:
        return "director_signaled_completion"
    return "manual_finish"


def _is_strong_turn(
    *,
    overall_score: int,
    focus_skill: str,
    priority: list[str],
    phase: str,
) -> bool:
    weakness_rank = priority.index(focus_skill) if focus_skill in priority else 99
    threshold = 80 if phase in {"opening", "discovery"} else 72
    return overall_score >= threshold and weakness_rank > 0


def _user_message_for_turn(
    *,
    scenario_id: str,
    phase: str,
    focus_skill: str,
    priority: list[str],
    patient_segment: str,
    evidence: str,
    next_step: str,
    overall_score: int,
    rng: random.Random,
) -> str:
    strong = _is_strong_turn(
        overall_score=overall_score,
        focus_skill=focus_skill,
        priority=priority,
        phase=phase,
    )

    if phase == "opening":
        if scenario_id == "adverse_event_followup_required":
            return rng.choice(USER_SAFETY_STRONG_JA if strong else USER_SAFETY_WEAK_JA)
        if scenario_id == "revisit_after_prior_rejection" and strong:
            return f"前回のご意見を踏まえ、今日は差分だけ短く共有します。{patient_segment} に関して判断材料が1点増えました。"
        if scenario_id == "formulary_restriction_negotiation" and strong:
            return f"院内条件を踏まえて現実的な使い方だけご相談したく伺いました。{patient_segment} に絞って確認させてください。"
        template = rng.choice(USER_OPENING_STRONG_JA if strong else USER_OPENING_WEAK_JA)
        return template.format(patient_segment=patient_segment)

    if phase == "safety":
        template = rng.choice(USER_SAFETY_STRONG_JA if strong else USER_SAFETY_WEAK_JA)
        return template

    if phase == "discovery":
        if scenario_id == "revisit_after_prior_rejection":
            if strong:
                return f"前回見送りになった背景で、特に何が一番引っ掛かっていたのか改めて伺いたいです。その上で、{evidence} をどう見るか整理したいです。"
            return "前回から新しいデータが出ていますので、今回は前向きにご検討いただけるかもしれません。"
        if scenario_id == "formulary_restriction_negotiation":
            if strong:
                return f"院内採用ではどの条件が最もネックになりますか。{patient_segment} での必要性から逆算して整理したいです。"
            return "採用面も含めて総合的にはメリットがあると思っています。まずは概要だけ共有させてください。"
        template = rng.choice(USER_DISCOVERY_STRONG_JA if strong else USER_DISCOVERY_WEAK_JA)
        return template.format(patient_segment=patient_segment, evidence=evidence)

    if phase == "evidence":
        if focus_skill == "objection_handling" or scenario_id in {"revisit_after_prior_rejection", "skeptical_doctor_competitor_pressure"}:
            template = rng.choice(USER_OBJECTION_STRONG_JA if strong else USER_OBJECTION_WEAK_JA)
            return template.format(evidence=evidence)
        template = rng.choice(USER_EVIDENCE_STRONG_JA if strong else USER_EVIDENCE_WEAK_JA)
        return template.format(patient_segment=patient_segment, evidence=evidence)

    template = rng.choice(USER_CLOSING_STRONG_JA if strong else USER_CLOSING_WEAK_JA)
    return template.format(next_step=next_step)


def _doctor_reply_for_turn(
    *,
    scenario_id: str,
    phase: str,
    focus_skill: str,
    turn_index: int,
    total_turns: int,
    finish_reason: str,
    overall_score: int,
    rng: random.Random,
) -> str:
    if phase == "opening":
        return SCENARIO_CHALLENGE_JA.get(scenario_id, "要点を簡潔にお願いします。")
    if phase == "safety":
        if overall_score < 70:
            return "まず報告の優先順位を明確にしてください。販促の話は後にしてください。"
        return "報告フローは理解したいです。必要情報を順に確認させてください。"
    if phase == "discovery":
        if scenario_id in {"formulary_restriction_negotiation", "revisit_after_prior_rejection"}:
            return SCENARIO_FOLLOWUP_JA.get(scenario_id, "その背景をもう少し具体的に教えてください。")
        return rng.choice(DOCTOR_DISCOVERY_REPLY_JA)
    if phase == "evidence":
        if overall_score < 62 and focus_skill == "objection_handling":
            return rng.choice(DOCTOR_OBJECTION_REPLY_JA)
        if scenario_id in {"cautious_doctor_evidence_check", "skeptical_doctor_competitor_pressure"}:
            return SCENARIO_FOLLOWUP_JA.get(scenario_id, "その差をどう解釈すべきか教えてください。")
        return rng.choice(DOCTOR_EVIDENCE_REPLY_JA)

    if turn_index == total_turns:
        if finish_reason == "learner_requested_finish":
            return "今日はここまでにしてください。資料だけ確認しておきます。"
        if finish_reason == "max_turns_reached":
            return "外来に戻る時間なので、続きは次回にしてください。"
        return SCENARIO_CLOSE_JA.get(scenario_id, "分かりました。次回また確認しましょう。")

    if overall_score >= 78:
        return SCENARIO_CLOSE_JA.get(scenario_id, "要点は分かりました。次回また確認します。")
    return rng.choice(DOCTOR_CLOSING_REPLY_JA)


def _director_events_for_turn(
    *,
    scenario_id: str,
    phase: str,
    focus_skill: str,
    turn_index: int,
    total_turns: int,
    overall_score: int,
) -> list[str]:
    events: list[str] = []
    if phase == "safety":
        events.append("safety_reporting_not_started" if overall_score < 76 else "safety_first_context")
    elif phase == "opening" and scenario_id == "busy_doctor_short_visit":
        events.append("time_pressure_not_respected" if overall_score < 70 else "opening_missing_permission")
    elif phase == "discovery" and scenario_id == "revisit_after_prior_rejection":
        events.append("prior_rejection_not_acknowledged" if overall_score < 74 else "no_new_relevance_after_rejection")
    elif phase == "discovery" and scenario_id == "formulary_restriction_negotiation":
        events.append("formulary_barrier_not_explored")
    elif phase == "evidence" and scenario_id == "skeptical_doctor_competitor_pressure":
        events.append("evidence_not_addressed" if overall_score < 72 else "carryover_evidence_gap")
    else:
        events.append(_event_for_priority(focus_skill, scenario_id))

    if phase == "discovery" and focus_skill in {"need_discovery", "profiling"} and overall_score < 60:
        events.append("discovery_question_missing")
    if phase == "closing" and (overall_score < 70 or turn_index == total_turns):
        events.append("closing_next_step_missing" if overall_score < 66 else "carryover_followup_gap")

    return list(dict.fromkeys(events))[:2]


def _action_for_turn(
    *,
    scenario_id: str,
    phase: str,
    focus_skill: str,
) -> str:
    if phase == "safety":
        return "state_reporting_process_and_followup"
    if scenario_id == "revisit_after_prior_rejection" and phase in {"discovery", "evidence"}:
        return "acknowledge_prior_rejection_and_offer_update"
    if scenario_id == "formulary_restriction_negotiation" and phase == "discovery":
        return "ask_about_formulary_barrier"
    if phase == "closing":
        return "state_micro_commitment_and_followup"
    return _action_for_priority(focus_skill)


def _event_for_priority(subskill_id: str, scenario_id: str) -> str:
    if subskill_id == "preparation":
        return "carryover_opening_gap"
    if subskill_id == "opening":
        return "opening_missing_permission"
    if subskill_id == "profiling":
        return "prior_rejection_not_acknowledged" if scenario_id == "revisit_after_prior_rejection" else "formulary_barrier_not_explored"
    if subskill_id == "scientific_delivery":
        return "carryover_evidence_gap"
    if subskill_id == "need_discovery":
        return "discovery_question_missing"
    if subskill_id == "objection_handling":
        return "evidence_not_addressed"
    return "closing_next_step_missing"


def _action_for_priority(subskill_id: str) -> str:
    if subskill_id == "preparation":
        return "shorten_opening_and_get_permission"
    if subskill_id == "opening":
        return "shorten_opening_and_get_permission"
    if subskill_id == "profiling":
        return "ask_about_formulary_barrier"
    if subskill_id == "scientific_delivery":
        return "cite_endpoint_safety_and_patient_segment"
    if subskill_id == "need_discovery":
        return "ask_one_targeted_discovery_question"
    if subskill_id == "objection_handling":
        return "acknowledge_prior_rejection_and_offer_update"
    return "state_micro_commitment_and_followup"
