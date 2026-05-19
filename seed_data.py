"""
NEXUS — Enterprise Data Seeding Script
Generates realistic synthetic data for all platform entities:
  suppliers, warehouses, shipments, inventory, disruptions,
  demand history, procurement transactions, routes
"""

import argparse
import json
import logging
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexus.seed")

random.seed(42)
np.random.seed(42)

# ─────────────────────────────────────────────
# REFERENCE DATA
# ─────────────────────────────────────────────
COUNTRIES = {
    "China": {"region": "APAC", "risk_base": 0.45, "currency": "CNY", "ports": ["Shanghai", "Shenzhen", "Guangzhou"]},
    "Vietnam": {"region": "APAC", "risk_base": 0.35, "currency": "VND", "ports": ["Ho Chi Minh City", "Haiphong"]},
    "Germany": {"region": "EMEA", "risk_base": 0.08, "currency": "EUR", "ports": ["Hamburg", "Bremen"]},
    "India": {"region": "APAC", "risk_base": 0.32, "currency": "INR", "ports": ["Mumbai", "Chennai"]},
    "Brazil": {"region": "LATAM", "risk_base": 0.52, "currency": "BRL", "ports": ["Santos", "Rio de Janeiro"]},
    "South Korea": {"region": "APAC", "risk_base": 0.12, "currency": "KRW", "ports": ["Busan", "Incheon"]},
    "Netherlands": {"region": "EMEA", "risk_base": 0.06, "currency": "EUR", "ports": ["Rotterdam", "Amsterdam"]},
    "Japan": {"region": "APAC", "risk_base": 0.10, "currency": "JPY", "ports": ["Yokohama", "Tokyo", "Nagoya"]},
    "Turkey": {"region": "EMEA", "risk_base": 0.48, "currency": "TRY", "ports": ["Istanbul", "Mersin"]},
    "Mexico": {"region": "LATAM", "risk_base": 0.38, "currency": "MXN", "ports": ["Manzanillo", "Veracruz"]},
    "USA": {"region": "Americas", "risk_base": 0.07, "currency": "USD", "ports": ["Los Angeles", "Houston", "New York"]},
    "Taiwan": {"region": "APAC", "risk_base": 0.55, "currency": "TWD", "ports": ["Kaohsiung", "Keelung"]},
}

PRODUCT_CATEGORIES = [
    {"name": "Electronics", "avg_value": 850, "fragile": True, "lead_time_days": 45},
    {"name": "Semiconductors", "avg_value": 2200, "fragile": True, "lead_time_days": 60},
    {"name": "Textiles", "avg_value": 85, "fragile": False, "lead_time_days": 30},
    {"name": "Machinery", "avg_value": 15000, "fragile": False, "lead_time_days": 90},
    {"name": "Auto Parts", "avg_value": 320, "fragile": False, "lead_time_days": 35},
    {"name": "Chemicals", "avg_value": 450, "fragile": False, "lead_time_days": 25},
    {"name": "Raw Materials", "avg_value": 180, "fragile": False, "lead_time_days": 20},
    {"name": "Precision Parts", "avg_value": 1200, "fragile": True, "lead_time_days": 50},
    {"name": "Metals", "avg_value": 280, "fragile": False, "lead_time_days": 28},
    {"name": "Components", "avg_value": 650, "fragile": True, "lead_time_days": 40},
]

DISRUPTION_TYPES = [
    {"type": "WEATHER", "titles": ["Typhoon in East China Sea", "Hurricane in Gulf of Mexico", "Severe flooding in Vietnam", "Blizzard affecting Northeast US ports"]},
    {"type": "GEOPOLITICAL", "titles": ["Trade restrictions imposed", "Port workers strike", "Customs delays at border", "Sanctions affecting supplier region"]},
    {"type": "SUPPLIER", "titles": ["Factory shutdown", "Quality recall issued", "Capacity reduction", "Financial distress reported"]},
    {"type": "PORT", "titles": ["Port congestion", "Equipment failure at terminal", "Cyber attack on port systems", "Customs backlog"]},
    {"type": "DEMAND", "titles": ["Unexpected demand surge", "Product launch demand spike", "Stockout risk identified", "Demand drop due to recession signal"]},
    {"type": "LOGISTICS", "titles": ["Container shortage", "Carrier capacity reduction", "Fuel price spike disrupting economics", "Driver shortage"]},
]

