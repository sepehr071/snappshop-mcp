"""Snapp! Shop tools: search, category lists, product detail with seller offers, reviews, similar items, deals."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .http import SITE, ApiError, fetch
from .registry import tool

SORTS = {
    "popular": "J0Wxq8",
    "cheapest": "x0QZq8",
    "priciest": "lgwWgo",
    "buyers_pick": "60rdDw",
    "bestselling": "50aLgW",
    "biggest_discount": "5DzQq4",
}
Sort = Annotated[
    Literal["popular", "cheapest", "priciest", "buyers_pick", "bestselling", "biggest_discount"] | None,
    Field(description="List order; default is the site's relevance order."),
]
MinPrice = Annotated[int | None, Field(ge=0, description="Lowest price in Toman (not Rial).")]
MaxPrice = Annotated[int | None, Field(ge=0, description="Highest price in Toman (not Rial).")]
Brands = Annotated[
    list[str] | None,
    Field(description="Brand ids from `brands` of an earlier answer."),
]
Page = Annotated[int, Field(ge=1, le=500, description="12 items per page.")]
Specs = Annotated[
    list[str] | None,
    Field(
        description="'filter=option' (name or id, from ss_filters), e.g. ['حافظه داخلی=256 گیگابایت']. One option per filter."
    ),
]
Colors = Annotated[list[str] | None, Field(description="Colour names or ids from ss_filters.")]


def _digits(href: str | None) -> int | None:
    m = re.search(r"/product/(?:snp-)?(\d+)", href or "")
    return int(m.group(1)) if m else None


def _card(i: dict) -> dict:
    p = i.get("price") or {}
    now = p.get("discounted_price") or p.get("price")
    st = i.get("state") or {}
    return {
        "id": (i.get("id") or "").removeprefix("pn-") or None,  # carousels prefix the hash id
        "product_id": _digits(i.get("href")),
        "title": i.get("title"),
        "price": now,
        "list_price": p.get("price") if now != p.get("price") else None,
        "discount_percent": p.get("discount") or None,
        "rating": st.get("rate") or None,
        "rating_count": st.get("rate_count") or None,
        "colors": [c.get("title") for c in i.get("colors") or []] or None,
        "badge": i.get("badge") or None,
        "sponsored": i.get("is_ads") or None,
        "url": f"{SITE}{i['href']}" if i.get("href") else None,
    }


def _list_body(
    sort: str | None,
    min_price: int | None,
    max_price: int | None,
    brands: list[str] | None,
    in_stock: bool,
    discounted: bool,
    express: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {"render": 4}
    if sort:
        body["sort"] = SORTS[sort]
    if min_price:
        body["min_price"] = min_price
    if max_price:
        body["max_price"] = max_price
    if brands:
        body["brands"] = brands
    if in_stock:
        body["is_available"] = True
    if discounted:
        body["has_discount"] = True
    if express:
        body["is_express"] = True
    return body


def _section(resp: dict) -> dict:
    """The product-list section of a search/landing answer, or {}."""
    return next((s for s in (resp.get("data") or {}).get("structure") or [] if s.get("section_type") == "plp"), {})


def _pick(wanted: str, options: list[dict], key: str, what: str) -> dict:
    """Match by id or title, exact first, then substring; fail with the choices."""
    w = wanted.strip().casefold()
    for test in (
        lambda o: w in (str(o.get("id", "")).casefold(), str(o.get(key, "")).casefold()),
        lambda o: bool(w) and w in str(o.get(key, "")).casefold(),
    ):
        hits = [o for o in options if test(o)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ToolError(f"'{wanted}' matches several {what}: " + ", ".join(str(o.get(key)) for o in hits[:8]) + ".")
    raise ToolError(f"No {what} '{wanted}'. Choices: " + ", ".join(str(o.get(key)) for o in options[:15]) + ".")


async def _apply_specs(path: str, body: dict, specs: list[str] | None, colors: list[str] | None) -> None:
    """Turn friendly spec/colour names into the ids the site sends; one extra call reads the list's filters."""
    if not specs and not colors:
        return
    probe = {k: v for k, v in body.items() if k not in ("skip", "exclude_filters")}
    filters = _section(await fetch(path, body=probe)).get("filter") or []
    chosen: dict[str, str] = {}
    for spec in specs or []:
        name, sep, option = spec.partition("=")
        if not sep:
            raise ToolError(f"Spec '{spec}' must look like 'filter=option' (see ss_filters).")
        f = _pick(
            name,
            [f for f in filters if f.get("items") and f["filter_id"] not in ("colors", "brands", "price")],
            "title",
            "filter",
        )
        chosen[f["filter_id"]] = _pick(option, f["items"], "title", f"option of '{f['title']}'")["id"]
    if chosen:
        body["special_filters"] = [{"id": k, "value": v} for k, v in chosen.items()]
    if colors:
        palette = next((f["items"] for f in filters if f.get("filter_id") == "colors"), None)
        if not palette:
            raise ToolError("This list has no colour filter.")
        body["colors"] = [_pick(c, palette, "title", "colour")["id"] for c in colors]


