from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "recipe": "CVD Conformal",
            "thickness": {"value": thickness, "unit": "nm"},
        }
    ]


def test_reusing_a_structure_as_template_starts_a_fresh_lineage(client):
    client.post("/api/auth/register", json={"email": "tmpl@example.com", "password": "supersecret", "name": "T"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]

    source = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(20), "title": "Reference", "intent": "Depart"},
    ).json()

    # the structure builder fetches this to pre-fill, then POSTs a brand-new /experiences (not /evoluer)
    process = client.get(f"/api/projects/{slug}/experiences/{source['id']}/process").json()
    fresh = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": process["substrate"],
            "steps": process["steps"],
            "title": "Nouvelle piste independante",
            "intent": "Reprend la meme structure sans heriter de la lignee",
        },
    ).json()

    detail = client.get(f"/api/projects/{slug}/experiences/{fresh['id']}").json()
    assert detail["parents"] == []
    assert detail["branch"] != source["branch"]
    # same structure content though (same process re-used)
    assert "<svg" in detail["structure_svg"]