CARRIER_NAMES = ["Maersk", "MSC", "CMA CGM", "COSCO", "Evergreen", "Hapag-Lloyd", "ONE", "Yang Ming"]

# ─────────────────────────────────────────────
# GENERATORS
# ─────────────────────────────────────────────

def gen_suppliers(n: int = 50) -> List[Dict]:
    """Generate realistic supplier profiles."""
    logger.info(f"Generating {n} suppliers...")
    countries = list(COUNTRIES.keys())
    categories = PRODUCT_CATEGORIES
    suppliers = []

    for i in range(n):
        country = random.choice(countries)
        country_data = COUNTRIES[country]
        category = random.choice(categories)
        risk_base = country_data["risk_base"] + random.uniform(-0.1, 0.2)
        risk_score = max(5, min(99, int((1 - risk_base) * 100 + random.gauss(0, 8))))

        risk_level = (
            "CRITICAL" if risk_score < 35 else
            "HIGH" if risk_score < 55 else
            "MEDIUM" if risk_score < 75 else "LOW"
        )

        suppliers.append({
            "id": f"SUP-{i+1:04d}",
            "name": f"{country} {category['name']} {'Co.' if i % 3 == 0 else 'Ltd' if i % 3 == 1 else 'GmbH'}",
            "country": country,
            "region": country_data["region"],
            "currency": country_data["currency"],
            "category": category["name"],
            "risk_level": risk_level,
            "risk_score": risk_score,
            "on_time_delivery_rate": round(min(0.99, max(0.4, 1 - risk_base + random.gauss(0, 0.05))), 3),
            "avg_lead_time_days": category["lead_time_days"] + random.randint(-5, 15),
            "monthly_volume_units": random.randint(5000, 80000),
            "annual_spend_usd": random.randint(500_000, 15_000_000),
            "tier": random.choice([1, 1, 1, 2, 2, 3]),
            "certifications": random.sample(["ISO9001", "ISO14001", "CTPAT", "AEO", "SA8000"], k=random.randint(1, 4)),
            "primary_port": random.choice(country_data["ports"]),
            "established_year": random.randint(1985, 2015),
            "employee_count": random.randint(50, 5000),
            "created_at": datetime.now().isoformat(),
        })

    return suppliers


def gen_warehouses(n: int = 12) -> List[Dict]:
    """Generate warehouse facility profiles."""
    logger.info(f"Generating {n} warehouses...")
    locations = [
        {"city": "Chicago", "state": "IL", "country": "USA", "lat": 41.878, "lng": -87.629, "region": "Americas"},
        {"city": "Dallas", "state": "TX", "country": "USA", "lat": 32.776, "lng": -96.797, "region": "Americas"},
        {"city": "Atlanta", "state": "GA", "country": "USA", "lat": 33.749, "lng": -84.388, "region": "Americas"},
        {"city": "Seattle", "state": "WA", "country": "USA", "lat": 47.606, "lng": -122.332, "region": "Americas"},
        {"city": "Los Angeles", "state": "CA", "country": "USA", "lat": 34.052, "lng": -118.244, "region": "Americas"},
        {"city": "Frankfurt", "state": "HE", "country": "Germany", "lat": 50.110, "lng": 8.682, "region": "EMEA"},
        {"city": "Amsterdam", "state": "NH", "country": "Netherlands", "lat": 52.370, "lng": 4.895, "region": "EMEA"},
        {"city": "London", "state": "ENG", "country": "UK", "lat": 51.508, "lng": -0.128, "region": "EMEA"},
        {"city": "Singapore", "state": "SG", "country": "Singapore", "lat": 1.352, "lng": 103.820, "region": "APAC"},
        {"city": "Dubai", "state": "DU", "country": "UAE", "lat": 25.204, "lng": 55.270, "region": "EMEA"},
        {"city": "Shanghai", "state": "SH", "country": "China", "lat": 31.224, "lng": 121.469, "region": "APAC"},
        {"city": "Tokyo", "state": "TK", "country": "Japan", "lat": 35.689, "lng": 139.692, "region": "APAC"},
    ]

    warehouses = []
    for i, loc in enumerate(locations[:n]):
        capacity = random.choice([30000, 40000, 50000, 60000, 75000, 100000])
        utilization = random.uniform(0.45, 0.95)
        inventory = int(capacity * utilization)
        status = "CRITICAL" if utilization > 0.92 else "WARNING" if utilization > 0.82 else "OPTIMAL"

        warehouses.append({
            "id": f"WH-{i+1:03d}",
            "name": f"{loc['city']} {'Hub' if i < 4 else 'DC' if i < 8 else 'Gateway'}",
            "city": loc["city"],
            "state": loc["state"],
            "country": loc["country"],
            "region": loc["region"],
            "lat": loc["lat"],
            "lng": loc["lng"],
            "capacity_units": capacity,
            "current_inventory_units": inventory,
            "utilization_pct": round(utilization * 100, 1),
            "status": status,
            "sq_footage": capacity * 8,
            "employees": random.randint(40, 250),
            "automation_level": random.choice(["MANUAL", "SEMI_AUTO", "AUTOMATED", "HIGHLY_AUTOMATED"]),
            "temperature_controlled": random.choice([True, False]),
            "reorder_point_pct": 30,
            "safety_stock_pct": 15,
            "last_cycle_count": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
            "created_at": datetime.now().isoformat(),
        })

    return warehouses


