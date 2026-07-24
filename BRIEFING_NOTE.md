# One-Page Briefing Note: Engage-Me Data Anonymiser

## Objective
Provide Beyond Housing with a local, self-hosted tool to anonymise free-text comments before analysis or sharing.

## Proposed Approach
Engage-Me supplies a Dockerised anonymisation application built on Microsoft Presidio and configured for UK social housing comment patterns.

## Why This Approach
- Data stays local: all processing is performed on Beyond Housing infrastructure.
- Lower governance risk: no transfer of raw identifiable comments to Engage-Me.
- Practical accuracy: combines proven PII recognisers with housing-specific rules.
- Auditability: downloadable detection report and residual flags for manual review.

## Solution Components
- Presidio Analyzer + Anonymizer
- Custom recognisers for housing references and key-safe/access codes
- spaCy `en_core_web_md` language model for balanced accuracy and size
- Streamlit UI for non-technical operation

## User Workflow (Dylan)
1. Start the container with `docker compose up --build`.
2. Open local web app in browser.
3. Upload CSV or Excel file.
4. Run anonymisation.
5. Download output workbook with reports.

## Deliverables
- `Anonymised Data` sheet
- `Detection Report` sheet (what was detected and where)
- `Residual Flags` sheet (possible leftovers requiring review)

## Controls and Residual Risk
- Perfect 100 percent anonymisation is not realistic for free text.
- Residual risk is managed through:
  - QA tuning loop on representative samples
  - Threshold and pattern calibration
  - Manual review of residual flags

## Recommended Rollout
1. Internal validation by Engage-Me with test comments.
2. Joint QA loop with Beyond Housing on 400 to 600 real comments.
3. Pattern and threshold tuning.
4. Freeze image and hand over runbook.
5. Document periodic spot-check process.

## Operational Notes
- Typical container image size: approximately 2.0 to 2.6 GB.
- Solution is designed for straightforward internal deployment and repeatable operation.
