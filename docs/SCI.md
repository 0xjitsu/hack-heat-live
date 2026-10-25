# Software Carbon Intensity note

This is an engineering estimate for the optional Most Environmentally Impactful prize. It is not a meter reading. The functional unit is one answered board question (one call to `query_board` or `POST /api/query`).

The method is the [Software Carbon Intensity](https://sci.greensoftware.foundation/) specification from the Green Software Foundation:

```text
SCI = ((E * I) + M) / R
```

- `E` is energy consumed by the software for the functional unit, in kWh.
- `I` is the location-based grid emission factor, in kgCO2e/kWh.
- `M` is embodied emissions allocated to that unit, in kgCO2e.
- `R` is the functional unit. Here `R = 1` query.

## What the design avoids

The hot path does not call a model. A question is a filter over the 64-row JSON board. GitLab Duo, and its model calls, run only when someone asks the radar-curator flow to review a candidate row. Reads stay deterministic.

The Cloud Run spec sets `minScale: 0`, `maxScale: 2`, and CPU throttling. An idle week costs no request CPU. The container is `python:3.12-slim` plus the package and the board. It does not install a timezone database, a web framework, or a GPU library.

## Worked example

Assumptions, all chosen to overestimate the service:

| Input | Value | Why |
|---|---|---|
| Active time per query | 0.1 s | Local queries finish in a few milliseconds. |
| Average power while serving | 5 W | Well above a throttled Cloud Run request. |
| Grid factor `I` | 0.4168 kgCO2e/kWh | Energy Market Authority, Singapore, average operating margin for 2022. Replace with the latest EMA factor before relying on the absolute number. |
| Embodied `M` per query | 0 | Scale-to-zero has no idle server to amortize. A full study would add a share of the build laptop. |
| Region | `asia-southeast1` | Same grid as the Asia/Singapore clock the board uses. |

```text
E = 5 W * 0.1 s = 0.5 J = 1.39e-7 kWh
E * I = 1.39e-7 * 0.4168 = 5.8e-8 kgCO2e
SCI ≈ 5.8e-8 kgCO2e per query
```

A person re-checking the same board for 15 minutes on a 30 W laptop:

```text
E = 30 W * 900 s = 0.0075 kWh
E * I ≈ 0.0031 kgCO2e ≈ 3.1 g
```

Under these assumptions, one manual pass is on the order of ten thousand queries. The weekly newsletter job is one pass, not one pass per reader.

An always-on 5 W instance for seven days is about `5 W * 168 h = 0.84 kWh`, or about 350 gCO2e at the same factor, before it answers anything. Scaling to zero removes that idle term. That is the operational gain this design is claiming.

Replace `I` with the current EMA factor if you opt in on the Devpost form. Say that the figure is an estimate from the assumptions above.