def gen_shipments(n: int = 300, suppliers: List[Dict] = None, warehouses: List[Dict] = None) -> List[Dict]:
    """Generate active and historical shipment records."""
    logger.info(f"Generating {n} shipments...")
    if not suppliers or not warehouses:
        raise ValueError("Suppliers and warehouses required for shipment generation")

    statuses = {
        "IN_TRANSIT": 0.45, "AT_PORT": 0.15, "CUSTOMS": 0.10,
        "DELIVERED": 0.20, "DELAYED": 0.08, "EXCEPTION": 0.02,
    }
    shipments = []

    for i in range(n):
        supplier = random.choice(suppliers)
        warehouse = random.choice(warehouses)
        carrier = random.choice(CARRIER_NAMES)
        category = next((c for c in PRODUCT_CATEGORIES if c["name"] == supplier["category"]), PRODUCT_CATEGORIES[0])
        status = random.choices(list(statuses.keys()), weights=list(statuses.values()))[0]

        origin_date = datetime.now() - timedelta(days=random.randint(1, 45))
        lead_time = category["lead_time_days"] + random.randint(-5, 15)
        eta = origin_date + timedelta(days=lead_time)
        delay_days = random.randint(1, 8) if status in ["DELAYED", "EXCEPTION"] else 0

        shipments.append({
            "id": f"SHP-{i+1:05d}",
            "tracking_number": f"{carrier[:3].upper()}{random.randint(100000000, 999999999)}",
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "destination_warehouse_id": warehouse["id"],
            "destination_city": warehouse["city"],
            "origin_country": supplier["country"],
            "origin_port": supplier["primary_port"],
            "carrier": carrier,
            "transport_mode": random.choice(["SEA", "SEA", "SEA", "AIR", "RAIL"]),
            "status": status,
            "category": category["name"],
            "quantity_units": random.randint(500, 25000),
            "weight_kg": random.randint(1000, 50000),
            "volume_cbm": random.randint(10, 200),
            "value_usd": random.randint(50_000, 5_000_000),
            "origin_date": origin_date.isoformat(),
            "eta": eta.isoformat(),
            "actual_arrival": (eta + timedelta(days=delay_days)).isoformat() if status == "DELIVERED" else None,
            "delay_days": delay_days,
            "is_delayed": delay_days > 0,
            "delay_risk_score": round(random.uniform(0, 1), 3),
            "customs_status": random.choice(["CLEARED", "PENDING", "HOLD"]) if status in ["AT_PORT", "CUSTOMS", "DELIVERED"] else None,
            "last_event": f"{status.replace('_', ' ').title()} — {(datetime.now() - timedelta(hours=random.randint(1, 72))).strftime('%Y-%m-%d %H:%M')}",
            "created_at": origin_date.isoformat(),
        })

    return shipments


