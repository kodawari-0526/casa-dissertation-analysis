# Scoring and aggregation

Auditability and confidence are kept separate from observed condition. For an auditable target, evidence mass equals confidence; for NA it is zero. Scores are combined with valid-target reweighting at image level, then aggregated image → point → segment with evidence-mass weights.

The visual weights are sidewalk 0.50, visible drainage 0.25, kerb ramp 0.125 and tactile paving 0.125. `RVSI_s` is the sidewalk/drainage robustness score with 0.70/0.30 weights. `SL_s` is the mean of the borough-specific lamp-density percentile and inverse maximum-gap percentile, with zero assigned to segments without linked lamps. The final score is `PSSI_s = 0.80 × EVIS_s + 0.20 × SL_s`; `PSSI_open`, `PSSI_eq` and `PSSI_main` are sensitivity outputs.
