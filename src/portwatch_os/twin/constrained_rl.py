"""Sequential masked Q-learning over existing berth-allocation rules.

Each transition uses simulator progression and the SAME operational reward as
the baseline policies. Joint proposals are validated against a cloned state
before selection; the simulator still applies its independent safety check.
This saved policy is a candidate for explicit simulation, never an executor.
"""
from __future__ import annotations
import json
import random
from pathlib import Path
from src.portwatch_os.clock import wall_now
import hashlib
import numpy as np
from src.portwatch_os.twin.policies import BasePolicy, FirstComeFirstServed, GreedyPolicy, LookaheadPolicy
from src.portwatch_os.twin.simulation import Action, NO_ACTION, SimulationResult, apply_action, validate_action, reward
from src.portwatch_os.twin.rl import PortEnvironment, ScenarioSpec, evaluate, TRAIN_SEED_BASE


class MaskedQLearningPolicy(BasePolicy):
    policy_id = "masked_q"
    name = "Sequential masked Q-learning"
    family = "reinforcement_learning"
    description = "Experimental sequential rule selection; every joint action is masked by berth, draught, crane and resource constraints."

    def __init__(self, table=None, *, training=False, seed=168, epsilon=.15):
        self.table = table or {}
        self.training, self.epsilon = training, epsilon
        self.rng = random.Random(seed)
        self.arms = [FirstComeFirstServed(), GreedyPolicy(), LookaheadPolicy()]
        self.previous = None
        self.masked_proposals = 0

    def reset(self):
        self.previous = None

    def context(self, state):
        return ":".join(map(str, (min(4,state.queue_length//3), min(3,len(state.free_berths())//2),
            int(state.weather_impact>.2),int(state.yard_utilisation>.8),min(3,int(state.hour//12)))))

    def potential(self, state):
        return reward(SimulationResult(final_state=state, metrics=state.metrics(), steps=0))

    def proposal(self, state, arm):
        if arm == 3:
            return [Action(kind=NO_ACTION)]
        trial = state.clone(); actions = []
        for action in self.arms[arm].act(state):
            if validate_action(trial,action):
                self.masked_proposals += 1
                continue
            apply_action(trial,action); actions.append(action)
        return actions or [Action(kind=NO_ACTION)]

    def update(self, context, potential, terminal=False):
        if not self.training or self.previous is None:
            return
        previous, arm, old_potential = self.previous
        q = self.table.setdefault(previous,[0.]*4)
        bootstrap = 0. if terminal else .98*max(self.table.setdefault(context,[0.]*4))
        target = potential-old_potential+bootstrap
        q[arm] += .12*(target-q[arm])

    def act(self, state):
        context, potential = self.context(state), self.potential(state)
        self.update(context,potential)
        q = self.table.setdefault(context,[0.]*4)
        arm = self.rng.randrange(4) if self.training and self.rng.random()<self.epsilon else max(range(4),key=lambda i:q[i])
        self.previous = context,arm,potential
        return self.proposal(state,arm)

    def finish(self, result):
        self.update(self.context(result.final_state),reward(result),terminal=True)
        self.previous = None

    def to_dict(self):
        return {**super().to_dict(),"table":self.table,"status":getattr(self,"experiment_status","CANDIDATE"),
                "experimentId":getattr(self,"experiment_id",None),"training":False}


def save_evaluated_policy(directory, policy, report):
    """Bind standalone policy and evaluation without changing fitted values."""
    identity = report.get("experimentId") or hashlib.sha256(
        json.dumps(report,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    report = {**report,"experimentId":identity}
    policy.experiment_status = report["status"]
    policy.experiment_id = identity
    report_bytes = json.dumps(report,indent=2).encode("utf-8")
    artifact = {**policy.to_dict(),"evaluationReportSha256":hashlib.sha256(report_bytes).hexdigest()}
    directory.mkdir(parents=True,exist_ok=True)
    (directory/"constrained_rl.json").write_bytes(json.dumps(artifact,indent=2).encode("utf-8"))
    (directory/"constrained_rl_report.json").write_bytes(report_bytes)
    return report


def load_candidate(path=None):
    from src.utils.config import FORECASTS_DIR
    payload = json.loads(Path(path or FORECASTS_DIR/"constrained_rl.json").read_text())
    policy = MaskedQLearningPolicy(payload["table"])
    report_path = Path(path or FORECASTS_DIR/"constrained_rl.json").with_name("constrained_rl_report.json")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    if report and payload.get("experimentId") and payload["experimentId"] != report.get("experimentId"):
        raise ValueError("Policy and evaluation experiment identities disagree")
    if report and payload.get("evaluationReportSha256") and payload["evaluationReportSha256"] != hashlib.sha256(report_path.read_bytes()).hexdigest():
        raise ValueError("Policy evaluation report hash disagrees")
    status = report.get("status","CANDIDATE") if report else payload.get("status","CANDIDATE")
    policy.experiment_status = status
    policy.experiment_id = payload.get("experimentId")
    policy.name += f" ({status.lower()} candidate)"
    return policy


def experiment(directory: Path, episodes=250, validation=50, test=100):
    env = PortEnvironment(ScenarioSpec(berth_count=6, arrivals=18, horizon_hours=60))
    policy = MaskedQLearningPolicy(training=True)
    curve = []
    for index in range(episodes):
        value, result = env.run_episode(policy,TRAIN_SEED_BASE+index)
        policy.finish(result); curve.append(value)
        if (index+1)%25 == 0:
            print(f"Training {index+1}/{episodes}: latest reward {value:.1f}",flush=True)
    policy.training = False
    rules = [FirstComeFirstServed(),GreedyPolicy(),LookaheadPolicy(),policy]
    valid = [evaluate(env,p,episodes=validation,seed_base=8_000_000).to_dict() for p in rules]
    measured = [evaluate(env,p,episodes=test,seed_base=9_000_000).to_dict() for p in rules]
    candidate = next(r for r in valid if r["policyId"] == policy.policy_id)
    strongest = max((r for r in valid if r["policyId"] != policy.policy_id),key=lambda r:r["meanReward"])
    gain = (candidate["meanReward"]-strongest["meanReward"])/max(1,abs(strongest["meanReward"]))
    status = "CANDIDATE" if gain>.02 and candidate["violations"]==0 and candidate["rejectedActions"]==0 and candidate["minReward"]>=strongest["minReward"]-.05*abs(strongest["minReward"]) else "REJECTED"
    # wall-clock: report generation is an actual research-run audit stamp, independent of simulator time.
    report = {"generatedAt":wall_now().isoformat(),"status":status,
        "trainingEpisodes":episodes,"trainingSeedRange":[TRAIN_SEED_BASE,TRAIN_SEED_BASE+episodes-1],
        "validationSeedRange":[8_000_000,8_000_000+validation-1],"testSeedRange":[9_000_000,9_000_000+test-1],
        "validation":valid,"test":measured,"validationGainVsStrongest":round(gain,4),
        "learningCurve":curve,"spec":env.spec.to_dict(),"maskedProposals":policy.masked_proposals,
        "reward":"Existing twin reward: waiting, turnaround, missed departures, completed calls, yard, idle capacity, rejected actions and violations",
        "limitations":"Generated simulator scenarios; not measured savings or real terminal policy performance. State buckets and simulator capacity parameters limit transfer.",
        "promotion":"Candidate simulation only. Operator review and existing advisory approval remain required.",
        "codeSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"seed":168}
    return save_evaluated_policy(directory,policy,report)


if __name__ == "__main__":
    from src.utils.config import FORECASTS_DIR
    result = experiment(FORECASTS_DIR)
    print(json.dumps({k:v for k,v in result.items() if k!="learningCurve"},indent=2))
