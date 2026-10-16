# Project 1: Python ETL Tool

> **Stage 1: Foundations & Python | Project 1 (P1) | Build session (3 hours)**
>
> Build a small but realistic data pipeline that reads several CSV files, cleans them,
> merges them, applies business rules, saves the results in three formats, and logs every step.

![Pipeline overview](images/01_pipeline_overview.png)

---

## 1. What is this project?

A company's sales data rarely lives in one tidy file. It arrives as **several related files**, with
gaps, duplicates and text where numbers should be. Your job is to turn that into **one trustworthy,
analysis-ready dataset**, and to do it in a way that is **repeatable** and **auditable**.

That job has a name: **ETL** (Extract, Transform, Load). In this project you build an ETL tool
using only what you have learned so far: core Python, `pathlib`, `logging`, and `pandas`.

**By the end you will have a tool that, with one function call:**

| # | It does this | Using |
|---|---|---|
| 1 | Reads **every CSV** in a folder | `pathlib` `glob`, `pd.read_csv` |
| 2 | **Cleans** missing values, duplicates, data types | `isnull`, `fillna`, `drop_duplicates`, `to_datetime` |
| 3 | **Merges** the files into one DataFrame | `pd.merge` |
| 4 | Applies **business logic** (calculations and classifications) | `apply`, `map`, `groupby` |
| 5 | **Saves** results as **CSV + Excel + JSON** | `to_csv`, `ExcelWriter`, `json` |
| 6 | **Logs** every step to a file and the console | `logging`, a custom context manager |

---

## 2. The data

We use the real, public **Northwind** sample: orders placed with a fictional food-trading company.
Five related tables, connected by ID columns (keys):

![Data model](images/02_data_model.png)

| File | Rows | What it holds |
|---|---|---|
| `orders.csv` | 830 | One row per order: customer, dates, freight |
| `order_details.csv` | 2,155 | One row per **order line**: product, price, quantity, discount |
| `customers.csv` | 91 | Who placed the orders |
| `products.csv` | 77 | What was sold, stock levels |
| `categories.csv` | 8 | Product categories |

**Read the diagram like this:** one customer has many orders, one order has many order lines,
one product appears on many order lines. We start from the **centre table** (`order_details`) and
attach everything else to it.

---

## 3. Project layout

```
etl_project/
├── raw/                      <- INPUT: the 5 CSV files land here
│   ├── orders.csv
│   ├── order_details.csv
│   ├── customers.csv
│   ├── products.csv
│   └── categories.csv
├── output/                   <- OUTPUT: what the tool produces
│   ├── order_lines_clean.csv     (full clean table)
│   ├── etl_report.xlsx           (full table + 5 summary sheets)
│   └── etl_summary.json          (headline numbers + summaries)
└── logs/
    └── etl_run.log           <- the audit trail of every run
```

**Files in this package**

| File | Purpose |
|---|---|
| `project1_python_etl_tool.ipynb` | The guided build notebook (used in the session) |
| `etl_tool.py` | The finished reference tool (compare your work against it) |
| `README.md` | This file |

---

## 4. Instructor briefing: explaining the project before implementation

**Time: about 15 to 20 minutes, before anyone opens the notebook.**
Each block below is one suggested slide: what to **show**, what to **say**, and what to **ask**.
Map them onto your own slide deck; the diagrams in `images/` can be dropped straight into slides.

### Slide 1: The goal (2 min)
- **Show:** the pipeline diagram at the top of this README.
- **Say:** "Today you build a tool, not a script. You run it once and a messy folder of files becomes
  one clean dataset, three output files, and a written record of what happened."
- **Ask:** "Where have you seen data arrive in several files that had to be combined?"

### Slide 2: Why ETL matters (2 min)
- **Say:** "Imagine this runs unattended at 3 a.m. and something breaks. The only thing you will have
  in the morning is the log. That is why logging is part of the design from the first line, not an afterthought."
- **Key idea:** a pipeline must be **repeatable** (same input, same output) and **auditable** (you can see what it did).

### Slide 3: The five steps (3 min)
- **Show:** the pipeline diagram; point at each box and the logging bar underneath.
- **Say:** "Extract reads. Clean fixes. Merge combines. Business logic adds meaning. Load saves. Logging watches all five."
- **Connect to prior learning:** this is the ETL mental model from Module 1, now built for real.

### Slide 4: The data model (3 min)
- **Show:** the data model diagram.
- **Say:** "Each table is only part of the story. `order_details` knows the price and quantity but not the customer's name.
  To answer 'which customers buy which categories?' we must join four tables."
- **Ask:** "If I want the customer name for each order line, which tables do I need to connect, and through which keys?"
- **Teaching point:** primary key vs foreign key in one sentence each.

### Slide 5: Cleaning is judgement, not a reflex (3 min)
- **Show:** the cleaning decisions diagram.

![Cleaning decisions](images/04_cleaning_decisions.png)

- **Say:** "Missing data is not one problem. `shipped_date` is empty for 21 orders because they have not shipped yet.
  If we fill it with a made-up date, we destroy that information and our 'Late delivery' rule gives wrong answers."
- **Ask:** "What would go wrong if we simply dropped every row with any missing value?"
  (Answer: we would lose the 21 unshipped orders and most customers, since `region` is empty for 60 of 91.)

