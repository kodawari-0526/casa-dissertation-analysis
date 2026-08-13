# Visual audit

The dissertation used `gemini-3-flash-preview` through the Gemini API with temperature fixed at 0. Each private street-view image is sent directly for a schema-constrained audit. The output separates observed score, auditability, confidence, visible evidence and the reason for any NA.

The runner resumes from JSONL, validates every successful response and records only error types on failure. Images, credentials and provider request URLs are not written to repository outputs.
