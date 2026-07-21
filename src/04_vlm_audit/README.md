# Visual audit

The production model is `gemini-2.5-flash`, called through the Gemini API. Each private street-view image is sent directly for a schema-constrained audit. The output separates observed score, auditability, confidence, visible evidence and the reason for any NA.

The runner resumes from JSONL, validates every successful response and records only error types on failure. Images, credentials and provider request URLs are not written to repository outputs.