def gen_demand_history(
    warehouses: List[Dict], n_days: int = 365, n_skus: int = 100
) -> pd.DataFrame:
    """Generate 1-year demand history for all warehouses and SKUs."""
    logger.info(f"Generating {n_days}-day demand history for {n_skus} SKUs × {len(warehouses)} warehouses...")
    records = []
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="D")
    categories = [c["name"] for c in PRODUCT_CATEGORIES]

    for sku_num in range(n_skus):
        sku_id = f"SKU-{sku_num:04d}"
        category = random.choice(categories)
        base_demand = random.uniform(100, 2000)

        for wh in warehouses[:4]:  # Subset of warehouses per SKU
            for date in dates:
                trend = base_demand * (1 + 0.015 * (date - dates[0]).days / 365)
                dow_factor = [1.15, 1.10, 1.05, 1.0, 0.90, 0.72, 0.65][date.dayofweek]
                seasonal = 1 + 0.20 * np.sin(2 * np.pi * date.month / 12)
                black_friday = 3.4 if (date.month == 11 and date.day >= 22 and date.dayofweek == 4) else 1.0
                cyber_monday = 2.8 if (date.month == 11 and date.day >= 25 and date.dayofweek == 0) else 1.0
                noise = np.random.lognormal(0, 0.12)

                qty = max(0, trend * dow_factor * seasonal * black_friday * cyber_monday * noise)
                records.append({
                    "date": date,
                    "sku_id": sku_id,
                    "warehouse_id": wh["id"],
                    "category": category,
                    "region": wh["region"],
                    "quantity": round(qty),
                    "price": round(random.uniform(10, 1000), 2),
                })

    df = pd.DataFrame(records)
    logger.info(f"Generated {len(df):,} demand records")
    return df


def gen_disruptions(n: int = 50) -> List[Dict]:
    """Generate historical and current disruption events."""
    logger.info(f"Generating {n} disruption events...")
    disruptions = []
    severities = {"LOW": 0.25, "MEDIUM": 0.35, "HIGH": 0.28, "CRITICAL": 0.12}

    for i in range(n):
        disp_type = random.choice(DISRUPTION_TYPES)
        severity = random.choices(list(severities.keys()), weights=list(severities.values()))[0]
        days_ago = random.randint(0, 60)
        duration_days = {"LOW": 2, "MEDIUM": 5, "HIGH": 12, "CRITICAL": 21}[severity]
        is_active = days_ago < duration_days

        disruptions.append({
            "id": f"DISR-{i+1:04d}",
            "event_type": disp_type["type"],
            "severity": severity,
            "title": random.choice(disp_type["titles"]),
            "description": f"Disruption event affecting supply chain operations. Severity: {severity}.",
            "status": "ACTIVE" if is_active else "RESOLVED",
            "affected_entities": [f"SUP-{random.randint(1, 50):04d}" for _ in range(random.randint(1, 4))],
            "estimated_impact_usd": {
                "LOW": random.randint(50_000, 500_000),
                "MEDIUM": random.randint(500_000, 5_000_000),
                "HIGH": random.randint(5_000_000, 50_000_000),
                "CRITICAL": random.randint(50_000_000, 500_000_000),
            }[severity],
            "shipments_affected": random.randint(1, 50),
            "detected_at": (datetime.now() - timedelta(days=days_ago)).isoformat(),
            "resolved_at": None if is_active else (datetime.now() - timedelta(days=max(0, days_ago - duration_days))).isoformat(),
            "mitigation_actions": random.randint(0, 8),
            "ai_confidence": round(random.uniform(0.75, 0.99), 3),
        })

    return disruptions