def _plp(resp: dict, page: int) -> dict:
    s = _section(resp)
    if not s:
        return {}
    pg = s.get("pagination") or {}
    out = {
        "total": pg.get("total"),
        "page": page,
        "pages": pg.get("total_pages"),
        "items": [_card(i) for i in s.get("items") or []],
    }
    if not out["items"] and page > 1:
        out["note"] = f"No items on page {page}; the last page is {pg.get('total_pages')}."
    if page == 1:
        brands = next((f for f in s.get("filter") or [] if f.get("filter_id") == "brands"), None)
        if brands:
            out["brands"] = [
                {"id": b["id"], "name": b.get("title"), "name_en": b.get("second_title")} for b in brands["items"][:25]
            ]
    return out


@tool("Search products")
async def ss_search(
    query: Annotated[str, Field(min_length=1, description="Persian or English, e.g. 'هدفون بلوتوثی'.")],
    sort: Sort = None,
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    brands: Brands = None,
    in_stock: Annotated[bool, Field(description="Only products that can be bought now.")] = False,
    discounted: Annotated[bool, Field(description="Only products with a discount.")] = False,
    express: Annotated[bool, Field(description="Only products with fast delivery.")] = False,
    specs: Specs = None,
    colors: Colors = None,
    page: Page = 1,
):
    """Search Snapp! Shop (اسنپ\u200cشاپ) products by name, with price, brand, spec, colour and delivery filters.

    Items carry `id` (ss_reviews / ss_similar) and `product_id` (ss_product); page 1 adds `brands`.
    An unmatched phrase returns unrelated items, so check titles.
    """
    body = {**_list_body(sort, min_price, max_price, brands, in_stock, discounted, express), "query": query}
    await _apply_specs("search/v1", body, specs, colors)
    if page > 1:
        body["skip"] = page - 1
    r = _plp(await fetch("search/v1", body=body), page)
    return r or {"total": 0, "items": []}


@tool("Search suggestions")
async def ss_suggest(query: Annotated[str, Field(min_length=1, description="Start of a search phrase.")]):
    """Complete a search phrase the way the site's search box does, most searched first."""
    d = (await fetch("search/v1/suggest", {"query": query, "limit": 8})).get("data") or {}
    terms = [
        {"term": c["term"], "score": c.get("score")}
        for c in d.get("completions") or []
        if c.get("term") and c["term"] != query
    ]
    return {"terms": terms, "categories": [c.get("title") or c for c in d.get("categories") or []]}


def _menu(resp: dict) -> list[dict]:
    """Flatten the mega menu into {title, path, level, parent} rows (path = what ss_category takes)."""
    rows: list[dict] = []

    def walk(nodes, level, parent):
        for n in nodes:
            if isinstance(n, list):
                walk(n, level, parent)
                continue
            m = re.match(r"/category/([^?#]+)", n.get("href") or "")
            path = m.group(1).strip("/") if m else parent  # links like 'mobile/' or 'tablet?sort=..' are the same page
            if m and level > 0 and path != parent and not any(r["path"] == path for r in rows):
                rows.append({"title": n.get("title"), "path": path, "level": level, "parent": parent})
            walk(n.get("children") or [], level + 1, path)

    walk(resp.get("data", {}).get("menus") or [], 0, None)
    return rows


