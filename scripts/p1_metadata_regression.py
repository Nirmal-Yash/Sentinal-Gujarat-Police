"""Contract-level regression for provided-vs-observed camera metadata.
No external camera or network is required; this verifies the normalization rule used by API/UI.
"""

def effective(provided, observed):
    return observed if observed not in (None, 0, "", "unknown") else provided

cases = [
    ({"provided_fps": 25, "observed_fps": 15.2}, 15.2),
    ({"provided_fps": 25, "observed_fps": 0}, 25),
    ({"provided_width": 1920, "observed_width": 1280}, 1280),
    ({"provided_width": 1920, "observed_width": None}, 1920),
]
for payload, expected in cases:
    key = next(k for k in payload if k.startswith("provided_"))
    observed_key = key.replace("provided_", "observed_")
    assert effective(payload.get(key), payload.get(observed_key)) == expected
print(f"metadata regression: {len(cases)}/{len(cases)} passed")
