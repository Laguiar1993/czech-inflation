# CZSO producer-price release dates checked on 18 September 2026 (reviewer, WebFetch)

The repository's `pipeline_available_from.csv` reconstructs the producer (PPI) and farm (agri4) stamps by a
fixed day-of-month rule (`tools/r14_food/prepare_inputs.py`): PPI on day 16 of the following month
(+9 in January, +4 March/April, +1 June/December) at midnight Prague; farm prices on day 26 at midnight.
Observed CZSO "Producer price indices" releases (industrial and agricultural producer prices in one release):

| Reference month | CZSO publication date (from the release page) | Reconstructed PPI stamp | Reconstructed agri stamp |
|---|---|---|---|
| June 2025 | 16 July 2025 | 17 Jul 2025 00:00 (1 day later than actual) | 26 Jul 2025 |
| July 2025 | 18 August 2025 | 16 Aug 2025 00:00 (2 days earlier than actual) | 26 Aug 2025 |
| December 2025 | 19 January 2026 | 17 Jan 2026 00:00 (2 days earlier than actual) | 26 Jan 2026 |
| January 2025 | 25 February 2025 | 25 Feb 2025 00:00 (same day, 9 hours early) | 26 Feb 2025 |
| January 2026 | 25 February 2026 | 25 Feb 2026 00:00 (same day) | 26 Feb 2026 |

The July 2025 and December 2025 pages state: "Except for the construction work price indices, the published
figures are final data." So the industrial and agricultural producer price indices are final on first release
(no vintage revisions to worry about for the index series). The farm-price panel used here is the physical
average producer prices of four products (`data/cz_agri_prices_raw.csv`), which the reviewer assumes are
published with the same release; the reconstruction puts them 7-10 days later than that release, i.e. it is
conservative for agri4 in every month checked. The PPI reconstruction is within +/-2 days of the observed
dates; the minimum slack between the reconstructed stamp of month t-1 and the origin clock is 7.0 days for PPI
and 6.0 days for agri4 (both at the 2025-26 origins whose clock is the eve of the flash release), so a 2-day
error in the reconstruction cannot move the last common month at any origin.

Sources:
- https://csu.gov.cz/rychle-informace/producer-price-indices-june-2025
- https://csu.gov.cz/rychle-informace/producer-price-indices-july-2025
- https://csu.gov.cz/rychle-informace/producer-price-indices-december-2025
- https://csu.gov.cz/rychle-informace/producer-price-indices-january-2025
- https://csu.gov.cz/rychle-informace/producer-price-indices-january-2026
