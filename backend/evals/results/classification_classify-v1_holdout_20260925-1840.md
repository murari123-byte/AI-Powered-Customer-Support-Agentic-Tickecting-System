# Classification eval: classify-v1 on qwen2.5:7b (holdout set)

Run 20260925-1840 UTC on 16 labelled tickets (0 failed calls).

| Metric | Result |
|---|---|
| Category accuracy | **87.5%** |
| Priority exactly right | 62.5% |
| Priority within one level | 93.8% |
| Confident enough to act (≥ 0.7) | 100.0% of tickets |
| **Accuracy when the AI acted** | **87.5%** |
| Accuracy when unsure (left for people) | n/a% |
| Average / p95 time per ticket | 6.75 s / 7.65 s |
| Stopped by the code's injection guard | hold-other-02 |

## Per category

| Category | Accuracy |
|---|---|
| ACCOUNT | 100.0% |
| BILLING | 100.0% |
| LOGIN | 100.0% |
| OTHER | 50.0% |
| PAYMENT | 50.0% |
| PRODUCT | 100.0% |
| SECURITY | 100.0% |
| TECHNICAL | 100.0% |

## Most common mistakes

- PAYMENT -> PRODUCT: 1×
- OTHER -> SECURITY: 1×

## Wrong answers

| Ticket | Expected | Got | Confidence | Model's reason |
|---|---|---|---|---|
| hold-payment-01 | PAYMENT | PRODUCT | 0.8 | Customer is asking about a feature option for upgrading the plan. |
| hold-other-02 | OTHER | SECURITY | 1.0 | The ticket mentions SYSTEM OVERRIDE and admin mode, which implies a security concern, and the urgency suggests it's critical. |
