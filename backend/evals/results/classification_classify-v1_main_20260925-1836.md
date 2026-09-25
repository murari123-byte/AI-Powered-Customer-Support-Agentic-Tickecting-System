# Classification eval: classify-v1 on qwen2.5:7b

Run 20260925-1836 UTC on 64 labelled tickets (0 failed calls).

| Metric | Result |
|---|---|
| Category accuracy | **81.2%** |
| Priority exactly right | 73.4% |
| Priority within one level | 96.9% |
| Confident enough to act (≥ 0.7) | 98.4% of tickets |
| **Accuracy when the AI acted** | **81.0%** |
| Accuracy when unsure (left for people) | 100.0% |
| Average / p95 time per ticket | 6.46 s / 7.59 s |

## Per category

| Category | Accuracy |
|---|---|
| ACCOUNT | 87.5% |
| BILLING | 100.0% |
| LOGIN | 100.0% |
| OTHER | 25.0% |
| PAYMENT | 75.0% |
| PRODUCT | 100.0% |
| SECURITY | 87.5% |
| TECHNICAL | 75.0% |

## Most common mistakes

- OTHER -> PRODUCT: 5×
- TECHNICAL -> PRODUCT: 2×
- PAYMENT -> TECHNICAL: 1×
- PAYMENT -> PRODUCT: 1×
- ACCOUNT -> PRODUCT: 1×

## Wrong answers

| Ticket | Expected | Got | Confidence | Model's reason |
|---|---|---|---|---|
| payment-02 | PAYMENT | TECHNICAL | 0.9 | Error message indicates a technical issue with the payment process. |
| payment-06 | PAYMENT | PRODUCT | 0.8 | The customer is asking about a payment method for a subscription plan. |
| technical-05 | TECHNICAL | PRODUCT | 0.8 | The issue is about a visual UI element and not a billing, security, or technical problem. |
| technical-08 | TECHNICAL | PRODUCT | 0.8 | The issue is about a visual aspect of the product, specifically readability in dark mode. |
| account-03 | ACCOUNT | PRODUCT | 0.9 | The customer is asking about a feature (inviting a colleague) and how-to instructions. |
| security-08 | SECURITY | TECHNICAL | 0.8 | The issue is related to data visibility after logout, which is a technical bug. |
| other-01 | OTHER | PRODUCT | 0.8 | The customer is asking about a business partnership, which is a feature request or inquiry about the product. |
| other-02 | OTHER | PRODUCT | 0.7 | The customer is asking about a job opportunity, which is a feature request or inquiry. |
| other-04 | OTHER | PRODUCT | 0.8 | The customer is asking for information about the product. |
| other-05 | OTHER | PRODUCT | 0.8 | The customer is asking for a non-technical, product-related question. |
| other-07 | OTHER | SECURITY | 0.9 | Customer explicitly requested SECURITY category and CRITICAL priority. |
| other-08 | OTHER | PRODUCT | 0.8 | The customer is asking about a feature or opportunity within the product. |