@tool("Categories")
async def ss_categories(
    parent: Annotated[
        str | None,
        Field(description="Path such as 'mobile'; empty lists top-level categories."),
    ] = None,
):
    """List Snapp! Shop categories as `path` values that ss_category accepts.

    No argument: top level; then pass a path for its subcategories and brand pages.
    """
    rows = _menu(await fetch("landing/v1/megamenu"))
    if parent is None:
        return {"categories": [{"title": r["title"], "path": r["path"]} for r in rows if r["level"] == 1]}
    parent = parent.strip("/").removeprefix("category/")
    kids = [{"title": r["title"], "path": r["path"]} for r in rows if r["parent"] == parent]
    if not kids:
        raise ToolError(f"No subcategories under '{parent}'. Call ss_categories without an argument for the top level.")
    return {"parent": parent, "categories": kids}


def _category_body(path: str) -> dict[str, Any]:
    parts = [p for p in path.strip("/").removeprefix("category/").split("/") if p]
    if not 1 <= len(parts) <= 2:
        raise ToolError("path must have one or two parts, e.g. 'mobile/samsung' (see ss_categories).")
    body: dict[str, Any] = {"slug": parts[0], "exclude_filters": True, "page_type": "category", "referrer": ""}
    if len(parts) == 2:
        body.update({"slug_2": parts[1], "page_type": "category_brand"})
    return body


@tool("Category products")
async def ss_category(
    path: Annotated[
        str,
        Field(description="Path from ss_categories, one or two parts, e.g. 'mobile/samsung'."),
    ],
    sort: Sort = None,
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    in_stock: Annotated[bool, Field(description="Only products that can be bought now.")] = False,
    discounted: Annotated[bool, Field(description="Only products with a discount.")] = False,
    express: Annotated[bool, Field(description="Only products with fast delivery.")] = False,
    specs: Specs = None,
    colors: Colors = None,
    page: Page = 1,
):
    """List the products of one Snapp! Shop category or category-brand page, with sort, price, spec and colour filters.

    Use after ss_categories. A top-level path such as 'mobile' has no list: pick a subcategory.
    """
    body = _list_body(sort, min_price, max_price, None, in_stock, discounted, express)
    body.update(_category_body(path))
    await _apply_specs("landing/v2", body, specs, colors)
    if page > 1:
        body["skip"] = page - 1
    r = _plp(await fetch("landing/v2", body=body), page)
    if not r:
        top = body["slug"]
        subs = [x["path"] for x in _menu(await fetch("landing/v1/megamenu")) if x["parent"] == top]
        raise ToolError(f"'{path}' has no product list. Try one of: {', '.join(subs[:20]) or 'ss_categories'}.")
    return r


OFFER_CAP = 25  # offers listed cheapest first; offer_count / seller_count report the full numbers
DELIVERY = {
    "asap": "express",
    "normal": "normal",
    "ship_by_seller": "shipped by the seller",
    "fbm": "shipped from Snapp! Shop warehouse",
}


def _product_id(value: str | int) -> str:
    # bare digits, 'snp-<digits>' or a product URL; never a number from a query string
    m = re.fullmatch(r"\s*(?:snp-)?(\d{3,})\s*", str(value)) or re.search(r"/product/(?:snp-)?(\d+)", str(value))
    if not m:
        raise ToolError("Give the numeric product_id from ss_search, a 'snp-123...' id or a snappshop.ir product URL.")
    return m.group(1)


