CAL-2471 needs a same-day calibration recommendation for the five-probe thermal array on bench B.

This is bench calibration work. The useful domain judgment is planning a small cross-temperature measurement pass, correcting for readout-bridge drift, and separating per-probe scale faults from Celsius offset faults without exhausting bench time.

The certified dry-well reference is stable, but the array readout started drifting after the last maintenance window. Use the `arrayctl` instrument interface to discover the available operations and submission schema, collect enough measurements to identify any faulty probes, and submit the calibration record the bench technician should apply.

Maintenance suspects the drift may include both common failure modes:

- multiplicative scale error
- additive offset error in Celsius

Include enough measurement rationale in the submitted calibration record that the bench technician can see which probes you checked, how you separated the suspected fault types, and why the reference probe is safe to use.

Keep the measurement pass focused. The bench is needed for other work this afternoon, so avoid repeated blind probing.
