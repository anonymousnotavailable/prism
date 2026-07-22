# Kaggle Dataset Research — Real-World Anomaly Patterns

Research pass over the 34 datasets in `30+ Kaggle Datasets for Beginner EDA`
(Aishwarya Mate), done to find data-quality patterns Prism's cleaning
detectors didn't yet cover. Each entry lists concrete, column-level known
issues (not generic "may have nulls" hand-waving) and a 1-10 messiness
score. `modules/dataset_knowledge.py` turns the highest-confidence entries
into a fingerprint library Prism uses to recognize a dataset on upload and
hand out tailored advice.

**What this research produced**, in `modules/hellmode.py` +
`modules/autocleaner.py` + `modules/data_engine.py`:
- **Meaningful-NA detector** — a categorical column with concentrated high
  missingness (≥40%) more likely means "doesn't apply" than "unknown"
  (House Prices' `PoolQC`/`Fence`/`Alley` being the canonical case). Fills
  with an explicit "Not Applicable" category instead of the mode.
- **Zero-sentinel detector** — numeric columns with physically-implausible
  names (glucose, bmi, budget, revenue, ...) where 0 shows up as a minority
  cluster clearly separated from the real distribution get flagged as a
  disguised null, not a genuine reading.
- **Multi-value delimited-cell detector** — comma/pipe/semicolon-packed
  cells (Netflix's `cast`, Amazon's `category`, YouTube's `tags`) get a
  `_count` + `_primary` column pair surfaced instead of being treated as
  one opaque category.
- **Encoding-robust CSV loading** — retries CP1252 then Latin-1 on a
  UTF-8 decode failure instead of hard-failing (YouTube Trending's
  international titles/tags, Online Retail's Windows-1252 export).

---

## 1. Bank Marketing (janiobachmann)
Portuguese bank telemarketing calls; ~11,162 rows × 17 cols. `pdays` uses
`-1` as a "never contacted" sentinel; `job`/`education`/`contact`/
`poutcome` use the literal string `"unknown"` as a real category;
yes/no fields need boolean coercion; heavy right-skew in `balance`.
**Messiness: 5/10.**

## 2. Credit Card Customers / BankChurners (sakshigoyal7)
Bank credit-card churn; ~10,127 rows × 23 cols. Two trailing leaked-model
columns literally named `Naive_Bayes_Classifier_...` must be dropped;
`Income_Category`/`Education_Level`/`Marital_Status` use `"Unknown"` as a
real category; ~16/84 class imbalance in the churn target.
**Messiness: 6/10.**

## 3. Loan Prediction (ninzaami)
614 rows × 13 cols. `Dependents` stores `"3+"` as a string sentinel
(breaks numeric coercion); missing values scattered across categorical and
numeric columns; `Credit_History` is a gappy 1.0/0.0 float flag; extreme
income outliers (10-40x median).
**Messiness: 7/10.**

## 4. House Prices — Ames (competition data)
1,460 train rows × 79 features. **The flagship pattern**: ~14 columns
(`PoolQC`, `MiscFeature`, `Alley`, `Fence`, `FireplaceQu`,
`GarageType/Finish/Qual/Cond`, `BsmtQual/Cond/Exposure/FinType1/2`) use
`NA` to mean "feature doesn't exist," not missing. `GarageYrBlt` has a
documented typo outlier (2207 for 2007). `MSSubClass` is a numeric dwelling
code that's actually categorical.
**Messiness: 9/10 — chosen as Prism's bundled `house_prices_ames_messy.csv` sample.**

## 5. Medical Appointment No-Shows (joniarroba)
110,527 rows × 14 cols. `PatientId` is float64 in scientific notation;
`Age` has an invalid `-1` sentinel plus a 115 outlier; column typos
(`Hipertension`, `Handcap`); some `ScheduledDay` > `AppointmentDay`
(impossible negative wait time); target label is inverted (`"Yes"` = missed).
**Messiness: 7/10.**

## 6. Brazilian E-commerce / Olist (olistbr)
~100k orders across 9 relational CSVs, not one flat table.
`product_category_name` is Portuguese, needs a translation-table join;
geolocation has out-of-bounds lat/lng; delivery timestamps occasionally
precede shipment timestamps.
**Messiness: 8/10.**

## 7. Superstore (vivek468)
9,994 rows × 21 cols. `Postal Code` null for 11 Burlington VT rows;
`Country` constant (zero information); some `Ship Date` < `Order Date`
after coercion; large negative-loss `Profit` outliers.
**Messiness: 3/10.**

## 8. Insurance / Medical Cost Personal (mirichoi0218)
1,338 rows × 7 cols. One well-known exact duplicate row; `charges` heavily
right-skewed (log-transform territory, not IQR clipping); a few
physiologically-implausible `bmi` outliers (>50).
**Messiness: 3/10.**

## 9. Telco Customer Churn (blastchar)
7,043 rows × 21 cols. `TotalCharges` is a string column with 11
whitespace-only values (not NaN) for `tenure=0` customers;
`OnlineSecurity`/`TechSupport`/etc. use `"No internet service"` as a real
third category; inconsistent 0/1 vs. Yes/No encoding across parallel
binary fields.
**Messiness: 6/10.**

## 10. HR Analytics (giripujar)
14,999 rows × 10 cols. Column typo `average_montly_hours`; inconsistent
casing (`Work_accident`); `salary` is ordinal text; department column is
misleadingly named `sales`. Synthetic and largely clean otherwise.
**Messiness: 2/10.**

## 11. Hotel Booking Demand (jessemostipak)
119,390 rows × 32 cols. `agent`/`company` mix ~14%/~94% missing with a
literal `"NULL"` string category; `meal` has redundant `"Undefined"`/`"SC"`
categories both meaning no meal package; `adr` has an extreme outlier
(~5,400) plus occasional negative/zero values.
**Messiness: 8/10.**

## 12. Food Delivery Time Prediction (denkuznetz)
~1,000 rows × 9 cols. Scattered missingness across weather/traffic/prep
fields; unrealistic distance/prep-time outliers; small-sample category
imbalance.
**Messiness: 4/10.**

## 13. Titanic (competition)
891 rows × 12 cols. `Cabin` ~77% missing; `Age` ~20% missing; `Fare` has
legitimate $0 crew values; `Name` embeds a title requiring string parsing;
`Ticket` format is wildly inconsistent and shared across families (not a
unique key).
**Messiness: 7/10.**

## 14. Netflix Shows (shivamb)
8,807 rows × 12 cols. `director`/`cast`/`country` have large-scale
missingness; `duration` mixes "90 min" (movies) with "2 Seasons" (TV) in
one column; `cast`/`country`/`listed_in` are comma-separated multi-value
cells; a documented scraping bug shifts some duration values into `rating`.
**Messiness: 7/10.**

## 15. Spotify Tracks (maharshipandya)
~114,000 rows × 20 cols. Duplicate `track_id`s (one row per genre tag);
zero/near-zero `duration_ms` for broken entries; heavily zero-inflated
`popularity`; non-UTF8 artist/track names from international catalogs.
**Messiness: 5/10.**

## 16. NYC Airbnb Open Data (dgomonov)
~48,900 rows × 16 cols. `last_review`/`reviews_per_month` null for
never-reviewed listings (informative, not random); `price` has ~26 exact-0
sentinel rows alongside real outliers to $10,000; `minimum_nights` up to
1,250; redundant `neighbourhood_group`/`neighbourhood` hierarchy.
**Messiness: 6/10.**

## 17. Amazon Sales Dataset (karkavelrajaj)
~1,465 rows × 16 cols. `discounted_price`/`actual_price` are ₹-prefixed,
comma-separated strings; `discount_percentage` has a trailing `%`;
`category` is a single pipe-delimited taxonomy hierarchy; `rating_count`
has comma separators; at least one corrupted non-numeric `rating` value.
**Messiness: 7/10.**

## 18. BigMart Sales (brijbhushannanda1979)
~8,523 rows × 12 cols. `Item_Fat_Content` has abbreviation-style
duplicates ("Low Fat"/"LF"/"low fat") too dissimilar for fuzzy matching;
`Item_Visibility` uses 0.0 as a "not tracked" sentinel; `Outlet_Size`
missing ~28% as a blank string; `Item_Identifier` prefix hides a category.
**Messiness: 8/10.**

## 19. Mall Customers (shwetabh123)
200 rows × 5 cols. Deliberately clean synthetic teaching data; only
friction is a header with embedded units (`Annual Income (k$)`).
**Messiness: 2/10.**

## 20. Online Retail (vijayuv / UCI mirror)
~541,909 rows × 8 cols. `InvoiceNo` starting with "C" marks a cancellation
paired with negative `Quantity`; `CustomerID` missing ~25%; `StockCode`
mixes real SKUs with non-product codes ("POST", "D", "M", "BANK CHARGES");
original file is Windows-1252 encoded, not UTF-8.
**Messiness: 8/10.**

## 21. Students Performance in Exams (spscientist)
1,000 rows × 8 cols. Fabricated/clean teaching dataset; only friction is
headers with spaces/slashes (`race/ethnicity`).
**Messiness: 2/10.**

## 22. Campus Placement (benroshan)
215 rows × 15 cols. `salary` is null for every "Not Placed" student —
structurally conditional on another column, not random.
**Messiness: 3/10.**

## 23. Diabetes Dataset / Pima Indians (mathchi)
768 rows × 9 cols. `Glucose`/`BloodPressure`/`SkinThickness`/`Insulin`/
`BMI` use biologically-impossible 0 as a disguised null (Insulin ~48%
zero-rate) — the canonical zero-sentinel example.
**Messiness: 6/10.**

## 24. Heart Disease Dataset (johnsmith88)
1,025 rows × 14 cols. Balloons from the original 303 unique UCI records to
1,025 via ~700+ duplicated rows — will silently inflate train/test-split
accuracy if not deduplicated first; `ca`/`thal` use out-of-range codes as
disguised missingness.
**Messiness: 7/10.**

## 25. Stroke Prediction (fedesoriano)
5,110 rows × 12 cols. `bmi` has 201 missing encoded as the literal string
`"N/A"`; `gender` has one rare `"Other"` row; `smoking_status` has an
`"Unknown"` category that's semantically missing; severe class imbalance
(~4.9% positive).
**Messiness: 6/10.**

## 26. Car Price Prediction (hellbuoy)
205 rows × 26 cols. `CarName` conflates make+model with misspellings
("maxda", "porcshce", "toyouta") needing substring extraction before fuzzy
normalization; `doornumber`/`cylindernumber` spell numbers as English
words ("four", "two").
**Messiness: 5/10.**

## 27. Craigslist Cars/Trucks (austinreese)
~426K rows × 26 cols. Pervasive patchy missingness across nearly every
column; spam-level price outliers ($0, $1, $99999999); odometer outliers;
same VIN reposted across many listing IDs. **1.4GB — too large to bundle.**
**Messiness: 9/10.**

## 28. Flight Delays (usdot)
flights.csv ~5.8M rows × 31 cols + 2 lookup tables. Delay columns null
specifically for cancelled/diverted flights (conditional on another
column); `CANCELLATION_REASON` uses undocumented single-letter codes;
requires joining IATA codes against separate lookup files.
**Messiness: 7/10.**

## 29. World Happiness Report (unsdsn)
Separate CSV per year, ~150-160 countries × 8-12 cols. Column names and
even which columns exist change year to year; inconsistent country naming
across years; "Dystopia Residual" is a constructed artifact easily
mistaken for a real measurement.
**Messiness: 6/10 — cross-year schema harmonization is out of scope for a single-flat-file tool.**

## 30. YouTube Trending Videos (datasnaek)
Per-country CSVs, ~40K rows × 16 cols each. **Confirmed non-UTF-8** —
must be read as Latin-1/CP1252/CP1252, not UTF-8; `category_id` needs a
join against a separate per-country JSON; `trending_date` uses "YY.DD.MM"
while `publish_time` is ISO8601; `tags` is pipe-delimited.
**Messiness: 9/10 — the dataset that justified the encoding-fallback fix.**

## 31. Coffee Quality Database / CQI (volpatto)
~1,338 rows × 44 cols. ~98/2 species class imbalance; altitude split
across low/high/mean columns plus a separate unit column (some entered in
feet landing in "meters" fields, producing >10,000m outliers); inconsistent
country naming; some sub-scores use 0 as a "not rated" sentinel.
**Messiness: 8/10.**

## 32. Wine Quality (yasserh)
1,143 rows × 13 cols. Severely imbalanced ordinal `quality` target
clustered at 5-6; this cut differs in row count from the canonical UCI
1,599-row file, a common source of confusion; legitimate but extreme
right-skew in several features.
**Messiness: 4/10.**

## 33. IMDb/TMDB Movies Dataset (ashpalsingh1525)
10,000+ rows. `budget`/`revenue` use 0 as a disguised-null sentinel;
`genres` is comma-separated multi-value; `status` mixes released and
unreleased films; `original_language` is an ISO code needing a lookup.
**Messiness: 7/10.**

## 34. Pokemon (abcsds)
800 rows × 13 cols. `Type 2` is legitimately null for single-typed
Pokemon (~50%) — a real category, not missing; ~48 Mega Evolution rows
have names concatenated with no separator; `#` is not a unique row key
(alt forms reuse their base number).
**Messiness: 5/10.**

---

## Patterns deliberately not built
- **Abbreviation/synonym category normalization** (BigMart's "LF" vs.
  "Low Fat") — needs a domain-specific synonym dictionary to be reliable;
  too fragile for a generic tool. Documented as a known limitation instead.
- **Multi-table / relational join handling** (Olist's 9-file schema) —
  out of scope for a single-flat-file EDA tool.
- **Cross-year/cross-file schema harmonization** (World Happiness) — same
  reasoning; a different kind of tool problem.
- **Full one-hot explosion of multi-value cells** — the count/primary
  split is deliberately conservative; unbounded one-hot expansion from an
  arbitrary delimited column is a judgment call left to the user, not
  something Auto Cleaner should decide unsupervised.