@tool("Product detail")
async def ss_product(
    product: Annotated[
        str,
        Field(description="`product_id` (digits), 'snp-<digits>' or a product URL."),
    ],
):
    """Get one product: specs, rating, and every seller's price, stock and delivery.

    Offers cheapest first. `id` and `category_id` feed ss_reviews / ss_similar.
    """
    d = (await fetch(f"products/v2/{_product_id(product)}")).get("data") or {}
    sellers = {v["id"]: v.get("title") for v in d.get("vendors") or []}
    # configurable_attribute lists each option value once (colour, size, ...); variants refer to them by id.
    names = {
        (a.get("value") or {}).get("id"): f"{a.get('title')}: {a['value'].get('title')}"
        for a in d.get("configurable_attribute") or []
        if a.get("value")
    }
    warranties = {w.get("id"): w.get("name") for w in d.get("warranties") or []}
    offers = []
    for var in d.get("variants") or []:
        for v in var.get("vendor") or []:
            price = v.get("special_price") or v.get("price")
            if not price:
                continue
            ship = v.get("shipment") or {}
            offers.append(
                {
                    "seller": sellers.get(v.get("vendor_id")),
                    "seller_id": v.get("vendor_id"),
                    "price": price,
                    "list_price": v.get("price") if price != v.get("price") else None,
                    "discount_percent": v.get("special_price_percent_discount") or None,
                    "stock": v.get("stock"),
                    "seller_rating": v.get("vendor_rate"),
                    "warranty": warranties.get(v.get("warranty_id")),
                    "delivery": [label for key, label in DELIVERY.items() if (ship.get(key) or {}).get("enabled")]
                    or None,
                    "variant": ", ".join(
                        f"{names[a['attribute_value_id']]}"
                        for a in var.get("attribute_ids") or []
                        if a.get("attribute_value_id") in names
                    )
                    or None,
                }
            )
    offers.sort(key=lambda o: o["price"])
    st = d.get("state") or {}
    c = d.get("content") or {}
    cats = [x for x in d.get("categories") or [] if x.get("id")]
    brand = d.get("brand") or {}
    return {
        "id": d.get("id"),
        "title": c.get("title_fa"),
        "title_en": c.get("title_en"),
        "brand": brand.get("title_fa") or brand.get("title_en"),
        "categories": [x.get("title") for x in cats],
        "category_id": d.get("similar_category_id"),
        "rating": st.get("star_rate"),
        "rating_count": st.get("rate_count"),
        "review_count": st.get("comments_count"),
        "price_from": offers[0]["price"] if offers else None,
        "offer_count": len(offers),
        "seller_count": len({o["seller_id"] for o in offers}),
        "offers": offers[:OFFER_CAP],
        "specs": {a["title"]: a["value"] for a in d.get("attributes") or [] if a.get("title")},
        "description": (c.get("description") or "")[:800] or None,
        "images": [i["src"] for i in (d.get("images") or [])[:6] if i.get("src")],
        "installment": (d.get("snapp_pay_installment") or {}).get("description"),
        "warning": d.get("warning_description"),
    }


@tool("Product reviews")
async def ss_reviews(
    id: Annotated[str, Field(description="Product `id` (6 characters), not the numeric product_id.")],
    page: Annotated[int, Field(ge=1, le=100, description="10 reviews per page.")] = 1,
):
    """Read buyers' reviews of a product: score, title, text, pros and cons, helpful votes and date.

    Reviewer names are left out.
    """
    resp = await fetch(f"reviews/v2/product/{id}", {"page": page, "per_page": 10})
    out = []
    for r in resp.get("data") or []:
        out.append(
            {
                "score": r.get("point"),
                "title": r.get("title"),
                "text": r.get("comment"),
                "pros": r.get("advantages"),
                "cons": r.get("disadvantages"),
                "bought": r.get("is_bought"),
                "seller": (r.get("bought_vendor") or {}).get("name"),
                "likes": r.get("likes"),
                "dislikes": r.get("dislikes"),
                "date": (r.get("created_at") or "")[:10],
                "reply": (r.get("reply") or None) and str(r["reply"])[:300],
            }
        )
    pg = (resp.get("meta") or {}).get("pagination") or {}
    return {"page": page, "total": pg.get("total"), "pages": pg.get("total_pages"), "reviews": out}


@tool("Similar products")
async def ss_similar(
    id: Annotated[str, Field(description="Product `id` (6 characters).")],
    category_id: Annotated[str, Field(description="`category_id` from ss_product.")],
    kind: Annotated[
        Literal["similar", "accessories"],
        Field(description="'similar' = alternatives; 'accessories' = cases, glass, etc."),
    ] = "similar",
):
    """Find alternatives to a product that Snapp! Shop shows under 'similar products'.

    Items have the same fields as ss_search.
    """
    section = "CROSS_SELL" if kind == "similar" else "RELATED_SELL"
    resp = await fetch("search/v1/similar-products", {"section": section, "product_id": id, "category_id": category_id})
    return {"items": [_card(i) for i in (resp.get("data") or {}).get("items") or []]}


