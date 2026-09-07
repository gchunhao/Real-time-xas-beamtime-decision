from __future__ import annotations

from dataclasses import dataclass

from .models import AnalysisResult, ScientificDecision, utc_now


@dataclass(slots=True)
class SimulatedExecution:
    sample_id: str
    scientific_decision: str
    sample_action: str
    scheduler_action: str
    effective_scheduler_action: str
    eligibility: str
    executed: bool
    sample_action_executed: bool
    scheduler_transition_executed: bool
    review_hold_active: bool
    mode: str = "SIMULATION"
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_id": self.sample_id,
            "scientific_decision": self.scientific_decision,
            "sample_action": self.sample_action,
            "scheduler_action": self.scheduler_action,
            "effective_scheduler_action": self.effective_scheduler_action,
            "eligibility": self.eligibility,
            "executed": self.executed,
            "sample_action_executed": self.sample_action_executed,
            "scheduler_transition_executed": self.scheduler_transition_executed,
            "review_hold_active": self.review_hold_active,
            "mode": self.mode,
            "created_at": self.created_at,
        }


class SchedulerSimulationAdapter:
    """v0.2 scheduler adapter with sample-level review holds.

    Acquisition control remains disconnected. The adapter records the action
    that would be taken. REVIEW_REQUIRED holds only the affected logical sample
    while the scheduler is still allowed to advance to the next sample.
    """

    def __init__(self) -> None:
        self.last_execution: SimulatedExecution | None = None
        self.history: list[SimulatedExecution] = []
        self.held_samples: set[str] = set()

    def apply(self, result: AnalysisResult) -> SimulatedExecution:
        is_review = result.recommendation is ScientificDecision.REVIEW_REQUIRED
        if is_review:
            self.held_samples.add(result.sample_id)
        else:
            self.held_samples.discard(result.sample_id)

        sample_action_executed = result.auto_execution_eligibility.value == "ELIGIBLE"
        scheduler_transition_executed = True
        execution = SimulatedExecution(
            sample_id=result.sample_id,
            scientific_decision=result.recommendation.value,
            sample_action=result.sample_action.value,
            scheduler_action=result.scheduler_action.value,
            effective_scheduler_action=result.effective_scheduler_action.value,
            eligibility=result.auto_execution_eligibility.value,
            executed=sample_action_executed or scheduler_transition_executed,
            sample_action_executed=sample_action_executed,
            scheduler_transition_executed=scheduler_transition_executed,
            review_hold_active=result.sample_id in self.held_samples,
            created_at=utc_now(),
        )
        self.last_execution = execution
        self.history.append(execution)
        self.history = self.history[-100:]
        return execution

    def resolve_review(self, sample_id: str, reviewer_decision: str | None) -> None:
        if reviewer_decision and reviewer_decision != ScientificDecision.REVIEW_REQUIRED.value:
            self.held_samples.discard(sample_id)

    def state(self) -> dict[str, object]:
        return {
            "mode": "SIMULATION",
            "acquisition_control_enabled": False,
            "held_samples": sorted(self.held_samples),
            "last_execution": self.last_execution.to_dict() if self.last_execution else None,
            "recent_executions": [item.to_dict() for item in self.history[-20:]],
        }
