"""
NEXUS — Reinforcement Learning Inventory Optimization Engine
PPO-based policy trained on multi-echelon supply chain environment.
Optimizes: safety stock, reorder timing, warehouse rebalancing.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mlflow
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import (
    BaseCallback, CheckpointCallback, EvalCallback,
)
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import VecNormalize, DummyVecEnv

logger = logging.getLogger("nexus.ml.inventory_rl")

# ─────────────────────────────────────────────
# ENVIRONMENT CONFIGURATION
# ─────────────────────────────────────────────
ENV_CONFIG = {
    "n_warehouses":         8,
    "n_skus":              20,
    "max_steps":          365,          # 1-year episode
    "holding_cost_rate":    0.25,       # 25% annual holding cost
    "stockout_penalty":   150.0,        # $ per unit-day stockout
    "transfer_cost":        2.5,        # $ per unit per transfer
    "order_cost":         500.0,        # Fixed order cost
    "lead_time_mean":      14,          # days
    "lead_time_std":        3,
    "demand_mean":        500.0,        # units/day
    "demand_std":         120.0,
    "max_capacity":    50000,
    "initial_inventory": 25000,
    "service_level_target": 0.97,
    "rebalance_max_fraction": 0.30,
}


# ─────────────────────────────────────────────
# SUPPLY CHAIN GYM ENVIRONMENT
# ─────────────────────────────────────────────
class SupplyChainEnv(gym.Env):
    """
    Multi-echelon supply chain optimization environment.
    State: warehouse inventory levels, in-transit inventory, demand forecasts
    Action: reorder quantities + inter-warehouse transfers
    Reward: profit - (holding costs + stockout penalties + transfer costs)
    """

    metadata = {"render_modes": ["human", "rgb_array"]}

    def __init__(self, config: Dict = ENV_CONFIG, render_mode: Optional[str] = None):
        super().__init__()
        self.config = config
        self.render_mode = render_mode
        self.n_wh  = config["n_warehouses"]
        self.n_sku = config["n_skus"]

        # Action space: [reorder_qty (n_wh × n_sku), transfer_fractions (n_wh × n_wh)]
        # Normalized to [0, 1] — scaled in step()
        n_reorder   = self.n_wh * self.n_sku
        n_transfers = self.n_wh * self.n_wh
        self.action_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(n_reorder + n_transfers,),
            dtype=np.float32,
        )

        # Observation space: [inventory (n_wh × n_sku), in_transit, demand_forecast, day_of_year, utilization]
        n_obs = (self.n_wh * self.n_sku * 2) + (self.n_wh * self.n_sku) + self.n_wh + 2
        self.observation_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(n_obs,),
            dtype=np.float32,
        )

        self.reset()

    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None):
        super().reset(seed=seed)
        cfg = self.config

        # Initialize state
        self.step_count = 0
        self.inventory = np.full(
            (self.n_wh, self.n_sku),
            cfg["initial_inventory"] / self.n_sku,
            dtype=np.float64,
        )
        self.in_transit = np.zeros((self.n_wh, self.n_sku), dtype=np.float64)
        self.lead_time_tracker: List[Dict] = []

        # Demand parameters (heterogeneous across SKUs)
        self.demand_means = np.random.uniform(
            cfg["demand_mean"] * 0.3,
            cfg["demand_mean"] * 1.7,
            (self.n_wh, self.n_sku),
        )
        self.demand_stds = self.demand_means * (cfg["demand_std"] / cfg["demand_mean"])

        # Seasonality factors
        self.seasonal_factors = np.array([
            1 + 0.3 * np.sin(2 * np.pi * d / 365 + np.random.uniform(0, 2 * np.pi))
            for d in range(cfg["max_steps"])
        ])

        # Metrics tracking
        self.episode_metrics = {
            "total_revenue": 0.0,
            "total_holding_cost": 0.0,
            "total_stockout_cost": 0.0,
            "total_transfer_cost": 0.0,
            "total_order_cost": 0.0,
            "stockout_events": 0,
            "service_level_events": [],
        }

        return self._get_obs(), {}

    def _get_obs(self) -> np.ndarray:
        cfg = self.config
        max_cap = cfg["max_capacity"]

        # Normalize all state components to [0, 1]
        inv_norm  = (self.inventory   / max_cap).flatten().astype(np.float32)
        tran_norm = (self.in_transit  / max_cap).flatten().astype(np.float32)

        # Demand forecast (next 7 days)
        season = self.seasonal_factors[min(self.step_count, len(self.seasonal_factors) - 1)]
        forecast = (self.demand_means * season / max_cap * 7).flatten().astype(np.float32)

        # Utilization per warehouse
        util = (self.inventory.sum(axis=1) / max_cap).astype(np.float32)

        # Time features
        day_of_year = np.array([self.step_count / cfg["max_steps"]], dtype=np.float32)
        week_season = np.array([season], dtype=np.float32)

        return np.concatenate([inv_norm, tran_norm, forecast, util, day_of_year, week_season])

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        cfg = self.config
        n_reorder = self.n_wh * self.n_sku

        # Decode actions
        reorder_actions   = action[:n_reorder].reshape(self.n_wh, self.n_sku)
        transfer_actions  = action[n_reorder:].reshape(self.n_wh, self.n_wh)

        # Scale reorder actions (0–1) → actual order quantities
        max_reorder = cfg["max_capacity"] * 0.4
        reorder_qty = reorder_actions * max_reorder

        # Scale transfer actions → fractions of source inventory
        np.fill_diagonal(transfer_actions, 0)  # No self-transfer
        transfer_fractions = transfer_actions * cfg["rebalance_max_fraction"]

        reward = 0.0

        # ── 1. Process Incoming Shipments ─────────────────
        arrived = []
        for shipment in self.lead_time_tracker:
            shipment["days_remaining"] -= 1
            if shipment["days_remaining"] <= 0:
                arrived.append(shipment)
        for s in arrived:
            self.lead_time_tracker.remove(s)
            wh, sku = s["warehouse"], s["sku"]
            self.in_transit[wh, sku] = max(0, self.in_transit[wh, sku] - s["qty"])
            self.inventory[wh, sku] = min(
                cfg["max_capacity"] / self.n_sku,
                self.inventory[wh, sku] + s["qty"],
            )

        # ── 2. Execute Transfers ───────────────────────────
        transfer_cost = 0.0
        for src in range(self.n_wh):
            for dst in range(self.n_wh):
                if src == dst:
                    continue
                for sku in range(self.n_sku):
                    frac  = float(transfer_fractions[src, dst])
                    qty   = min(self.inventory[src, sku] * frac,
                                cfg["max_capacity"] / self.n_sku - self.inventory[dst, sku])
                    qty   = max(0.0, qty)
                    if qty > 1.0:
                        self.inventory[src, sku] -= qty
                        self.inventory[dst, sku] += qty
                        transfer_cost += qty * cfg["transfer_cost"]

        self.episode_metrics["total_transfer_cost"] += transfer_cost
        reward -= transfer_cost

        # ── 3. Place Reorders ──────────────────────────────
        order_cost = 0.0
        for wh in range(self.n_wh):
            for sku in range(self.n_sku):
                qty = float(reorder_qty[wh, sku])
                if qty > 10:
                    lead_time = max(1, int(np.random.normal(
                        cfg["lead_time_mean"], cfg["lead_time_std"]
                    )))
                    self.lead_time_tracker.append({
                        "warehouse": wh, "sku": sku,
                        "qty": qty, "days_remaining": lead_time,
                    })
                    self.in_transit[wh, sku] += qty
                    order_cost += cfg["order_cost"]

        self.episode_metrics["total_order_cost"] += order_cost
        reward -= order_cost

        # ── 4. Simulate Demand ─────────────────────────────
        season = self.seasonal_factors[min(self.step_count, len(self.seasonal_factors) - 1)]
        demand = np.random.normal(
            self.demand_means * season,
            self.demand_stds,
        ).clip(min=0)

        # ── 5. Fulfill Demand ──────────────────────────────
        holding_cost   = 0.0
        stockout_cost  = 0.0
        revenue        = 0.0
        service_events = []

        for wh in range(self.n_wh):
            for sku in range(self.n_sku):
                d = demand[wh, sku]
                avail = self.inventory[wh, sku]

                fulfilled = min(d, avail)
                lost      = max(0.0, d - avail)

                self.inventory[wh, sku] = max(0.0, avail - fulfilled)

                # Revenue from fulfilled demand
                unit_price = 50.0  # Simplified unit price
                revenue += fulfilled * unit_price

                # Stockout penalty
                if lost > 0:
                    stockout_cost += lost * cfg["stockout_penalty"]
                    self.episode_metrics["stockout_events"] += 1

                # Service level tracking
                service_level = fulfilled / max(d, 1e-8)
                service_events.append(service_level)

        # Holding cost for end-of-day inventory
        daily_holding = (self.inventory.sum() *
                         (50.0 * cfg["holding_cost_rate"] / 365))
        holding_cost += daily_holding

        # Accumulate metrics
        self.episode_metrics["total_revenue"]      += revenue
        self.episode_metrics["total_holding_cost"] += holding_cost
        self.episode_metrics["total_stockout_cost"] += stockout_cost
        self.episode_metrics["service_level_events"].extend(service_events)

        reward += revenue - holding_cost - stockout_cost

        self.step_count += 1
        terminated = self.step_count >= self.config["max_steps"]
        truncated  = False

        info = {}
        if terminated:
            info["episode_metrics"] = self.episode_metrics
            info["avg_service_level"] = float(np.mean(service_events)) if service_events else 0.0
            info["total_profit"] = float(
                self.episode_metrics["total_revenue"]
                - self.episode_metrics["total_holding_cost"]
                - self.episode_metrics["total_stockout_cost"]
                - self.episode_metrics["total_transfer_cost"]
                - self.episode_metrics["total_order_cost"]
            )

        return self._get_obs(), float(reward), terminated, truncated, info

    def render(self):
        if self.render_mode == "human":
            total_inv = self.inventory.sum()
            avg_util  = total_inv / (self.n_wh * self.config["max_capacity"] / self.n_sku)
            print(f"Day {self.step_count:3d} | "
                  f"Total Inventory: {total_inv:,.0f} | "
                  f"Avg Utilization: {avg_util:.1%} | "
                  f"Stockout Events: {self.episode_metrics['stockout_events']}")


# ─────────────────────────────────────────────
# MLFLOW CALLBACK
# ─────────────────────────────────────────────
class MLflowCallback(BaseCallback):
    """Log RL training metrics to MLflow every N steps."""

    def __init__(self, verbose: int = 0, log_freq: int = 1000):
        super().__init__(verbose)
        self.log_freq = log_freq

    def _on_step(self) -> bool:
        if self.n_calls % self.log_freq == 0:
            mlflow.log_metrics({
                "rl/mean_reward": float(np.mean(self.locals.get("rewards", [0]))),
                "rl/total_timesteps": self.num_timesteps,
            }, step=self.num_timesteps)
        return True

    def _on_rollout_end(self):
        if self.locals.get("infos"):
            for info in self.locals["infos"]:
                metrics = info.get("episode_metrics", {})
                if metrics:
                    mlflow.log_metrics({
                        "rl/episode_revenue":      metrics.get("total_revenue", 0),
                        "rl/episode_holding_cost": metrics.get("total_holding_cost", 0),
                        "rl/episode_stockouts":    metrics.get("stockout_events", 0),
                    }, step=self.num_timesteps)


# ─────────────────────────────────────────────
# TRAINING PIPELINE
# ─────────────────────────────────────────────
def train_inventory_rl(
    total_timesteps: int = 2_000_000,
    n_envs: int = 8,
    experiment_name: str = "nexus-inventory-rl",
    run_name: Optional[str] = None,
    save_dir: str = "ml/models/inventory_rl",
) -> Dict:
    """Train PPO inventory optimization agent with MLflow tracking."""
    run_name = run_name or f"ppo-inventory-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    Path(save_dir).mkdir(parents=True, exist_ok=True)

    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=run_name) as run:
        # Log hyperparameters
        ppo_params = {
            "algorithm": "PPO",
            "n_envs": n_envs,
            "total_timesteps": total_timesteps,
            "learning_rate": 3e-4,
            "n_steps": 2048,
            "batch_size": 512,
            "n_epochs": 10,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_range": 0.2,
            "ent_coef": 0.01,
            "vf_coef": 0.5,
            "max_grad_norm": 0.5,
        }
        mlflow.log_params({**ppo_params, **ENV_CONFIG})

        # Create vectorized environments
        def make_env():
            env = SupplyChainEnv(config=ENV_CONFIG)
            env = Monitor(env)
            return env

        train_env = make_vec_env(make_env, n_envs=n_envs)
        train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True, clip_obs=10.0)

        eval_env = make_vec_env(make_env, n_envs=2)
        eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=False, clip_obs=10.0)

        # Build PPO agent
        logger.info(f"Building PPO agent | n_envs={n_envs} | timesteps={total_timesteps:,}")
        model = PPO(
            policy="MlpPolicy",
            env=train_env,
            learning_rate=ppo_params["learning_rate"],
            n_steps=ppo_params["n_steps"],
            batch_size=ppo_params["batch_size"],
            n_epochs=ppo_params["n_epochs"],
            gamma=ppo_params["gamma"],
            gae_lambda=ppo_params["gae_lambda"],
            clip_range=ppo_params["clip_range"],
            ent_coef=ppo_params["ent_coef"],
            vf_coef=ppo_params["vf_coef"],
            max_grad_norm=ppo_params["max_grad_norm"],
            policy_kwargs={"net_arch": [512, 512, 256]},
            verbose=1,
        )

        # Callbacks
        callbacks = [
            MLflowCallback(log_freq=5000),
            EvalCallback(
                eval_env,
                best_model_save_path=f"{save_dir}/best_model",
                log_path=f"{save_dir}/eval_logs",
                eval_freq=50_000,
                n_eval_episodes=10,
                deterministic=True,
            ),
            CheckpointCallback(
                save_freq=200_000,
                save_path=f"{save_dir}/checkpoints",
                name_prefix="ppo_inventory",
            ),
        ]

        # Train
        logger.info(f"Starting PPO training | run_id={run.info.run_id}")
        model.learn(total_timesteps=total_timesteps, callback=callbacks, progress_bar=True)

        # Evaluate final policy
        logger.info("Evaluating final policy...")
        from stable_baselines3.common.evaluation import evaluate_policy
        mean_reward, std_reward = evaluate_policy(
            model, eval_env, n_eval_episodes=20, deterministic=True
        )
        logger.info(f"Final Policy: mean_reward={mean_reward:.2f} ± {std_reward:.2f}")

        mlflow.log_metrics({
            "rl/final_mean_reward": mean_reward,
            "rl/final_std_reward": std_reward,
        })

        # Save model and normalizer
        model_path = f"{save_dir}/final_model"
        norm_path  = f"{save_dir}/vec_normalize.pkl"
        model.save(model_path)
        train_env.save(norm_path)

        # Log artifacts
        mlflow.log_artifact(f"{model_path}.zip")
        mlflow.log_artifact(norm_path)

        # Register model
        mlflow.pyfunc.log_model("inventory_rl_model", python_model=InventoryRLWrapper(model))
        model_version = mlflow.register_model(
            f"runs:/{run.info.run_id}/inventory_rl_model",
            "nexus-inventory-rl",
        )
        if mean_reward > 0:
            client = mlflow.tracking.MlflowClient()
            client.transition_model_version_stage(
                name="nexus-inventory-rl",
                version=model_version.version,
                stage="Production",
                archive_existing_versions=True,
            )

        return {
            "run_id": run.info.run_id,
            "model_version": model_version.version,
            "mean_reward": mean_reward,
            "std_reward": std_reward,
            "model_path": model_path,
        }


# ─────────────────────────────────────────────
# INFERENCE ENGINE
# ─────────────────────────────────────────────
class InventoryRLWrapper(mlflow.pyfunc.PythonModel):
    """MLflow wrapper for production RL inference."""

    def __init__(self, model):
        self.model = model

    def predict(self, context, model_input):
        obs = np.array(model_input).astype(np.float32)
        action, _ = self.model.predict(obs, deterministic=True)
        return action


class InventoryOptimizer:
    """
    Production inventory optimization engine.
    Loads trained PPO policy and generates reorder/transfer recommendations.
    """

    def __init__(self):
        self.model: Optional[PPO] = None
        self.env_config = ENV_CONFIG
        self._load_model()

    def _load_model(self):
        try:
            model_uri = "models:/nexus-inventory-rl/Production"
            self.model = mlflow.pyfunc.load_model(model_uri)
            logger.info("RL inventory model loaded from MLflow registry")
        except Exception as e:
            logger.warning(f"RL model unavailable: {e} — using heuristic policy")

    def optimize(self, warehouse_states: List[Dict]) -> Dict:
        """
        Generate inventory optimization recommendations.
        warehouse_states: list of {warehouse_id, inventory, capacity, demand_forecast, ...}
        """
        if not self.model:
            return self._heuristic_optimize(warehouse_states)

        obs = self._build_observation(warehouse_states)
        action = self.model.predict(obs)
        return self._decode_action(action, warehouse_states)

    def _heuristic_optimize(self, warehouse_states: List[Dict]) -> Dict:
        """Rule-based fallback: EOQ + safety stock heuristics."""
        recommendations = []
        for wh in warehouse_states:
            util = wh.get("utilization_pct", 70)
            if util < 30:
                recommendations.append({
                    "warehouse_id": wh["warehouse_id"],
                    "action": "REORDER",
                    "quantity": int(wh.get("capacity", 50000) * 0.40),
                    "urgency": "HIGH",
                    "reasoning": f"Inventory at {util}% — below safety stock threshold",
                    "estimated_stockout_days": max(0, (30 - util) / 5),
                })
            elif util > 90:
                recommendations.append({
                    "warehouse_id": wh["warehouse_id"],
                    "action": "TRANSFER_OUT",
                    "quantity": int(wh.get("capacity", 50000) * 0.15),
                    "urgency": "CRITICAL",
                    "reasoning": f"At {util}% capacity — risk of overflow and service failure",
                    "estimated_stockout_days": None,
                })
        return {
            "recommendations": recommendations,
            "policy": "HEURISTIC_EOQ",
            "total_actions": len(recommendations),
            "generated_at": datetime.now().isoformat(),
        }

    def _build_observation(self, warehouse_states: List[Dict]) -> np.ndarray:
        """Convert warehouse states to RL observation vector."""
        max_cap = self.env_config["max_capacity"]
        obs_parts = []
        for wh in warehouse_states[:self.env_config["n_warehouses"]]:
            inv = wh.get("current_inventory", 0) / max_cap
            util = wh.get("utilization_pct", 50) / 100
            forecast = wh.get("demand_forecast_7d", 3500) / max_cap
            obs_parts.extend([inv, util, forecast])

        # Pad if fewer warehouses than expected
        expected_len = self.env_config["n_warehouses"] * 3 + 2
        obs = np.array(obs_parts, dtype=np.float32)
        obs = np.pad(obs, (0, max(0, expected_len - len(obs))), mode="constant")
        return obs[:expected_len]

    def _decode_action(self, action: np.ndarray, warehouse_states: List[Dict]) -> Dict:
        """Decode RL action vector into human-readable recommendations."""
        n_wh   = len(warehouse_states)
        n_sku  = self.env_config["n_skus"]
        n_reorder = n_wh * n_sku

        reorder_actions  = action[:n_reorder].reshape(n_wh, n_sku) if len(action) > n_reorder else np.zeros((n_wh, n_sku))
        transfer_actions = action[n_reorder:].reshape(n_wh, n_wh) if len(action) > n_reorder + n_wh * n_wh else np.zeros((n_wh, n_wh))

        recommendations = []
        for i, wh in enumerate(warehouse_states):
            total_reorder = float(reorder_actions[i].sum()) * self.env_config["max_capacity"] * 0.4
            if total_reorder > 500:
                recommendations.append({
                    "warehouse_id": wh["warehouse_id"],
                    "action": "REORDER",
                    "quantity": int(total_reorder),
                    "urgency": "HIGH" if total_reorder > 5000 else "MEDIUM",
                    "reasoning": "RL policy recommends restocking based on demand forecast and safety stock",
                    "policy": "PPO",
                })

        return {
            "recommendations": recommendations,
            "policy": "PPO_RL",
            "total_actions": len(recommendations),
            "generated_at": datetime.now().isoformat(),
        }


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train NEXUS Inventory RL Agent")
    parser.add_argument("--timesteps", type=int, default=2_000_000)
    parser.add_argument("--n-envs",    type=int, default=8)
    parser.add_argument("--experiment", type=str, default="nexus-inventory-rl")
    parser.add_argument("--run-name",   type=str, default=None)
    parser.add_argument("--save-dir",   type=str, default="ml/models/inventory_rl")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    print(f"\n🤖 Training PPO Inventory Optimization Agent")
    print(f"   Timesteps: {args.timesteps:,} | Envs: {args.n_envs}")

    result = train_inventory_rl(
        total_timesteps=args.timesteps,
        n_envs=args.n_envs,
        experiment_name=args.experiment,
        run_name=args.run_name,
        save_dir=args.save_dir,
    )

    print(f"\n✅ Training Complete!")
    print(f"   Run ID:       {result['run_id']}")
    print(f"   Mean Reward:  {result['mean_reward']:.2f} ± {result['std_reward']:.2f}")
    print(f"   Model Path:   {result['model_path']}")
