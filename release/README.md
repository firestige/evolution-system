# Evolution release path

Pushing `release/next` automatically starts candidate qualification. The pushed commit must contain `release/request.json` with `candidate_tag`, the exact 40-character superproject `authority_ref`, and the exact Evolution `product_commit` pinned by that authority. The candidate workflow has no manual or reusable entry point.

Stable promotion remains manual-only. It reuses the candidate's qualified OCI digest, validates its provenance and image identity, retags that digest, and creates the final GitHub Release without rebuilding.
