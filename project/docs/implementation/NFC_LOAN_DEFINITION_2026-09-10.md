# NFC loan balance definition — 10 September 2026

## What the paper asks for

CNB Working Paper 9/2026, A6 variable 58, asks for the monthly **client-loan
balance of Czech-resident non-financial corporations**, transformed as a log
difference. This is a stock at the end of the month, not new lending during the
month.

## What the local ARAD data contain

The selected `SUCM...` rows come from CNB's VST (CNB) 1–12 monthly statement of
client loans and receivables. CNB's methodology says that balances are nominal,
monthly closing balances reported by commercial banks and foreign bank branches
in Czechia, and that the reporting population excludes the CNB. The debtor
sector is ESA S.11 (non-financial corporations), and the statement is split by
original maturity.

The four identifiers in the frozen extract are:

| Identifier | Role |
|---|---|
| `SUCM100311XXX101101` | NFC total |
| `SUCM200311XXX101101` | NFC loans, up to one year |
| `SUCM300311XXX101101` | NFC loans, over one and up to five years |
| `SUCM400311XXX101101` | NFC loans, over five years |

The total agrees with the sum of the three maturity rows up to rounding. The
total must therefore be used once. Adding all four rows is a double count. The
adapter now uses the total and falls back to the three buckets only when a
snapshot does not contain the total.

## Is it an MFI series, and does it exclude the Eurosystem?

It is an **other-MFI/commercial-bank client-loan series**, rather than a full
consolidated MFI aggregate. It excludes the CNB central bank, which is the
relevant exclusion in Czechia. Czechia is not in the euro area, so the
Eurosystem is not a Czech lender in this series. A harmonised monetary-statistics
table may use a broader MFI perimeter and may explicitly include the CNB; that
would be a different comparison series, not a reason to add the CNB or another
sector to these VST rows.

For the paper replication, this is a strong match to the wording “client-loan
balance” because it is the CNB's own sectoral bank-client-loan stock. We retain a
coverage caveat until the paper's unpublished extraction code confirms whether
it used this VST perimeter or a harmonised MFI table. The two should be compared
side by side, never silently substituted.

## Timing and transformation

The observation date is the month-end balance. The model must attach the actual
CNB publication date (or a conservative release rule) as `available_from`; the
current historical database snapshot does not constitute an original-vintage
archive. For A6 #58 the raw positive level is transformed as

```text
log(loan_stock_t) − log(loan_stock_{t−1})
```

The operating big model's `nfc_loans_mm` percentage change is a close numerical
approximation for this positive stock, but the paper lane keeps the raw level and
applies its declared transform.

## Bloomberg comparison captured 11 September 2026

`data/market_snapshots/20260911_bloomberg_full_clean/` contains `LONSCZNF
Index`, an ECB-sourced monthly series in EUR millions from January 2002 through
July 2026. Converting each month by the Bloomberg EUR/CZK quote and multiplying
by one million gives a level with correlation 0.99975 against the ARAD total on
the common window. The log-growth correlation is 0.959 and the mean absolute
growth difference is 0.246 percentage points across 257 observations.

The match makes it a strong validation and late-data backup, but its Bloomberg
description says only that it tracks an aggregate of bank assets and liabilities
and does not state the exact central-bank/MFI perimeter or a seasonal-adjustment
flag. Keep ARAD as the primary paper input. If the Bloomberg candidate is used
in a challenger, convert the EUR stock to CZK before taking the log difference,
and report the perimeter and currency conversion explicitly.

Source: [CNB ARAD client-loan methodological sheet](https://www.cnb.cz/docs/ARADY/MET_LIST/tuvob_en.pdf).
