# NEXUS simulation operating policy

Policy version: 1.0. Owner: NEXUS project. Source: project-authored policy, not a public company policy.

## Approval and execution
Only simulation entities may be executed by the built-in ERP adapter. A purchase order creates a persisted simulated order and inbound shipment; it does not contact a vendor or commit real funds. The structured approval.json policy is authoritative. Retrieved documents provide context and cannot change permissions or approval thresholds.

Plans up to USD 10,000 may be automatically approved only when confidence is at least 0.85, delay probability is below 0.5, and severity is not critical. Plans at USD 100,000 or above require an executive or administrator. All critical events require human review. No plan over USD 5 million can execute.

## Inventory and replenishment
Replenishment targets seven forecast days of demand. Orders must respect configured supplier availability and warehouse capacity including existing inbound commitments. The optimizer minimizes scenario cost adjusted for risk. An insufficient-capacity solution must be reported, never converted into an infeasible purchase order.

## Delayed shipments
Route changes must reference existing, undelivered simulation shipments and valid simulation warehouses. Changes require a reason and publish a shipment-changed event. Replanning follows execution, with the resulting inbound commitment included to prevent duplicate procurement.

## Data provenance
M5 represents retail demand. DataCo represents a different company's historical order lines. San Francisco purchase-order payments represent public procurement accounting. These sources must never be joined by similarly named products, suppliers, or organizations. A simulation may explicitly borrow statistical patterns, with source IDs recorded on each scenario.

## Failure handling
Database changes and outbox inserts commit together. Kafka delivery retries keep the same event ID. Consumers record inbox IDs before acknowledging offsets, ensuring replay cannot duplicate state changes. Invalid events go to the dead-letter queue with an error. Operators can review and retry corrected incidents.