@tool("Seller products")
async def ss_seller(
    seller_id: Annotated[str, Field(description="`seller_id` from an ss_product offer.")],
    sort: Sort = None,
    page: Page = 1,
):
    """List the products one seller (فروشنده) offers on Snapp! Shop."""
    body = _list_body(sort, None, None, None, False, False, False)
    # The seller page itself (landing/v2, page_type vendor) lists in the site's order; search/v1 with a vendor filter differs.
    body.update({"slug": seller_id, "exclude_filters": True, "page_type": "vendor", "referrer": ""})
    if page > 1:
        body["skip"] = page - 1
    try:
        resp = await fetch("landing/v2", body=body)
    except ApiError as e:
        if e.status in (400, 404, 422):
            raise ToolError(f"No seller '{seller_id}'. Use a seller_id from the offers in ss_product.") from e
        raise
    r = _plp(resp, page)
    if not r:
        raise ToolError(f"No products found for seller '{seller_id}'. Check the id in ss_product offers.")
    info = next((s for s in resp["data"]["structure"] if s.get("section_type") == "vendor_info"), {})
    return {"seller": info.get("title"), "seller_score": info.get("rating"), **r}


def _filter_view(f: dict, limit: int = 40) -> dict:
    out = {"filter": f.get("title"), "id": f.get("filter_id"), "type": f.get("filter_type")}
    items = f.get("items") or []
    if f.get("filter_type") == "range_select" and items:
        rng = items[0]
        out["min"], out["max"] = (
            (rng.get("from") or {}).get("minimum_value"),
            (rng.get("to") or {}).get("maximum_value"),
        )
    else:
        out["options"] = [i.get("title") for i in items[:limit]]
        if len(items) > limit:
            out["more_options"] = len(items) - limit
    return out


@tool("List filters")
async def ss_filters(
    path: Annotated[str | None, Field(description="Category path such as 'mobile/samsung'.")] = None,
    query: Annotated[str | None, Field(description="Or a search phrase.")] = None,
):
    """Show the filters Snapp! Shop offers for a category or search: price range, colours, brands and spec filters.

    Give `path` or `query`. Call before using specs / colors / brands.
    """
    if bool(path) == bool(query):
        raise ToolError("Give exactly one of path or query.")
    if path:
        body = {"render": 4, **_category_body(path)}
        body.pop("exclude_filters")
        s = _section(await fetch("landing/v2", body=body))
    else:
        s = _section(await fetch("search/v1", body={"render": 4, "query": query}))
    if not s:
        raise ToolError(f"'{path or query}' has no product list, so no filters. Pick a subcategory (ss_categories).")
    flt = s.get("filter") or []
    brands = next((f for f in flt if f.get("filter_id") == "brands"), None)
    return {
        "total": (s.get("pagination") or {}).get("total"),
        "brands": [{"id": b["id"], "name": b.get("title")} for b in (brands or {}).get("items", [])[:40]],
        "filters": [_filter_view(f) for f in flt if f.get("filter_id") != "brands"],
    }


@tool("Brand page")
async def ss_brand(
    slug: Annotated[str, Field(description="Slug from snappshop.ir/brand/<slug>, e.g. 'samsung'.")],
    sort: Sort = None,
    page: Page = 1,
):
    """List the products of one brand page on Snapp! Shop.

    For a brand inside a category use ss_category.
    """
    body = _list_body(sort, None, None, None, False, False, False)
    slug = slug.strip("/").removeprefix("brand/")
    body.update({"slug": slug, "exclude_filters": True, "page_type": "brand", "referrer": ""})
    if page > 1:
        body["skip"] = page - 1
    try:
        resp = await fetch("landing/v2", body=body)
    except ApiError as e:
        if e.status in (400, 404, 422):
            raise ToolError(f"No brand page '{slug}'. Brand slugs are in snappshop.ir/brand/<slug> links.") from e
        raise
    r = _plp(resp, page)
    if not r:
        raise ToolError(f"No brand page '{slug}'.")
    info = next((s for s in resp["data"]["structure"] if s.get("section_type") == "brand_info"), {})
    return {"brand": info.get("title"), **r}


@tool("Collection products")
async def ss_collection(
    id: Annotated[str, Field(description="`collection_id` from ss_promotions.")],
    sort: Sort = None,
    page: Page = 1,
):
    """List every product of one promotion collection (flash sale, carousel, 'see all' list) from ss_promotions."""
    body = _list_body(sort, None, None, None, False, False, False)
    body["slug"] = id
    if page > 1:
        body["skip"] = page - 1
    try:
        r = _plp(await fetch("search/v1", body=body), page)
    except ApiError as e:
        if e.status in (400, 404, 422):
            raise ToolError(f"No collection '{id}'. Get ids from ss_promotions.") from e
        raise
    if not r:
        raise ToolError(f"No collection '{id}'. Get ids from ss_promotions.")
    r.pop("brands", None)
    return r


