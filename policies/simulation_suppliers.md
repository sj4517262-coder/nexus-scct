# Simulation supplier reference

Source: project-authored synthetic supplier profiles. These are not DataCo vendors or San Francisco contractors.

SIM-SUP-01, Pacific replenishment partner: standard service, unit cost USD 4.20, configured lead time 4 days, order capacity 500,000 units. Operates only inside the simulator.

SIM-SUP-02, Regional express partner: expedited service, unit cost USD 5.10, configured lead time 2 days, order capacity 300,000 units. Operates only inside the simulator.

SIM-SUP-03, Consolidated freight partner: consolidated service, unit cost USD 3.80, configured lead time 6 days, order capacity 800,000 units. Operates only inside the simulator.

Delay probabilities are produced by the trained DataCo delay model using explicitly supplied scenario attributes. Applying that model to synthetic suppliers is a simulation assumption, not a validated prediction for a real vendor.
