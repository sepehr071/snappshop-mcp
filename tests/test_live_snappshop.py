import pytest

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_live_search_product_reviews(client):
    r = (
        await client.call_tool("ss_search", {"query": "هدفون", "sort": "cheapest", "max_price": 2000000})
    ).structured_content
    assert r["total"] > 50 and all(i["price"] <= 2000000 for i in r["items"])
    p = (await client.call_tool("ss_product", {"product": str(r["items"][0]["product_id"])})).structured_content
    assert p["title"] and p["offers"] and p["price_from"] > 0
    rv = (await client.call_tool("ss_reviews", {"id": p["id"]})).structured_content
    assert "reviews" in rv


async def test_live_categories_and_category(client):
    top = (await client.call_tool("ss_categories", {})).structured_content["categories"]
    assert "mobile" in {c["path"] for c in top}
    kids = (await client.call_tool("ss_categories", {"parent": "mobile"})).structured_content["categories"]
    r = (await client.call_tool("ss_category", {"path": kids[0]["path"], "sort": "cheapest"})).structured_content
    assert r["items"]


async def test_live_suggest(client):
    r = (await client.call_tool("ss_suggest", {"query": "هد"})).structured_content
    assert any(t["term"] == "هدفون" for t in r["terms"])
