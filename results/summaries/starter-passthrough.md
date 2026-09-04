# Starter-passthrough verifier run

Date: 2026-09-04

Simulates an agent that ships the bundled futures-only scanner and writes the sample report (the report the starter already gets right).

```
docker build -t scan-margin-agent tasks/scan-margin/environment
docker build -t scan-margin-verifier tasks/scan-margin/tests
# run starter CLI on the sample book, copy /app/hsm and the report into the verifier
bash /tests/test.sh
```

Reward: **0**

Pytest: 8 failed, 5 passed.

| Test | Starter | Oracle | Discriminates? |
|------|---------|--------|----------------|
| sample | 5000.00 | 5000.00 | no (by design) |
| fx_equity | 19530.00 | 19530.00 | no (pure FX futures) |
| netting | 5000.00 | 5000.00 | no (netting is in the starter) |
| visible artifact | pass | pass | no |
| sample vs som_otm totals differ | pass | pass | weak |
| som_otm | 0.00 | 50898.39 | yes (SOM / option scan) |
| calendar | 0.00 | 449.69 | yes (intra-month charge) |
| crack | 40160.00 | 33760.00 | yes (missing $6400 ICS credit) |
| nov_long | worst id 1 | 14 | yes (option scenarios) |
| mixed_opt | 7500.00 | 20490.35 | yes |
| ics_priority | 57760.00 | 50560.00 | yes (missing $7200 credits) |
| multi_cc | 80000.00 | 103284.66 | yes |
| vol_mix | 5000.00 | 23994.84 | yes |

Binary reward remains 0. A cheat that only reproduces the sample file cannot pass.