def _collection_id(href: str | None) -> str | None:
    m = re.match(r"/product-list/([^/?]+)", href or "")
    return m.group(1) if m else None


def _link(href: str) -> dict[str, str | None]:
    """Say which tool takes a banner or menu link: category path, promotion page, brand slug or collection id."""
    m = re.match(r"/(category|campaign|landing|product-category|brand)/([^?#]+)", href)
    if not m:
        return {"collection_id": _collection_id(href)} if _collection_id(href) else {"href": href}
    kind, rest = m.groups()
    if kind == "category":
        return {"path": rest}
    if kind == "brand":
        return {"brand": rest}
    return {"page": f"{'collection' if kind == 'product-category' else kind}/{rest}"}


@tool("Promotions")
async def ss_promotions(
    page: Annotated[
        str,
        Field(
            description="'home', 'campaign/<slug>', 'landing/<slug>' or 'collection/<slug>' (slugs from site links)."
        ),
    ] = "home",
):
    """Show what Snapp! Shop is promoting: flash sales with end times, carousels, campaign pages and top products.

    Product sections carry a `collection_id` for ss_collection.
    """
    kind, _, slug = page.strip("/").partition("/")
    body: dict[str, Any] = {"render": 4, "referrer": ""}
    if kind == "home" and not slug:
        body["page_type"] = "home"
    elif kind in ("campaign", "landing", "collection") and slug:
        body.update({"page_type": "product_category" if kind == "collection" else kind, "slug": slug})
    else:
        raise ToolError("page must be 'home', 'campaign/<slug>', 'landing/<slug>' or 'collection/<slug>'.")
    resp = await fetch("landing/v2", body=body)
    sections = []
    for s in (resp.get("data") or {}).get("structure") or []:
        items = s.get("items") or []
        kind_ = s["section_type"]
        if not items:
            continue
        if kind_ in ("flash_sales", "product_carousel", "product_collection"):
            sections.append(
                {
                    "type": kind_,
                    "title": (s.get("title") or "").replace("\u200c", " ").strip() or None,
                    "collection_id": _collection_id(s.get("href")),
                    "ends_at": s.get("end_date") if kind_ == "flash_sales" else None,
                    "items": [_card(i) for i in items[:6]],
                    "item_count": len(items),
                }
            )
        elif kind_ in ("category", "hero_slider", "grid_banner"):
            links = [{"title": i["title"], **_link(i["href"])} for i in items if i.get("title") and i.get("href")]
            if links:
                sections.append({"type": kind_, "title": s.get("title"), "links": links[:12]})
    if not sections:
        raise ToolError(f"Nothing promoted on '{page}' (wrong slug, or the page is empty).")
    return {"page": page, "sections": sections}


@tool("Compare products")
async def ss_compare(
    products: Annotated[
        list[str],
        Field(min_length=2, max_length=4, description="product_id, 'snp-<digits>' or URL."),
    ],
):
    """Compare 2-4 products side by side: price, rating, seller count and the specs that differ.

    `specs` lists only differing rows, in product order.
    """
    cards = [await ss_product(p) for p in products]
    keys = list(dict.fromkeys(k for c in cards for k in c["specs"]))
    rows = {k: [c["specs"].get(k) for c in cards] for k in keys}
    # a row only one product has (a phone against a non-phone) says nothing about a difference
    diff = {k: v for k, v in rows.items() if sum(x is not None for x in v) > 1 and len(set(v)) > 1}
    return {
        "products": [
            {
                "title": c.get("title"),
                "id": c.get("id"),
                "price_from": c.get("price_from"),
                "rating": c.get("rating"),
                "rating_count": c.get("rating_count"),
                "sellers": c["seller_count"],
            }
            for c in cards
        ],
        "specs": diff,
        "same_specs": sum(len(set(v)) == 1 for v in rows.values()),
        "only_one_has": sum(sum(x is not None for x in v) == 1 for v in rows.values()),
    }