def gen_kpi_history(warehouses: List[Dict], n_days: int = 90) -> List[Dict]:
    """Generate 90-day KPI history for trend analysis."""
    logger.info(f"Generating {n_days}-day KPI history...")
    records = []
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq="D")

    for date in dates:
        # Simulate gradual improvement trend with some variance
        progress = (date - dates[0]).days / n_days
        records.append({
            "date": date.isoformat(),
            "otif_pct": round(min(99, max(70, 82 + progress * 12 + np.random.normal(0, 2))), 2),
            "fill_rate_pct": round(min(99, max(80, 88 + progress * 8 + np.random.normal(0, 1.5))), 2),
            "inventory_turnover_annual": round(max(3, 6.5 + progress * 1.5 + np.random.normal(0, 0.3)), 2),
            "warehouse_utilization_pct": round(min(98, max(50, 72 + np.random.normal(0, 5))), 1),
            "transport_cost_per_unit_usd": round(max(1.5, 3.2 - progress * 0.8 + np.random.normal(0, 0.2)), 3),
            "stockout_probability_pct": round(max(0.1, 8 - progress * 5 + np.random.normal(0, 0.5)), 2),
            "supplier_reliability_pct": round(min(99, max(75, 85 + progress * 7 + np.random.normal(0, 2))), 2),
            "delay_risk_pct": round(max(1, 25 - progress * 12 + np.random.normal(0, 2)), 2),
            "ai_decisions_count": random.randint(20, 180),
            "ai_auto_approve_rate_pct": round(random.uniform(88, 97), 1),
            "disruptions_active": random.randint(0, 6),
        })

    return records


# ─────────────────────────────────────────────
# MAIN SEEDING PIPELINE
# ─────────────────────────────────────────────

def seed_all(
    n_suppliers: int = 50,
    n_warehouses: int = 12,
    n_shipments: int = 300,
    n_disruptions: int = 50,
    n_demand_skus: int = 100,
    n_demand_days: int = 365,
    output_dir: str = "data/seeds",
) -> Dict:
    """Run complete data seeding pipeline and save to disk."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"Starting NEXUS data seeding pipeline → {output_dir}")
    results = {}

    # Generate all entities
    suppliers = gen_suppliers(n_suppliers)
    warehouses = gen_warehouses(n_warehouses)
    shipments = gen_shipments(n_shipments, suppliers, warehouses)
    disruptions = gen_disruptions(n_disruptions)
    kpi_history = gen_kpi_history(warehouses)

    # Save JSON files
    for name, data in [
        ("suppliers", suppliers), ("warehouses", warehouses),
        ("shipments", shipments), ("disruptions", disruptions),
        ("kpi_history", kpi_history),
    ]:
        path = f"{output_dir}/{name}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"✅ Saved {len(data):,} {name} → {path}")
        results[name] = len(data)

    # Generate and save demand history as Parquet
    demand_df = gen_demand_history(warehouses, n_demand_days, n_demand_skus)
    demand_path = f"{output_dir}/demand_history.parquet"
    demand_df.to_parquet(demand_path, index=False)
    logger.info(f"✅ Saved {len(demand_df):,} demand records → {demand_path}")
    results["demand_history"] = len(demand_df)

    # Summary report
    logger.info("\n" + "="*60)
    logger.info("NEXUS DATA SEEDING COMPLETE")
    logger.info("="*60)
    for entity, count in results.items():
        logger.info(f"  {entity:25s}: {count:>10,} records")
    logger.info("="*60)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed NEXUS platform with synthetic data")
    parser.add_argument("--suppliers", type=int, default=50)
    parser.add_argument("--warehouses", type=int, default=12)
    parser.add_argument("--shipments", type=int, default=300)
    parser.add_argument("--disruptions", type=int, default=50)
    parser.add_argument("--demand-skus", type=int, default=100)
    parser.add_argument("--demand-days", type=int, default=365)
    parser.add_argument("--output-dir", type=str, default="data/seeds")
    args = parser.parse_args()

    result = seed_all(
        n_suppliers=args.suppliers,
        n_warehouses=args.warehouses,
        n_shipments=args.shipments,
        n_disruptions=args.disruptions,
        n_demand_skus=args.demand_skus,
        n_demand_days=args.demand_days,
        output_dir=args.output_dir,
    )
    print(f"\n✅ Seeding complete — {sum(result.values()):,} total records generated")
