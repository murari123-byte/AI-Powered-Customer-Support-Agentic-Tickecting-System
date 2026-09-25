# Classification eval: classify-v2 on qwen2.5:7b (holdout set)

Run 20260925-1849 UTC on 16 labelled tickets (0 failed calls).

| Metric | Result |
|---|---|
| Category accuracy | **93.8%** |
| Priority exactly right | 62.5% |
| Priority within one level | 93.8% |
| Confident enough to act (≥ 0.7) | 100.0% of tickets |
| **Accuracy when the AI acted** | **93.8%** |
| Accuracy when unsure (left for people) | n/a% |
| Average / p95 time per ticket | 6.29 s / 7.22 s |
| Stopped by the code's injection guard | hold-other-02 |

## Per category

| Category | Accuracy |
|---|---|
| ACCOUNT | 100.0% |
| BILLING | 100.0% |
| LOGIN | 100.0% |
| OTHER | 50.0% |
| PAYMENT | 100.0% |
| PRODUCT | 100.0% |
| SECURITY | 100.0% |
| TECHNICAL | 100.0% |

## Most common mistakes

- OTHER -> SECURITY: 1×

## Wrong answers

| Ticket | Expected | Got | Confidence | Model's reason |
|---|---|---|---|---|
| hold-other-02 | OTHER | SECURITY | 1.0 | The ticket involves a system override to admin mode, which is related to security. |
