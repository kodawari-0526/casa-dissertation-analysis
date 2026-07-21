# Street-network preparation

`build_network.py` queries the current OpenStreetMap network inside a 100 m buffer around each study borough, simplifies topology, converts the result to an undirected physical network, applies the dissertation's highway and access filters, clips it to the borough boundary and removes duplicates and implausible fragments.

The production network contained 6,228 segments. Because OpenStreetMap changes over time, the script records any count difference in its QA file. Pass `--strict-count` when reproducing against a fixed local snapshot and require an exact match.
