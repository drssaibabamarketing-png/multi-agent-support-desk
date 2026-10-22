# Source list
Public sources only. Every citation link in a reply comes from this list (`corpus.ALLOWED_URLS`).

## Milestone 1: HDFC Mutual Fund, AMFI, SEBI
| # | URL | Used for |
|---|---|---|
| 1 | https://www.hdfcfund.com/explore/mutual-funds/hdfc-mid-cap-opportunities-fund/direct | Mid-Cap scheme facts |
| 2 | https://www.hdfcfund.com/explore/mutual-funds/hdfc-small-cap-fund/direct | Small Cap scheme facts |
| 3 | https://www.hdfcfund.com/explore/mutual-funds/hdfc-gold-etf-fund-fund/direct | Gold ETF FoF scheme facts |
| 4 | https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct | Large Cap (formerly Top 100) scheme facts |
| 5 | https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver-fund/direct | ELSS scheme facts |
| 6 | https://www.hdfcfund.com/statutory-disclosure/nav-and-idcw | NAV page (listed, not served as an answer: volatile) |
| 7 | https://www.hdfcfund.com/investor-services/download-statements/account-statement | Account statement steps |
| 8 | https://www.hdfcfund.com/investor-services/download-statements/capital-gains-statement | Capital gains statement steps |
| 9 | https://www.hdfcfund.com/investor-services/kyc | KYC |
| 10 | https://www.hdfcfund.com/about-us/corporate-governance | Governance |
| 11 | https://www.hdfcfund.com/investor-services/downloads/forms | Forms |
| 12 | https://www.amfiindia.com/ | ELSS, SIP basics |
| 13 | https://investor.sebi.gov.in/ | Regulator context |
| 14 | https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doFaq=yes | Exit load definition |
| 15 | https://www.sebi.gov.in/legal/master-circulars/may-2023/master-circular-for-mutual-funds_71438.html | Riskometer rule |

## Milestone 2: Groww fees and reviews
| # | Source | URL | Used for |
|---|---|---|---|
| 16 | Groww pricing and charges | https://groww.in/pricing | Brokerage, DP, square-off facts |
| 17 | Groww Help Centre | https://groww.in/help | Charges FAQs |
| 18 | AMFI investor corner | https://www.amfiindia.com/investor-corner | Exit load / expense ratio explainer |
| 19 | Groww Play Store reviews | https://play.google.com/store/apps/details?id=com.nextbillion.groww | `data/reviews.csv` (Pattern agent and test complaints) |

## Notes
- `corpus_registry.py` uses a few URLs that differ from items 3, 4, 6, 7, 8, 9, 10, 11. `corpus.URL_FIX` maps them to the published list above so citations only point to listed pages.
- Scheme facts in `corpus_registry.py` must be verified against items 1-5 before submission (see README, Limitations).
