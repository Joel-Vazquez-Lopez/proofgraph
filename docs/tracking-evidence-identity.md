# Tracking evidence identity and legacy graph compatibility

## Confirmed defect

Before this fix, merchant-submitted shipment IDs were `ship_<carrier>_<last4>` and lookup observation IDs were `obs_carrier_<last4>`. Different tracking numbers sharing a suffix could overwrite the prior `GraphNode` when `EvidenceGraph.add_node` reused the same ID. Repeated lookups also replaced observations, discarding prior event history.

## New rules

1. Shipment identity is the **full carrier/tracking pair**, canonicalized by case-folding the carrier and uppercasing the tracking ID, encoded in a SHA-256 digest prefix. The full raw tracking number does not appear in the opaque graph ID.
2. When a graph already contains a shipment matching the **full** carrier/tracking pair, reuse its existing ID (including `ship_usps_9999` legacy IDs) without overwriting that node.
3. If no exact pair exists, allocate a new `ship_<digest>` ID, with a random collision fallback if an existing node has that opaque ID.
4. Every carrier verification attempt creates a distinct `obs_carrier_<digest>_<nonce>` observation event. Old observations, even historic `obs_carrier_9999` nodes, are retained rather than overwritten.
5. No endpoint, Pydantic schema, table, field name, or evaluator policy changes.

## Compatibility and limitations

- Previously persisted graph IDs remain stable; existing graph edges are never renamed.
- New submissions matching old shipment content reuse the legacy shipment ID.
- Evidence already overwritten in historical stored graphs **cannot be reconstructed** by this change.
- Repeated carrier lookups now append observations instead of replacing them; this intentionally increases observation/event counts and makes history auditable. The existing evaluator chooses observations according to its existing semantics. Handling conflicting observations across time belongs to Agent 1 and is not redefined here.
- `POST /verify-carrier` still operates on the first shipment when a case has multiple tracking records; selecting a particular shipment requires a separately coordinated API contract.
- Independent verification vs synthetic fixture truth is handled separately by PR A (#5), not this identity patch.

## Tests

Distinct full tracking numbers sharing the same last four digits, case-insensitive idempotent resubmissions, preserved known and unknown carrier observations, repeated verification append-only history, and compatibility with old four-digit IDs.
