"""
NEXUS — Supplier Risk Intelligence Engine
XGBoost-based risk scoring with graph analytics for
cascading disruption simulation and dependency mapping.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import mlflow
import networkx as nx
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import roc_auc_score, classification_report

logger = logging.getLogger("nexus.ml.supplier_risk")


# ─────────────────────────────────────────────
# RISK FEATURES SCHEMA
# ─────────────────────────────────────────────
RISK_FEATURES = [
    # Delivery performance
    "on_time_delivery_rate_90d",     # % on-time deliveries last 90 days
    "avg_delay_days_90d",            # Average delay in days (last 90d)
    "delivery_variance_90d",         # Std dev of delivery times
    "consecutive_delays",            # Count of back-to-back delays
    # Financial health
    "payment_delay_days",            # Days late on payments to us
    "credit_score_normalized",       # Normalized credit rating 0-1
    "revenue_concentration_pct",     # % of our spend they depend on
    "financial_distress_score",      # Altman Z-score derived metric
    # Geopolitical exposure
    "country_risk_score",            # Country-level political stability index
    "trade_restriction_flag",        # Active trade restrictions (0/1)
    "sanctions_flag",                # Any sanctions exposure (0/1)
    "tariff_rate",                   # Current effective tariff rate
    # Operational capacity
    "capacity_utilization_pct",      # Supplier's reported capacity usage
    "lead_time_trend",               # Lead time trend (positive = worsening)
    "quality_rejection_rate",        # % of units rejected in last 90d
    "certifications_valid",          # Active quality certifications (0/1)
    # Weather & Environmental
    "weather_risk_proximity",        # Proximity to active weather events 0-1
    "nat_disaster_risk_score",       # Historical disaster frequency in region
    "climate_vulnerability_index",   # Long-term climate risk score
    # Supply chain dependency
    "single_source_items_pct",       # % of our items sourced only from this supplier
    "substitute_availability_score", # Ease of switching to alternatives 0-1
    "dependency_tier",               # Tier 1, 2, or 3 supplier
    # Behavioral signals
    "communication_responsiveness",  # Response time to inquiries (normalized)
    "contract_compliance_score",     # Contract terms compliance 0-1
    "audit_score",                   # Last audit score (normalized)
]

RISK_TARGET = "disruption_event_90d"  # Binary: did supplier cause disruption in next 90d?


# ─────────────────────────────────────────────
# DATA GENERATION (SYNTHETIC)
# ─────────────────────────────────────────────

def generate_supplier_training_data(n_suppliers: int = 5000, seed: int = 42) -> pd.DataFrame:
    """Generate realistic synthetic supplier risk training dataset."""
    np.random.seed(seed)
    records = []

    for i in range(n_suppliers):
        risk_profile = np.random.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                                         p=[0.4, 0.35, 0.18, 0.07])

        if risk_profile == "LOW":
            otd = np.random.beta(18, 2)         # High on-time rate
            delay = np.random.exponential(0.5)
            credit = np.random.beta(14, 3)
            country_risk = np.random.beta(2, 12)
            disruption_prob = 0.04
        elif risk_profile == "MEDIUM":
            otd = np.random.beta(10, 4)
            delay = np.random.exponential(1.5)
            credit = np.random.beta(8, 5)
            country_risk = np.random.beta(4, 8)
            disruption_prob = 0.18
        elif risk_profile == "HIGH":
            otd = np.random.beta(5, 5)
            delay = np.random.exponential(3.0)
            credit = np.random.beta(4, 8)
            country_risk = np.random.beta(6, 6)
            disruption_prob = 0.42
        else:  # CRITICAL
            otd = np.random.beta(2, 6)
            delay = np.random.exponential(6.0)
            credit = np.random.beta(2, 12)
            country_risk = np.random.beta(8, 4)
            disruption_prob = 0.71

        records.append({
            "supplier_id": f"SUP-{i:05d}",
            "on_time_delivery_rate_90d": np.clip(otd, 0, 1),
            "avg_delay_days_90d": max(0, delay),
            "delivery_variance_90d": np.random.exponential(delay / 2 + 0.1),
            "consecutive_delays": np.random.poisson(delay),
            "payment_delay_days": max(0, np.random.normal(delay * 3, 2)),
            "credit_score_normalized": np.clip(credit, 0, 1),
            "revenue_concentration_pct": np.random.beta(2, 8) * 100,
            "financial_distress_score": 1 - credit + np.random.normal(0, 0.05),
            "country_risk_score": np.clip(country_risk, 0, 1),
            "trade_restriction_flag": int(country_risk > 0.7 and np.random.random() < 0.3),
            "sanctions_flag": int(country_risk > 0.85 and np.random.random() < 0.15),
            "tariff_rate": np.random.uniform(0, 25) if country_risk > 0.5 else np.random.uniform(0, 5),
            "capacity_utilization_pct": np.clip(np.random.normal(75 + (1-credit)*20, 10), 30, 99),
            "lead_time_trend": np.random.normal(delay * 0.1, 0.5),
            "quality_rejection_rate": np.clip(np.random.exponential(0.02 + (1-otd)*0.1), 0, 0.5),
            "certifications_valid": int(credit > 0.5 and np.random.random() < 0.85),
            "weather_risk_proximity": np.random.beta(2, 8),
            "nat_disaster_risk_score": country_risk * np.random.uniform(0.5, 1.5),
            "climate_vulnerability_index": np.random.uniform(0, 1),
            "single_source_items_pct": np.random.beta(2, 5) * 100,
            "substitute_availability_score": np.clip(np.random.beta(4, 4), 0, 1),
            "dependency_tier": np.random.choice([1, 2, 3], p=[0.5, 0.35, 0.15]),
            "communication_responsiveness": np.clip(np.random.beta(10-int(delay), 3), 0, 1),
            "contract_compliance_score": np.clip(np.random.beta(12, 3) * credit, 0, 1),
            "audit_score": np.clip(np.random.beta(14, 3) * credit, 0, 1),
            RISK_TARGET: int(np.random.random() < disruption_prob),
        })

    df = pd.DataFrame(records)
    logger.info(f"Generated {n_suppliers:,} synthetic supplier records | "
                f"Disruption rate: {df[RISK_TARGET].mean():.1%}")
    return df


# ─────────────────────────────────────────────
# MODEL TRAINING
# ─────────────────────────────────────────────

def train_supplier_risk_model(
    df: pd.DataFrame,
    experiment_name: str = "nexus-supplier-risk",
    run_name: Optional[str] = None,
) -> Dict:
    """Train XGBoost supplier risk scoring model with full MLflow tracking."""
    run_name = run_name or f"xgb-risk-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    X = df[RISK_FEATURES]
    y = df[RISK_TARGET]

    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=run_name) as run:
        params = {
            "n_estimators": 400,
            "max_depth": 7,
            "learning_rate": 0.05,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
            "min_child_weight": 5,
            "gamma": 0.1,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "scale_pos_weight": (y == 0).sum() / (y == 1).sum(),  # Handle class imbalance
            "objective": "binary:logistic",
            "eval_metric": ["auc", "aucpr"],
            "random_state": 42,
            "n_jobs": -1,
        }
        mlflow.log_params(params)

        # Stratified K-Fold CV
        model = xgb.XGBClassifier(**params)
        cv_scores = cross_val_score(
            model, X, y, cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
            scoring="roc_auc", n_jobs=-1,
        )
        logger.info(f"CV AUC-ROC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
        mlflow.log_metrics({
            "cv_auc_mean": cv_scores.mean(),
            "cv_auc_std": cv_scores.std(),
        })

        # Final fit on full dataset
        model.fit(X, y, eval_set=[(X, y)], verbose=False)

        # Feature importance
        importance = dict(zip(RISK_FEATURES, model.feature_importances_))
        top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
        logger.info("Top 10 risk features:")
        for feat, imp in top_features:
            logger.info(f"  {feat}: {imp:.4f}")
        mlflow.log_dict(importance, "feature_importance.json")

        # Register model
        mlflow.xgboost.log_model(model, "model")
        model_uri = f"runs:/{run.info.run_id}/model"
        model_version = mlflow.register_model(model_uri, "nexus-supplier-risk")

        if cv_scores.mean() >= 0.88:
            client = mlflow.tracking.MlflowClient()
            client.transition_model_version_stage(
                name="nexus-supplier-risk",
                version=model_version.version,
                stage="Production",
                archive_existing_versions=True,
            )
            logger.info(f"Supplier risk model v{model_version.version} promoted to Production")

        return {
            "run_id": run.info.run_id,
            "model_version": model_version.version,
            "cv_auc_mean": cv_scores.mean(),
            "cv_auc_std": cv_scores.std(),
            "feature_importance": dict(top_features),
        }


# ─────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────

class SupplierRiskEngine:
    """
    Production scoring engine for supplier risk assessment.
    Combines XGBoost risk scoring with NetworkX graph analytics.
    """

    def __init__(self):
        self.model = None
        self.dependency_graph = nx.DiGraph()
        self._load_model()

    def _load_model(self):
        try:
            model_uri = "models:/nexus-supplier-risk/Production"
            self.model = mlflow.xgboost.load_model(model_uri)
            logger.info("Supplier risk model loaded from MLflow registry")
        except Exception as e:
            logger.warning(f"MLflow model unavailable: {e} — using heuristic scoring")

    def score_supplier(self, supplier_features: Dict) -> Dict:
        """Score a single supplier and return risk assessment."""
        features_df = pd.DataFrame([supplier_features])[RISK_FEATURES]

        if self.model:
            disruption_prob = float(self.model.predict_proba(features_df)[0, 1])
        else:
            # Heuristic fallback scoring
            disruption_prob = self._heuristic_score(supplier_features)

        risk_score = int((1 - disruption_prob) * 100)
        risk_level = (
            "CRITICAL" if risk_score < 35 else
            "HIGH" if risk_score < 55 else
            "MEDIUM" if risk_score < 75 else
            "LOW"
        )

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "disruption_probability_90d": disruption_prob,
            "key_risk_factors": self._identify_key_risks(supplier_features),
            "recommended_actions": self._recommend_actions(risk_level, supplier_features),
            "scored_at": datetime.now().isoformat(),
        }

    def _heuristic_score(self, features: Dict) -> float:
        """Rule-based fallback scoring."""
        score = 0.0
        score += (1 - features.get("on_time_delivery_rate_90d", 0.9)) * 0.25
        score += min(features.get("avg_delay_days_90d", 0) / 10, 0.2) * 0.2
        score += features.get("country_risk_score", 0) * 0.2
        score += (1 - features.get("credit_score_normalized", 0.7)) * 0.15
        score += features.get("quality_rejection_rate", 0) * 5 * 0.1
        score += features.get("sanctions_flag", 0) * 0.1
        return min(score, 0.95)

    def _identify_key_risks(self, features: Dict) -> List[str]:
        """Identify the top contributing risk factors."""
        risks = []
        if features.get("on_time_delivery_rate_90d", 1) < 0.85:
            risks.append("Delivery performance below 85% — chronic lateness pattern")
        if features.get("country_risk_score", 0) > 0.6:
            risks.append("Elevated geopolitical risk in supplier country")
        if features.get("payment_delay_days", 0) > 15:
            risks.append("Payment delays detected — financial stress indicator")
        if features.get("quality_rejection_rate", 0) > 0.05:
            risks.append("Quality rejection rate exceeds 5% threshold")
        if features.get("single_source_items_pct", 0) > 50:
            risks.append("High single-source concentration — limited alternatives")
        if features.get("capacity_utilization_pct", 0) > 90:
            risks.append("Supplier near capacity — surge fulfillment risk")
        if features.get("sanctions_flag", 0):
            risks.append("CRITICAL: Active sanctions exposure detected")
        return risks[:4]

    def _recommend_actions(self, risk_level: str, features: Dict) -> List[str]:
        """Generate actionable recommendations based on risk level."""
        actions = {
            "CRITICAL": [
                "Immediately identify and qualify alternative suppliers",
                "Increase safety stock for affected SKUs by 60%",
                "Escalate to Chief Procurement Officer",
                "Activate emergency sourcing protocol",
            ],
            "HIGH": [
                "Place dual-source order with backup supplier",
                "Increase safety stock by 30% for affected SKUs",
                "Schedule weekly supplier performance review",
                "Prepare contingency procurement plan",
            ],
            "MEDIUM": [
                "Monitor delivery performance closely for next 30 days",
                "Increase safety stock by 15% as precautionary measure",
                "Request supplier capacity and risk assessment",
            ],
            "LOW": [
                "Continue standard monitoring cadence",
                "Annual supplier audit as scheduled",
            ],
        }
        return actions.get(risk_level, [])

    # ─── Graph Analytics ──────────────────────
    def build_dependency_graph(self, suppliers: List[Dict], products: List[Dict]) -> nx.DiGraph:
        """Build supplier dependency graph for cascading analysis."""
        G = nx.DiGraph()

        # Add supplier nodes
        for s in suppliers:
            G.add_node(
                s["id"],
                node_type="supplier",
                risk_level=s.get("risk_level", "MEDIUM"),
                risk_score=s.get("risk_score", 70),
                country=s.get("country", "Unknown"),
                volume=s.get("monthly_volume", 0),
            )

        # Add product/warehouse nodes and edges
        for p in products:
            G.add_node(p["id"], node_type="product", category=p.get("category"))
            for supplier_id in p.get("supplier_ids", []):
                if supplier_id in [s["id"] for s in suppliers]:
                    G.add_edge(
                        supplier_id, p["id"],
                        dependency_type="supplies",
                        volume_pct=p.get("volume_from_supplier_pct", 100),
                        is_sole_source=p.get("volume_from_supplier_pct", 100) == 100,
                    )

        self.dependency_graph = G
        logger.info(f"Dependency graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G

    def simulate_disruption_cascade(
        self,
        disrupted_supplier_id: str,
        disruption_severity: float = 1.0,
    ) -> Dict:
        """
        Simulate cascading impact of a supplier disruption.
        Uses BFS propagation with decay factor.
        """
        if not self.dependency_graph.has_node(disrupted_supplier_id):
            return {"error": f"Supplier {disrupted_supplier_id} not in graph"}

        cascade = {disrupted_supplier_id: disruption_severity}
        affected_products = []
        affected_warehouses = []
        total_volume_at_risk = 0

        # BFS cascade simulation
        queue = [(disrupted_supplier_id, disruption_severity)]
        visited = {disrupted_supplier_id}

        while queue:
            node_id, impact = queue.pop(0)
            for successor in self.dependency_graph.successors(node_id):
                if successor not in visited:
                    edge_data = self.dependency_graph.edges[node_id, successor]
                    vol_pct = edge_data.get("volume_pct", 100) / 100
                    propagated_impact = impact * vol_pct

                    cascade[successor] = propagated_impact
                    visited.add(successor)
                    queue.append((successor, propagated_impact))

                    node_data = self.dependency_graph.nodes[successor]
                    if node_data.get("node_type") == "product":
                        affected_products.append({
                            "product_id": successor,
                            "impact_severity": propagated_impact,
                            "sole_source": edge_data.get("is_sole_source", False),
                        })
                    total_volume_at_risk += node_data.get("volume", 0) * propagated_impact

        # Calculate network metrics
        centrality = nx.betweenness_centrality(self.dependency_graph)
        disrupted_centrality = centrality.get(disrupted_supplier_id, 0)

        return {
            "disrupted_supplier": disrupted_supplier_id,
            "severity": disruption_severity,
            "cascade_depth": max(
                nx.shortest_path_length(self.dependency_graph, disrupted_supplier_id, n)
                for n in cascade if n != disrupted_supplier_id
            ) if len(cascade) > 1 else 0,
            "total_nodes_affected": len(cascade),
            "affected_products": affected_products[:20],
            "total_volume_at_risk_units": round(total_volume_at_risk),
            "supplier_network_centrality": round(disrupted_centrality, 4),
            "is_critical_node": disrupted_centrality > 0.15,
            "simulation_timestamp": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Generating synthetic supplier risk data...")
    df = generate_supplier_training_data(n_suppliers=5000)

    print(f"\nDataset shape: {df.shape}")
    print(f"Disruption rate: {df[RISK_TARGET].mean():.1%}")

    print("\nTraining XGBoost supplier risk model...")
    result = train_supplier_risk_model(df)
    print(f"\n✅ Training complete!")
    print(f"  Run ID: {result['run_id']}")
    print(f"  CV AUC-ROC: {result['cv_auc_mean']:.4f} ± {result['cv_auc_std']:.4f}")
    print(f"\nTop risk features:")
    for feat, imp in list(result["feature_importance"].items())[:5]:
        print(f"  {feat}: {imp:.4f}")