| Finding | Decision |
|---|---|
| `shipped_date` missing | **Keep missing** (it means "not shipped yet") |
| `region`, `fax`, `postal_code` missing | **Fill** with `"N/A"` |
| Dates stored as text | **Convert** to real dates |
| `camelCase` column names | **Rename** to `snake_case` |
| Duplicate rows | **Drop** (none in this data, but the tool must cope; we prove it in the stress test) |

### Slide 6: The silent bug we guard against (3 min)
- **Show:** the merge safety diagram.

![Merge safety](images/03_merge_safety.png)

- **Say:** "If a lookup table accidentally has duplicate keys, a merge quietly **multiplies rows**. Revenue is inflated,
  nothing crashes, and nobody notices for months. We add two defences: `validate="many_to_one"` and a row-count check."
- **Key idea:** a good pipeline **fails loudly** rather than producing wrong numbers quietly.

### Slide 7: The business rules (2 min)
- **Say:** "Clean data is not yet useful. Business logic turns it into decisions."

| New column | Rule |
|---|---|
| `line_total` | `unit_price x quantity x (1 - discount)` |
| `days_to_ship` | `shipped_date - order_date` |
| `delivery_status` | not shipped, **Not Shipped**; shipped after the required date, **Late**; otherwise **On Time** |
| `stock_status` | discontinued, **Discontinued**; stock at or below reorder level, **Reorder**; otherwise **OK** |
| `customer_tier` | total revenue at or above 30,000 **Gold**; at or above 10,000 **Silver**; otherwise **Bronze** |

- **Point out:** the thresholds live in one `CONFIG` dictionary, so changing a business rule means changing one line.

### Slide 8: One result, three formats (1 min)

| Format | Audience | Contents |
|---|---|---|
| **CSV** | Other tools and pipelines | Full clean order-line table |
| **Excel** | Business users | One workbook: full table plus one sheet per summary |
| **JSON** | Applications and APIs | Headline numbers plus all summaries |

### Slide 9: How the session runs and how success is judged (2 min)
- **Say:** "For each step I will build it with you, then you get a short 'Your turn' task. At the end you compare your work
  with the finished `etl_tool.py`."
- **Success criteria (tell learners up front):**
  - [ ] Reads all CSVs in a folder without hard-coding file names
  - [ ] Cleans missing values, duplicates and types, with a reason for each decision
  - [ ] Merges into one DataFrame with the **same number of rows** as `order_details`
  - [ ] Adds at least the calculations and classifications above
  - [ ] Saves CSV, Excel and JSON
  - [ ] Writes a log line for every step

### Quick comprehension check before starting (optional, 2 min)
1. Why does the tool start the merge from `order_details`?
2. Why did we **not** fill `shipped_date`?
3. What does `validate="many_to_one"` protect against?
4. Why is logging set up before anything else?

---

## 5. Quick start

**Requirements:** Python 3.9+, internet access the first time (the sample files are downloaded from GitHub).

```bash
pip install pandas openpyxl
```

**Option A: follow the guided notebook**
```bash
jupyter notebook project1_python_etl_tool.ipynb
```

**Option B: run the finished tool**
```bash
python etl_tool.py
```

Both create an `etl_project/` folder next to where you run them.

### What a successful run looks like
```
[INFO] === ETL run started ===
[INFO] START  1. extract (read all CSVs)
[INFO] read orders.csv: 830 rows x 14 columns
...
[INFO] merge: 2155 order lines x 20 columns, unmatched keys=0
[INFO] business logic: total revenue=1,265,793.02; delivery={'On Time': 1990, 'Late': 92, 'Not Shipped': 73} ...
[INFO] saved CSV   -> etl_project/output/order_lines_clean.csv
[INFO] saved Excel -> etl_project/output/etl_report.xlsx
[INFO] saved JSON  -> etl_project/output/etl_summary.json
[INFO] === ETL run finished OK ===
```

Use these numbers as a **self-check**: if your row counts or total revenue differ, something earlier in the pipeline is off.

---

## 6. Common mistakes (good to warn learners)

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError: 'orderDate'` | Columns were renamed to `snake_case` first, but the code still uses `camelCase` | Use `order_date` after cleaning |
| Row count grows after a merge | A lookup table has duplicate keys | Use `validate="many_to_one"` and check the row count |
| `shipped_date` all filled in | Filled every missing value blindly | Fill only columns where a default makes sense |
| Excel save fails | `openpyxl` not installed | `pip install openpyxl` |
| Duplicate lines in the log | Logger created twice in a notebook | `logger.handlers.clear()` (already in `setup_logger`) |
| Download fails | No internet | Place the five CSVs in `etl_project/raw/` manually |

---

## 7. Extension challenges

1. Flag orders whose `freight` is above the 90th percentile as `"High Freight"`.
2. Also save the main table as **Parquet** and compare file sizes with the CSV.
3. Write **one CSV per year** into `output/by_year/`.
4. Make `profile_table()` return a dictionary and save a `quality_report.json`.
5. Raise an error if any `line_total` is negative, and show the failure in the log.
6. Add your own CSV to `raw/` and see what the tool does with it.

---

## 8. Skills this project connects

| Earlier topic | Where it appears here |
|---|---|
| Functions, error handling | Every step is a function; `try / except / finally` wraps the run |
| File I/O, `pathlib` | Finding and reading all CSVs; creating folders |
| Context managers | `log_step()` records start, finish and timing |
| `logging` | Audit trail of every step |
| JSON and CSV | Output formats |
| pandas Part 1 | Reading, missing data, types |
| pandas Part 2 | Merge, groupby, apply and map, writing Excel |
