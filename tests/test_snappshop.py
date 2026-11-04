import json

import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

TOOLS = {
    "ss_search",
    "ss_suggest",
    "ss_categories",
    "ss_category",
    "ss_product",
    "ss_reviews",
    "ss_similar",
    "ss_seller",
    "ss_filters",
    "ss_brand",
    "ss_collection",
    "ss_promotions",
    "ss_compare",
}


@pytest.fixture(autouse=True)
def guest_token(api):
    api["/guest/v2/token"] = {"status": True, "data": {"token": "guest-jwt"}}


async def test_all_tools_are_read_only_and_described(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True, t.name
        assert t.title and t.description.splitlines()[0].endswith("."), t.name
        assert "title" not in str(t.input_schema.get("properties", {}).values()), t.name


async def test_search_sends_site_body_and_returns_cards(client, api):
    api["/search/v1"] = fixture("search.json")
    r = (
        await client.call_tool(
            "ss_search",
            {"query": "هدفون", "sort": "cheapest", "max_price": 2000000, "in_stock": True, "page": 3},
        )
    ).structured_content
    call = api.calls[-1]
    assert json.loads(call.content) == {
        "render": 4,
        "sort": "x0QZq8",
        "max_price": 2000000,
        "is_available": True,
        "query": "هدفون",
        "skip": 2,
    }
    assert call.headers["authorization"] == "Bearer guest-jwt"
    assert r["total"] == 6992 and r["page"] == 3 and "brands" not in r
    first = r["items"][0]
    assert first["product_id"] and first["url"].startswith("https://snappshop.ir/product/snp-") and first["price"]


async def test_search_first_page_lists_brand_ids(client, api):
    api["/search/v1"] = fixture("search.json")
    r = (await client.call_tool("ss_search", {"query": "هدفون"})).structured_content
    assert r["brands"] and len(r["brands"][0]["id"]) == 6
    assert "skip" not in json.loads(api.calls[-1].content)


async def test_guest_token_is_fetched_once_and_renewed_on_401(client, api):
    seen = []

    def search(request):
        seen.append(request.headers["authorization"])
        if len(seen) == 1:
            return httpx.Response(401, json={"message": "expired"})
        return httpx.Response(200, json=fixture("search.json"))

    tokens = iter(["old-jwt", "new-jwt"])
    api["/guest/v2/token"] = lambda request: httpx.Response(200, json={"data": {"token": next(tokens)}})
    api["/search/v1"] = search
    await client.call_tool("ss_search", {"query": "a"})
    assert seen == ["Bearer old-jwt", "Bearer new-jwt"]


async def test_product_offers_are_cheapest_first_with_seller_names(client, api):
    api["/products/v2/1222938263"] = fixture("product.json")
    r = (
        await client.call_tool("ss_product", {"product": "https://snappshop.ir/product/snp-1222938263"})
    ).structured_content
    prices = [o["price"] for o in r["offers"]]
    assert prices == sorted(prices) and r["price_from"] == prices[0] == 274200
    assert r["offers"][0]["seller"] == "داروخانه سیب سبز" and r["offers"][0]["list_price"] == 633000
    assert r["id"] == "0WdnlY" and r["category_id"] and r["specs"]


async def test_product_rejects_garbage_id(client):
    r = await client.call_tool("ss_product", {"product": "abc"})
    assert r.is_error and "product_id" in r.content[0].text


async def test_reviews_drop_reviewer_names(client, api):
    api["/reviews/v2/product/0WdnlY"] = fixture("reviews.json")
    r = (await client.call_tool("ss_reviews", {"id": "0WdnlY"})).structured_content
    assert r["reviews"][0]["score"] == 5 and r["reviews"][0]["text"]
    assert "first_name" not in json.dumps(r, ensure_ascii=False)


async def test_categories_top_level_and_children(client, api):
    api["/landing/v1/megamenu"] = fixture("megamenu.json")
    top = (await client.call_tool("ss_categories", {})).structured_content
    assert top["categories"][0] == {"title": "موبایل", "path": "mobile"}
    kids = (await client.call_tool("ss_categories", {"parent": "/category/mobile"})).structured_content
    assert kids["categories"] and all(c["path"].startswith("mobile/") for c in kids["categories"])


async def test_category_without_product_list_points_to_subcategories(client, api):
    api["/landing/v2"] = {"data": {"structure": [{"section_type": "hero_slider", "items": []}]}}
    api["/landing/v1/megamenu"] = fixture("megamenu.json")
    r = await client.call_tool("ss_category", {"path": "mobile"})
    assert r.is_error and "mobile/" in r.content[0].text


async def test_category_two_part_path_uses_category_brand_page(client, api):
    api["/landing/v2"] = {"data": {"structure": [{"section_type": "plp", "items": [], "pagination": {"total": 0}}]}}
    await client.call_tool("ss_category", {"path": "mobile/samsung", "page": 2})
    assert json.loads(api.calls[-1].content) == {
        "render": 4,
        "slug": "mobile",
        "slug_2": "samsung",
        "exclude_filters": True,
        "page_type": "category_brand",
        "referrer": "",
        "skip": 1,
    }


@pytest.mark.parametrize("status,hint", [(403, "Iranian"), (404, "nothing"), (500, "server error")])
async def test_http_errors_are_explained(client, api, status, hint):
    api["/search/v1"] = lambda request: httpx.Response(status, text="x")
    r = await client.call_tool("ss_search", {"query": "a"})
    assert r.is_error and hint in r.content[0].text


async def test_request_headers_match_the_sites_frontend(api):
    from snappshop_mcp import http

    api["/landing/v1/megamenu"] = {}
    await http.fetch("landing/v1/megamenu")
    h = api.calls[-1].headers
    assert h["accept"] == "*/*" and h["origin"] == "https://snappshop.ir" and h["referer"] == "https://snappshop.ir/"
    assert (h["sec-fetch-site"], h["sec-fetch-mode"], h["sec-fetch-dest"]) == ("same-site", "cors", "empty")
    assert h["s-area-ids"] == "29,197" and h["s-device-source"] == "shop" and h["x-origin"] == "https://snappshop.ir"
    assert h["s-session-id"] and h["uuid"]
    assert api.calls[-1].url.params["lat"] == "35.77331"


async def test_product_variants_are_named_and_empty_pages_explained(client, api):
    d = {"data": {"configurable_attribute": [{"title": "رنگ", "value": {"id": "c1", "title": "سبز"}}], "vendors": []}}
    d["data"]["variants"] = [
        {
            "attribute_ids": [{"attribute_id": "a", "attribute_value_id": "c1"}],
            "vendor": [{"price": 5, "special_price": 0}],
        }
    ]
    api["/products/v2/12345"] = d
    r = (await client.call_tool("ss_product", {"product": "12345"})).structured_content
    assert r["offers"][0]["variant"] == "رنگ: سبز" and r["price_from"] == 5
    api["/search/v1"] = {
        "data": {"structure": [{"section_type": "plp", "items": [], "pagination": {"total_pages": 3}}]}
    }
    r = (await client.call_tool("ss_search", {"query": "a", "page": 9})).structured_content
    assert "last page is 3" in r["note"]


async def test_seller_uses_the_vendor_page(client, api):
    api["/landing/v2"] = {"data": {"structure": [{"section_type": "plp", "items": [], "pagination": {"total": 0}}]}}
    await client.call_tool("ss_seller", {"seller_id": "gAkLXP", "sort": "cheapest"})
    assert json.loads(api.calls[-1].content) == {
        "render": 4,
        "sort": "x0QZq8",
        "slug": "gAkLXP",
        "exclude_filters": True,
        "page_type": "vendor",
        "referrer": "",
    }


FILTERS = [
    {"filter_id": "colors", "filter_type": "color_picker", "title": "رنگ", "items": [{"id": "c1", "title": "مشکی"}]},
    {
        "filter_id": "aD59bD",
        "filter_type": "radio_select",
        "title": "حافظه داخلی",
        "items": [{"id": "o1", "title": "128 گیگابایت"}, {"id": "o2", "title": "256 گیگابایت"}],
    },
]


def plp(filters=()):
    return {
        "data": {
            "structure": [
                {
                    "section_type": "plp",
                    "items": [],
                    "filter": list(filters),
                    "pagination": {"total": 5, "total_pages": 1},
                }
            ]
        }
    }


async def test_category_specs_and_colors_are_resolved_to_ids(client, api):
    api["/landing/v2"] = plp(FILTERS)
    await client.call_tool("ss_category", {"path": "mobile/samsung", "specs": ["حافظه داخلی=256"], "colors": ["مشکی"]})
    first, final = (json.loads(c.content) for c in api.calls[-2:])
    assert "exclude_filters" not in first and final["exclude_filters"] is True
    assert final["special_filters"] == [{"id": "aD59bD", "value": "o2"}] and final["colors"] == ["c1"]


async def test_unknown_spec_lists_the_choices(client, api):
    api["/landing/v2"] = plp(FILTERS)
    r = await client.call_tool("ss_category", {"path": "mobile/samsung", "specs": ["رم=8"]})
    assert r.is_error and "حافظه داخلی" in r.content[0].text


async def test_filters_tool_by_path_and_by_query(client, api):
    api["/landing/v2"] = plp(FILTERS)
    api["/search/v1"] = plp(FILTERS)
    a = (await client.call_tool("ss_filters", {"path": "mobile/samsung"})).structured_content
    b = (await client.call_tool("ss_filters", {"query": "گوشی"})).structured_content
    assert a["filters"][1]["options"] == ["128 گیگابایت", "256 گیگابایت"] and a["total"] == b["total"] == 5
    assert (await client.call_tool("ss_filters", {})).is_error


async def test_collection_uses_search_with_slug(client, api):
    api["/search/v1"] = plp()
    await client.call_tool("ss_collection", {"id": "q7x9ED", "page": 2})
    assert json.loads(api.calls[-1].content) == {"render": 4, "slug": "q7x9ED", "skip": 1}


async def test_promotions_show_sections_and_link_targets(client, api):
    item = {"id": "pn-O3MRmK", "href": "/product/snp-1043970074", "title": "x", "price": {"price": 5}}
    api["/landing/v2"] = {
        "data": {
            "structure": [
                {
                    "section_type": "flash_sales",
                    "title": "A",
                    "href": "/product-list/q7x9ED",
                    "end_date": "2026/11/05 00:00",
                    "items": [item],
                },
                {
                    "section_type": "hero_slider",
                    "items": [
                        {"title": "b", "href": "/campaign/supermarket"},
                        {"title": "c", "href": "/category/fashion"},
                    ],
                },
                {"section_type": "html", "items": []},
            ]
        }
    }
    r = (await client.call_tool("ss_promotions", {})).structured_content
    flash, banners = r["sections"]
    assert flash["collection_id"] == "q7x9ED" and flash["items"][0]["id"] == "O3MRmK" and flash["ends_at"]
    assert banners["links"] == [{"title": "b", "page": "campaign/supermarket"}, {"title": "c", "path": "fashion"}]
    assert (await client.call_tool("ss_promotions", {"page": "nonsense"})).is_error


async def test_brand_and_compare(client, api):
    resp = plp()
    resp["data"]["structure"].insert(0, {"section_type": "brand_info", "title": "الن نار"})
    api["/landing/v2"] = resp
    assert (await client.call_tool("ss_brand", {"slug": "/brand/elen-nar"})).structured_content["brand"] == "الن نار"
    assert json.loads(api.calls[-1].content)["slug"] == "elen-nar"
    api["/products/v2/11111"] = {
        "data": {
            "content": {"title_fa": "A"},
            "attributes": [{"title": "رم", "value": "4"}, {"title": "رنگ", "value": "x"}],
        }
    }
    api["/products/v2/22222"] = {
        "data": {
            "content": {"title_fa": "B"},
            "attributes": [{"title": "رم", "value": "8"}, {"title": "رنگ", "value": "x"}],
        }
    }
    r = (await client.call_tool("ss_compare", {"products": ["11111", "22222"]})).structured_content
    assert r["specs"] == {"رم": ["4", "8"]} and r["same_specs"] == 1


async def test_similar_defaults_to_the_sites_similar_section(client, api):
    api["/search/v1/similar-products"] = {"data": {"items": []}}
    await client.call_tool("ss_similar", {"id": "0WdnlY", "category_id": "x"})
    assert api.calls[-1].url.params["section"] == "CROSS_SELL"
    await client.call_tool("ss_similar", {"id": "0WdnlY", "category_id": "x", "kind": "accessories"})
    assert api.calls[-1].url.params["section"] == "RELATED_SELL"


async def test_reviews_report_total_and_pages(client, api):
    api["/reviews/v2/product/0WdnlY"] = {"data": [], "meta": {"pagination": {"total": 237, "total_pages": 24}}}
    r = (await client.call_tool("ss_reviews", {"id": "0WdnlY"})).structured_content
    assert (r["total"], r["pages"]) == (237, 24)


async def test_product_id_ignores_numbers_in_query_strings(client):
    r = await client.call_tool("ss_product", {"product": "https://snappshop.ir/search?query=12345678"})
    assert r.is_error and "product_id" in r.content[0].text


async def test_offers_carry_warranty_delivery_and_totals(client, api):
    v = {
        "vendor_id": "s1",
        "price": 9,
        "special_price": 0,
        "warranty_id": "w1",
        "vendor_rate": "excellent",
        "shipment": {"asap": {"enabled": True}, "normal": {"enabled": False}},
    }
    api["/products/v2/123456"] = {
        "data": {
            "content": {},
            "vendors": [{"id": "s1", "title": "S"}],
            "warranties": [{"id": "w1", "name": "گارانتی"}],
            "variants": [{"vendor": [v, {**v, "price": 8}]}],
        }
    }
    r = (await client.call_tool("ss_product", {"product": "123456"})).structured_content
    assert (r["offer_count"], r["seller_count"]) == (2, 1)
    first = r["offers"][0]
    assert (first["price"], first["warranty"], first["delivery"], first["seller_rating"]) == (
        8,
        "گارانتی",
        ["express"],
        "excellent",
    )


async def test_seller_and_brand_errors_name_the_input(client, api):
    api["/landing/v2"] = lambda request: httpx.Response(422, json={"message": "bad"})
    s = await client.call_tool("ss_seller", {"seller_id": "zzz"})
    b = await client.call_tool("ss_brand", {"slug": "nope"})
    assert "seller 'zzz'" in s.content[0].text and "brand page 'nope'" in b.content[0].text


async def test_seller_answer_names_the_seller(client, api):
    resp = plp()
    resp["data"]["structure"].insert(0, {"section_type": "vendor_info", "title": "داروخانه", "rating": 82})
    api["/landing/v2"] = resp
    r = (await client.call_tool("ss_seller", {"seller_id": "gAkLXP"})).structured_content
    assert (r["seller"], r["seller_score"]) == ("داروخانه", 82)


async def test_categories_follow_the_menu_tree_not_the_path_prefix(client, api):
    leaf = {"title": "اپل", "href": "/category/tablet/apple"}
    api["/landing/v1/megamenu"] = {
        "data": {
            "menus": [
                [
                    {
                        "title": "همه",
                        "href": "/categories",
                        "children": [
                            {
                                "title": "دیجیتال",
                                "href": "/category/digital",
                                "children": [
                                    {
                                        "title": "گروه",
                                        "href": "/category/digital",
                                        "children": [
                                            {"title": "همه کالاها", "href": "/category/digital/"},
                                            {
                                                "title": "تبلت",
                                                "href": "/category/tablet",
                                                "children": [
                                                    {"title": "تبلت", "href": "/category/tablet?sort=50aLgW"},
                                                    leaf,
                                                ],
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            ]
        }
    }
    kids = (await client.call_tool("ss_categories", {"parent": "digital"})).structured_content["categories"]
    assert kids == [{"title": "تبلت", "path": "tablet"}]
    sub = (await client.call_tool("ss_categories", {"parent": "tablet"})).structured_content["categories"]
    assert sub == [{"title": "اپل", "path": "tablet/apple"}]
