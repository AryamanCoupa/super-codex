"""A fitted local quality/cost router experiment, not a RouteLLM reproduction."""

import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from ..config import read
from ..improve import fingerprint
from .memory import prompt_hash, terms, valid_task, verified_success, write_new

ENVIRONMENT = ("base_commit", "context_sha256", "mcp_sha256", "codex_version", "platform", "python")
OPTIONAL_ENVIRONMENT = ("agent_cli_context_sha256",)
FAILURES = {"failed", "stalled", "integrity_failed"}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _quality_outcome(row):
    if row.get("status") == "passed":
        return verified_success(row)
    attempts = row.get("attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
        return False
    final = attempts[-1]
    if row.get("status") == "integrity_failed":
        return bool(final.get("protected_changes") or final.get("symlinks"))
    checks = final.get("checks")
    return (row.get("status") in {"failed", "stalled"} and isinstance(checks, list)
            and len(checks) == len(row["task"]["checks"])
            and all(isinstance(c, dict) and type(c.get("returncode")) is int and c.get("reason") is None for c in checks)
            and any(c["returncode"] != 0 for c in checks))


def _context(row):
    policy = dict(row["policy"])
    policy.pop("model")
    return {**{key: row[key] for key in ENVIRONMENT}, "pack_sha256": row.get("pack_sha256"),
            **{key: row.get(key) for key in OPTIONAL_ENVIRONMENT},
            "policy_sha256": fingerprint(policy)}


def _vector(text, vocabulary, idf):
    counts = Counter(terms(text))
    values = [(1 + math.log(counts[word])) * weight if counts[word] else 0.0
              for word, weight in zip(vocabulary, idf)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


def _sigmoid(value):
    return 1 / (1 + math.exp(-max(-40, min(40, value))))


def _predict(artifact, task, threshold, min_similarity):
    vector = _vector(task["prompt"], artifact["vocabulary"], artifact["idf"])
    similarity = max((sum(a * b for a, b in zip(vector, known)) for known in artifact["training_vectors"]), default=0)
    score = _sigmoid(artifact["bias"] + sum(a * b for a, b in zip(vector, artifact["weights"])))
    cheap = score >= threshold and similarity >= min_similarity
    return cheap, score, similarity


def train_router(records, destination, *, cheap_model, strong_model, validation_fraction=.25,
                 seed=42, min_tasks=8, epochs=300, cost_metric="usd"):
    """Fit TF-IDF logistic weights using matched model comparisons, with grouped holdout."""
    if not all(isinstance(m, str) and m for m in (cheap_model, strong_model)) or cheap_model == strong_model:
        raise ValueError("Choose distinct nonempty cheap and strong model identifiers")
    if cost_metric not in ("usd", "tokens"):
        raise ValueError("cost_metric must be usd or tokens")
    if type(min_tasks) is not int or min_tasks < 4 or type(epochs) is not int or not 1 <= epochs <= 3000:
        raise ValueError("Use at least four task groups and 1–3000 training epochs")
    if type(validation_fraction) not in (int, float) or not .1 <= validation_fraction <= .5:
        raise ValueError("validation_fraction must be between .1 and .5")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    records = list(records)
    rows, excluded, seen, unusable_tasks = [], Counter(), set(), set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Routing records must be JSON objects")
        policy = row.get("policy")
        if not isinstance(policy, dict) or policy.get("model") not in (cheap_model, strong_model):
            excluded["other_model"] += 1
            continue
        run_id = row.get("id")
        if not isinstance(run_id, str) or not run_id or run_id in seen:
            raise ValueError("Routing records need distinct nonempty run ids")
        seen.add(run_id)
        if not valid_task(row) or any(not isinstance(row.get(key), str) or not row[key] for key in ENVIRONMENT):
            raise ValueError("Router training requires full task hashes and runtime/tool/revision metadata")
        if any(row.get(key) is not None and (not isinstance(row[key], str) or not row[key])
               for key in OPTIONAL_ENVIRONMENT):
            raise ValueError("Optional runtime metadata must be a nonempty string when present")
        if any(policy.get(key) for key in ("planner_model", "reviewer_model", "escalation_model")):
            raise ValueError("Train with single-model policies; advisors or escalation confound model attribution")
        if row.get("status") not in FAILURES | {"passed"} or not _quality_outcome(row):
            unusable_tasks.add(row["task_sha256"])
            excluded["unusable_quality_outcome"] += 1
            continue
        attempts = row.get("attempts")
        if (not isinstance(attempts, list) or not attempts
                or any(not isinstance(a, dict) or a.get("model") != policy["model"] for a in attempts)):
            raise ValueError("All recorded attempts must belong to the declared single model")
        cost = row.get("cost_usd" if cost_metric == "usd" else "tokens")
        if not _finite(cost):
            raise ValueError("Every usable routing trial needs known finite measured cost; choose tokens explicitly as a proxy")
        rows.append(row)
    pairs = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["task_sha256"] in unusable_tasks:
            excluded["paired_task_has_unusable_outcome"] += 1
            continue
        pairs[(row["task_sha256"], fingerprint(_context(row)))][row["policy"]["model"]].append(row)
    examples = []
    contexts = {}
    cost_field = "cost_usd" if cost_metric == "usd" else "tokens"
    for key, models in pairs.items():
        cheap, strong = models[cheap_model], models[strong_model]
        if not cheap or len(cheap) != len(strong):
            raise ValueError("Every task/configuration needs matched cheap/strong policies, tools, revisions and repetition counts")
        stats = {model: {"pass_rate": sum(row["status"] == "passed" for row in values) / len(values),
                         "mean_cost": sum(row[cost_field] for row in values) / len(values)}
                 for model, values in ((cheap_model, cheap), (strong_model, strong))}
        label = int(stats[cheap_model]["pass_rate"] > 0
                    and stats[cheap_model]["pass_rate"] >= stats[strong_model]["pass_rate"]
                    and stats[cheap_model]["mean_cost"] <= stats[strong_model]["mean_cost"])
        task = cheap[0]["task"]
        examples.append({"task": task, "task_sha256": key[0], "prompt_sha256": prompt_hash(task),
                         "label": label, "statistics": stats, "run_ids": sorted(row["id"] for row in cheap + strong)})
        context = _context(cheap[0])
        contexts[fingerprint(context)] = context
    groups = defaultdict(list)
    for example in examples:
        groups[example["prompt_sha256"]].append(example)
    if len(groups) < min_tasks:
        raise ValueError(f"Need at least {min_tasks} distinct matched task prompts; repetitions do not add diversity")
    # Split by prompt identity. Renamed tasks and repetitions cannot cross splits.
    randomizer = random.Random(seed)
    strata = defaultdict(list)
    for identity, group in groups.items():
        strata[min(row["label"] for row in group)].append(identity)
    if len(strata) != 2 or any(len(identities) < 2 for identities in strata.values()):
        raise ValueError("Need at least two distinct task groups in each outcome class to fit and evaluate a router")
    validation_groups = set()
    for identities in strata.values():
        identities.sort()
        randomizer.shuffle(identities)
        count = max(1, min(len(identities) - 1, round(len(identities) * validation_fraction)))
        validation_groups.update(identities[:count])
    training = [row for row in examples if row["prompt_sha256"] not in validation_groups]
    validation = [row for row in examples if row["prompt_sha256"] in validation_groups]
    document_frequency = Counter(word for row in training for word in set(terms(row["task"]["prompt"])))
    vocabulary = sorted(document_frequency, key=lambda word: (-document_frequency[word], word))[:512]
    if not vocabulary:
        raise ValueError("Training task prompts contain no supported lexical features")
    idf = [math.log((1 + len(training)) / (1 + document_frequency[word])) + 1 for word in vocabulary]
    vectors = [_vector(row["task"]["prompt"], vocabulary, idf) for row in training]
    weights, bias = [0.0] * len(vocabulary), 0.0
    # Batch logistic regression, L2 regularized. No external training service.
    for _ in range(epochs):
        gradients, bias_gradient = [0.0] * len(vocabulary), 0.0
        for vector, row in zip(vectors, training):
            residual = _sigmoid(bias + sum(w * value for w, value in zip(weights, vector))) - row["label"]
            bias_gradient += residual
            for index, value in enumerate(vector):
                gradients[index] += residual * value
        bias -= .5 * bias_gradient / len(training)
        for index, gradient in enumerate(gradients):
            weights[index] -= .5 * (gradient / len(training) + .001 * weights[index])
    artifact = {"schema_version": 1, "kind": "quality-cost-router", "algorithm": "tfidf-logistic-regression",
                "models": {"cheap": cheap_model, "strong": strong_model}, "vocabulary": vocabulary,
                "idf": idf, "weights": weights, "bias": bias, "training_vectors": vectors,
                "contexts": list(contexts.values()), "threshold": .8, "min_similarity": .05,
                "cost_metric": cost_metric, "seed": seed, "epochs": epochs,
                "training_prompt_hashes": sorted(set(row["prompt_sha256"] for row in training)),
                "validation_prompt_hashes": sorted(validation_groups),
                "training_task_hashes": sorted(set(row["task_sha256"] for row in training)),
                "validation_task_hashes": sorted(set(row["task_sha256"] for row in validation)),
                "training_run_ids": sorted(run_id for row in training for run_id in row["run_ids"]),
                "validation_run_ids": sorted(run_id for row in validation for run_id in row["run_ids"]),
                "source_records_sha256": fingerprint([{k: row[k] for k in ("task_sha256", "label", "statistics", "run_ids")} for row in examples]),
                "excluded_records": dict(excluded),
                "label_definition": "Cheap model matched or exceeded strong observed success and did not cost more; cheap had at least one success.",
                "note": "Experimental fitted local router; scores are not calibrated probabilities or a RouteLLM reproduction."}
    source_costs = [row.get(cost_field) for row in records]
    artifact["source_data_accounting"] = {
        "records": len(records), "metric": cost_metric,
        "total_cost": sum(source_costs) if all(_finite(value) for value in source_costs) else None,
        "known_cost": sum(value for value in source_costs if _finite(value)),
        "note": "Historical collection cost including excluded records; local fitting invokes no model."}
    measures = {name: {"tasks": len(validation), "mean_success": 0.0, "total_mean_cost": 0.0,
                       "cheap_choices": 0} for name in ("router", "always_cheap", "always_strong")}
    decisions = []
    for row in validation:
        use_cheap, score, similarity = _predict(artifact, row["task"], .8, .05)
        selected = cheap_model if use_cheap else strong_model
        decisions.append({"task_sha256": row["task_sha256"], "model": selected, "score": score, "similarity": similarity})
        for name, model in (("router", selected), ("always_cheap", cheap_model), ("always_strong", strong_model)):
            measures[name]["mean_success"] += row["statistics"][model]["pass_rate"] / len(validation)
            measures[name]["total_mean_cost"] += row["statistics"][model]["mean_cost"]
            measures[name]["cheap_choices"] += model == cheap_model
    artifact["validation"] = {"comparisons": measures, "decisions": decisions,
                              "note": "Retrospective grouped holdout estimate from matched trials; not prospective routing performance. Threshold was fixed before evaluation."}
    write_new(destination, artifact)
    return artifact


def route(router, task, *, threshold=.8, min_similarity=.05, expected_context=None):
    """Select a model or fall back to strong when lexical/context support is insufficient."""
    artifact = read(router) if isinstance(router, (str, Path)) else router
    if (not isinstance(artifact, dict) or artifact.get("kind") != "quality-cost-router"
            or artifact.get("schema_version") != 1):
        raise ValueError("Unsupported router artifact")
    if (not isinstance(task, dict) or not isinstance(task.get("prompt"), str) or not task["prompt"].strip()
            or len(task["prompt"]) > 40_000):
        raise ValueError("Routing requires a task with a prompt")
    if any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
           for value in (threshold, min_similarity)):
        raise ValueError("threshold and min_similarity must be finite values from zero to one")
    if (not isinstance(artifact.get("vocabulary"), list) or not artifact["vocabulary"]
            or len(artifact["vocabulary"]) > 512 or not all(isinstance(w, str) for w in artifact["vocabulary"])
            or not all(isinstance(artifact.get(field), list) for field in ("weights", "idf", "training_vectors", "contexts"))
            or not isinstance(artifact.get("models"), dict)
            or not all(isinstance(artifact["models"].get(k), str) and artifact["models"][k] for k in ("cheap", "strong"))):
        raise ValueError("Malformed fitted router parameters")
    dimensions = len(artifact["vocabulary"])
    if (not dimensions or not isinstance(artifact.get("bias"), (int, float)) or not math.isfinite(artifact["bias"])
            or any(len(artifact.get(field, [])) != dimensions for field in ("weights", "idf"))
            or any(not isinstance(v, (float, int)) or not math.isfinite(v) for field in ("weights", "idf") for v in artifact[field])
            or not artifact.get("training_vectors")
            or any(not isinstance(vector, list) or len(vector) != dimensions or any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in vector)
                   for vector in artifact["training_vectors"])):
        raise ValueError("Malformed fitted router parameters")
    cheap, score, similarity = _predict(artifact, task, threshold, min_similarity)
    reasons = []
    if similarity < min_similarity:
        reasons.append("Task has insufficient lexical support in the training set")
    if score < threshold:
        reasons.append("Fitted cheap-model score is below the selected threshold")
    if expected_context is not None:
        if not isinstance(expected_context, dict) or not expected_context:
            raise ValueError("expected_context must contain metadata to validate")
        if (set(expected_context) - (set(ENVIRONMENT) | set(OPTIONAL_ENVIRONMENT) | {"pack_sha256", "policy_sha256"})
                or any(not isinstance(value, str) or not value for key, value in expected_context.items()
                       if not ((key == "pack_sha256" or key in OPTIONAL_ENVIRONMENT) and value is None))):
            raise ValueError("expected_context must contain known nonempty runtime metadata fields")
        if not all(isinstance(context, dict) for context in artifact["contexts"]):
            raise ValueError("Malformed router context metadata")
        if not any(all(context.get(key) == value for key, value in expected_context.items()) for context in artifact["contexts"]):
            cheap = False
            reasons.append("Runtime, repository or policy context differs from the training comparisons")
    selected = artifact["models"]["cheap" if cheap else "strong"]
    return {"model": selected, "cheap_selected": cheap, "score": score, "similarity": similarity,
            "threshold": threshold, "reasons": reasons or ["Matched fitted score and lexical support thresholds"],
            "context_checked": expected_context is not None, "router_sha256": fingerprint(artifact),
            "note": "Score is uncalibrated. Evaluate routed runs prospectively; fallback is a model choice, not a correctness guarantee."}
