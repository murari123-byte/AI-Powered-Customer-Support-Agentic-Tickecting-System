# Classification eval: classify-v2 on qwen2.5:7b (main set)

Run 20260925-1847 UTC on 64 labelled tickets (0 failed calls).

| Metric | Result |
|---|---|
| Category accuracy | **93.8%** |
| Priority exactly right | 71.9% |
| Priority within one level | 95.3% |
| Confident enough to act (≥ 0.7) | 100.0% of tickets |
| **Accuracy when the AI acted** | **93.8%** |
| Accuracy when unsure (left for people) | n/a% |
| Average / p95 time per ticket | 6.44 s / 7.1 s |
| Stopped by the code's injection guard | other-07 |

## Per category

| Category | Accuracy |
|---|---|
| ACCOUNT | 87.5% |
| BILLING | 100.0% |
| LOGIN | 87.5% |
| OTHER | 87.5% |
| PAYMENT | 87.5% |
| PRODUCT | 100.0% |
| SECURITY | 100.0% |
| TECHNICAL | 100.0% |

## Most common mistakes

- PAYMENT -> TECHNICAL: 1×
- ACCOUNT -> PRODUCT: 1×
- LOGIN -> TECHNICAL: 1×
- OTHER -> PRODUCT: 1×

## Wrong answers

| Ticket | Expected | Got | Confidence | Model's reason |
|---|---|---|---|---|
| payment-02 | PAYMENT | TECHNICAL | 0.9 | Error message indicates an issue with the app, not a payment or billing problem. |
| account-03 | ACCOUNT | PRODUCT | 0.9 | The customer is asking how to use a feature of the product. |
| login-08 | LOGIN | TECHNICAL | 0.8 | The issue is with the app's performance, specifically login speed. |
| other-08 | OTHER | PRODUCT | 0.8 | The customer is asking about participating in user research, which is related to how the product can be used. |
