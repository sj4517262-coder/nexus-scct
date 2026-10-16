"""Explicitly labelled sample operations, seeded only once per database."""
import math
from datetime import date, timedelta
from nexus.store import now


def seed(store, con):
    suppliers = [
        ("Shenzhen Electronics Co.", "China", "Electronics", 78, 45000, 22.5, 114.1),
        ("Vietnam Textile Group", "Vietnam", "Textiles", 37, 28000, 21, 105.8),
        ("Munich Industrial GmbH", "Germany", "Machinery", 9, 18000, 48.1, 11.6),
        ("Bangalore Tech Parts", "India", "Components", 33, 32000, 12.9, 77.6),
        ("São Paulo Logistics SA", "Brazil", "Raw Materials", 66, 15000, -23.5, -46.6),
        ("Seoul Semiconductor", "South Korea", "Semiconductors", 7, 38000, 37.5, 127),
        ("Rotterdam Chemicals BV", "Netherlands", "Chemicals", 13, 22000, 51.9, 4.5),
        ("Tokyo Precision Ltd", "Japan", "Precision Parts", 6, 41000, 35.7, 139.7),
        ("Istanbul Metals Corp", "Turkey", "Metals", 44, 19000, 41, 28.9),
        ("Mexico City Auto Parts", "Mexico", "Auto Parts", 26, 27000, 19.4, -99.1),
    ]
    for i, (name, country, category, risk, volume, lat, lng) in enumerate(suppliers, 1):
        store.put(con, "suppliers", dict(id=f"S{i:03}", name=name, country=country, category=category, risk_score=risk, monthly_volume=volume, lat=lat, lng=lng, updated_at=now()))
    warehouses = [
        ("Chicago Hub", 50000, 39000, 41.8, -87.6), ("Dallas DC", 45000, 40950, 32.8, -96.8),
        ("Atlanta SE", 35000, 22400, 33.7, -84.4), ("Seattle Pacific", 40000, 22000, 47.6, -122.3),
        ("Frankfurt Euro", 55000, 45100, 50.1, 8.7), ("Amsterdam Port", 38000, 26980, 52.4, 4.9),
        ("Singapore APAC", 60000, 52800, 1.3, 103.8), ("Dubai Gateway", 42000, 28140, 25.2, 55.3),
    ]
    for i, (name, capacity, stock, lat, lng) in enumerate(warehouses, 1):
        store.put(con, "warehouses", dict(id=f"W{i:03}", name=name, capacity=capacity, stock=stock, lat=lat, lng=lng, updated_at=now()))
    for i in range(1, 25):
        supplier = f"S{(i - 1) % 10 + 1:03}"
        warehouse = f"W{(i - 1) % 8 + 1:03}"
        status = "DELIVERED" if i <= 12 else "DELAYED" if i % 5 == 0 else "IN_TRANSIT"
        store.put(con, "shipments", dict(id=f"SHP-{i:04}", tracking_number=f"NXS-{10000+i}", supplier_id=supplier, warehouse_id=warehouse, carrier=["OceanLink", "Global Freight", "SkyBridge"][i%3], quantity=1000+i*100, cost_usd=2000+i*230, status=status, eta=(date.today()+timedelta(days=-2 if i<=12 else i%10+1)).isoformat(), delivered_at=(date.today()-timedelta(days=1 if i%4==0 else 3)).isoformat() if i<=12 else None, route="Direct", updated_at=now()))
    for i, (title, event_type, severity, affected, value) in enumerate([
        ("Taiwan Strait shipping restrictions", "GEOPOLITICAL", "CRITICAL", ["S001", "S006"], 45000000),
        ("East China Sea weather disruption", "WEATHER", "HIGH", ["S001", "S002"], 8500000),
        ("Shenzhen factory shutdown", "SUPPLIER", "HIGH", ["S001"], 2400000),
    ], 1):
        store.put(con, "disruptions", dict(id=f"DIS-{i:03}", title=title, event_type=event_type, severity=severity, affected_entities=affected, estimated_impact_usd=value, description="Sample disruption for operational workflow evaluation.", status="ACTIVE", detected_at=now(), resolved_at=None))
        store.put(con, "decisions", dict(id=f"DEC-{i:03}", disruption_id=f"DIS-{i:03}", agent="Planner", action=f"Review contingency sourcing: {title}", reasoning="Supplier exposure and estimated impact require a manager review. Approval records a plan; no external purchase is placed.", confidence=0.88, value_usd=value, status="PENDING", created_at=now(), reviewed_by=None))
    for i in range(90):
        day = date.today()-timedelta(days=90-i)
        quantity = round(1200+2*i+180*math.sin(2*math.pi*day.weekday()/7)+40*math.cos(i))
        store.put(con, "demand", dict(id=f"{day}:ALL", date=str(day), quantity=quantity, source="sample"))
    store.event(con, "SYSTEM", "Sample workspace initialized. All records are local; no external orders are executed.")
