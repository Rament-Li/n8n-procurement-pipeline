# Extraction evals

A small test harness for the email extraction step of the procurement pipeline. It runs 30 synthetic emails through the same prompt layout the n8n workflow uses, compares the model output with the answer written down for each email, and reports how many it got right.

## Why this exists

The workflow shows how the extraction is wired up. These evals show whether the extraction works, and let a prompt change be judged on evidence. Two prompts are included. `v1_baseline.txt` is the prompt used in the workflow. `v2_explicit_rules.txt` is a rewrite with step-by-step decision rules aimed at the failure modes the test cases probe.

## What is in the test set

`cases.json` holds 30 synthetic emails from seven fictional suppliers, each with the expected result. Nothing in it comes from a real organisation, and every address uses `example.com`.

| Group | What it tests |
|---|---|
| Orders (C01 to C08, C24 to C28, C30) | single and multiple items, euro and dollar prices, no date stated, references with slashes, shipping, handling, discount and VAT lines that must not become items, recommended products in a footer, repeat emails |
| Dispatch and delivery (C09 to C13, C23, C29) | tracking numbers that must not become order references, missing order reference, part shipments |
| Invoices (C14 to C16) | invoice numbers versus order references |
| Cancellations, refunds, returns (C17 to C19) | status detection |
| Not procurement (C20 to C22) | newsletters, abandoned baskets and account notices must return no items |

Some answers are ambiguous, so a case can accept a list of valid values, for example `["other", "order"]` for a cancellation. A field with no expected value is not scored.

## How a case is scored

Each case is checked field by field: `docType`, `supplier`, `order_ref`, `status`, `order_date`, `currency` and `items`. A case counts as fully correct only when every scored field is right. Items must match in number, by SKU (or by product name when the model returns no SKU) and by quantity. The scoring code is in `scoring.py` and is covered by unit tests.

## Run it

The API key is only ever read from the `ANTHROPIC_API_KEY` environment variable. The scripts do not accept it as an argument, do not read it from a file, and never print or save it.

1. Once, turn on the push check: `git config core.hooksPath .githooks`
2. Create a separate API key in the Anthropic Console with a low spend limit, and revoke it when you have finished.
3. In a terminal, enter the key without displaying it or saving it in shell history: `read -rs ANTHROPIC_API_KEY` (paste the key, press Enter), then `export ANTHROPIC_API_KEY`
4. Preview a request with no network call: `python3 evals/run_evals.py --prompt evals/prompts/v1_baseline.txt --dry-run`
5. Run each prompt: `python3 evals/run_evals.py --prompt evals/prompts/v1_baseline.txt` and the same for `v2_explicit_rules.txt`. Add `--repeat 3` because model output varies between runs.
6. Build the table: `python3 evals/make_report.py`
7. Before committing, check for credentials: `python3 evals/check_no_secrets.py`
8. Clear the key: `unset ANTHROPIC_API_KEY`

A full run of both prompts is 60 short API calls.

## Keeping credentials out of the repository

- The key lives only in the terminal session's environment.
- `check_no_secrets.py` scans every file Git would commit for key-shaped text and exits with an error if it finds any. It never prints the matched text.
- The `.githooks/pre-push` hook runs that scan and blocks the push on a match.
- The GitHub Actions workflow runs only the unit tests and the scan. It makes no API calls and uses no repository secrets.
- `.gitignore` excludes `.env` files and common key file types.

## Results

See [RESULTS.md](RESULTS.md). It is generated from the files in `results/`.

### What I found

I ran both prompts against the 30 synthetic emails, three runs each. The original prompt scored 84/90 and the rewritten prompt scored 90/90. Both failures in the original were consistent across repeats, not random. It extracted items from an abandoned-basket email that was never an order, and it listed an unshipped item in a partial-shipment email. Adding explicit rules for those two situations fixed both.

Caveat: I wrote the second prompt after seeing the test cases, so this shows it handles these cases, not that it generalises. The suite no longer separates the two prompts, so the next step is adding harder cases such as forwarded threads, multi-currency invoices and ambiguous dates.

## Limitations

The emails are synthetic and written by hand, so they are cleaner than real inbox traffic. Thirty cases is enough to show differences between prompts, not to estimate real-world accuracy. Model output varies between runs, so repeat runs are more reliable than a single run. The expected answers reflect one reasonable reading of each email.
