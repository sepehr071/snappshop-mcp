<!-- mcp-name: io.github.sepehr071/snappshop-mcp -->

<div align="center">

<img src="https://raw.githubusercontent.com/sepehr071/snappshop-mcp/main/.github/banner.png" alt="snappshop-mcp: unofficial Snapp! Shop MCP server for Claude, Cursor and Copilot" width="100%">

# snappshop-mcp: Snapp! Shop MCP server for AI agents

**Let your AI agent shop around on Snapp! Shop (اسنپ&zwnj;شاپ).**<br>
An unofficial, read-only MCP server for [Snapp! Shop](https://snappshop.ir), the Snapp marketplace in Iran:<br>
search products, compare every seller's price in Toman, filter by specs, read buyer reviews and catch today's flash sales, all from Claude, Cursor or Copilot.

[![PyPI](https://img.shields.io/pypi/v/snappshop-mcp?color=2563eb)](https://pypi.org/project/snappshop-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/snappshop-mcp)](https://pypi.org/project/snappshop-mcp/)
[![CI](https://github.com/sepehr071/snappshop-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sepehr071/snappshop-mcp/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.sepehr071%2Fsnappshop--mcp-7c3aed)](https://registry.modelcontextprotocol.io/?q=snappshop-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/snappshop-mcp/blob/main/LICENSE)

[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=snappshop&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJzbmFwcHNob3AtbWNwIl19)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_snappshop--mcp-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=snappshop&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22snappshop-mcp%22%5D%7D)

[For AI agents](#for-ai-agents) · [Why](#why) · [What it can do](#what-it-can-do) · [Quick start](#quick-start) · [Tools](#tools) · [How it works](#how-it-works) · [Good to know](#good-to-know) · [FAQ](#faq) · [Configuration](#configuration) · [فارسی](#فارسی) · [Development](#development)

</div>

---

## For AI agents

- **What:** unofficial MCP server (model context protocol) for Snapp! Shop (snappshop.ir), a marketplace of many shops and pharmacies in Iran: electronics, phones, health and beauty, home, fashion. Queries in Persian match best; prices in Toman.
- **Install:** `uvx snappshop-mcp` or `claude mcp add snappshop -- uvx snappshop-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none, no API key or account (it uses the guest session the site gives every visitor). Snapp! Shop only accepts Iranian IPs: run it from Iran without a VPN, or set `SNAPPSHOP_MCP_PROXY` to an HTTP proxy that exits in Iran. System proxy settings are ignored.
- **Access:** read-only. No login, basket, orders or payment, so no confirmation is needed before calling any tool. All 13 tools carry `readOnlyHint: true`.
- **Tools:** 13: `ss_search`, `ss_suggest`, `ss_filters`, `ss_categories`, `ss_category`, `ss_brand`, `ss_product`, `ss_compare`, `ss_reviews`, `ss_similar`, `ss_seller`, `ss_promotions`, `ss_collection`.
  Typical sequence: `ss_search` -> `ss_product` (all sellers, cheapest first) -> `ss_reviews`. Browsing: `ss_categories` -> `ss_filters` -> `ss_category`.
- **Ids:** `product_id` (digits) goes to `ss_product` and `ss_compare`; `id` (6 characters) to `ss_reviews` and `ss_similar`; `seller_id` to `ss_seller`; `collection_id` to `ss_collection`.
- **Units:** prices in **Toman**, for delivery to Tehran, as the site shows them.
- **Use when:** comparing prices, sellers, specs and reviews of products sold in Iran, or watching flash sales.
- **Do not use when:** the user wants to order or pay, or is outside Iran with no Iranian IP or proxy (the site answers HTTP 403).
- **Output:** compact JSON. Null and empty fields are omitted (a missing `rating` = not rated). Lists are 12 items per page; the site caps a list at 10,000 items. Reviewer names are left out.
- **Machine-readable:** [`server.json`](https://github.com/sepehr071/snappshop-mcp/blob/main/server.json) and the
  [iran-mcp catalog](https://github.com/sepehr071/iran-mcp) once the server is listed there.

## Why

Snapp! Shop sells one product through many sellers at different prices, warranties and delivery terms. Finding the
best offer means opening product pages one by one. An agent with `snappshop-mcp` reads them all in seconds:

> **You:** Who sells the Samsung Galaxy A07 (64 GB) cheapest on Snapp! Shop, and with what warranty?
>
> **Agent:** *calls* `ss_search(query="Galaxy A07 64")` → `ss_product(product="25751584")`
>
> | Price (Toman) | Seller | Colour | Warranty |
> |---:|---|---|---|
> | **44,600,000** | دیجی لند سانا | سبز | گارانتی ۱۸ ماهه شرکتی |
> | **44,770,000** | سام پلاس | بنفش | گارانتی ۱۸ ماهه هماهنگ (داریا همراه) |
> | **45,500,000** | ویراوین | سبز | گارانتی ۱۸ ماهه شرکتی |
>
> 12 sellers in total, rating 4.3 from 370 ratings. Want the reviews with `ss_reviews`?

<sub>Real tool output from 2026-11-04; prices and stock change all the time. Prices are in Toman.</sub>

## What it can do

- **Search** products by name, with price range, brand, spec, colour, stock, discount and fast-delivery filters
- **Compare sellers**: every offer of a product with price, discount, stock, warranty, delivery method and seller rating
- **Compare products** side by side: price, rating and only the specs that differ
- **Browse** the category tree, brand pages and seller pages; `ss_filters` shows the real filters of a list
- **Read reviews** with scores, pros and cons, and find similar products
- **Catch deals**: flash sales with end times, campaign pages and every product in a promotion
- **Read-only by design**: no login, no basket, no orders, no payment

Example prompts:

- "Cheapest Samsung phone in stock, with 256 GB storage and a black colour."
- "Compare the Xiaomi Poco X7 Pro and the Galaxy A56: what differs in the specs?"
- "Which seller of this magnesium supplement has the lowest price, and what do buyers say?"
- "What flash sales end tonight on Snapp! Shop?"
- <span dir="rtl">ارزان&zwnj;ترین گوشی سامسونگ موجود با حافظه ۲۵۶ گیگابایت را پیدا کن.</span>
- <span dir="rtl">فروشنده&zwnj;های این محصول را با قیمت و گارانتی مقایسه کن.</span>
- <span dir="rtl">امروز چه فروش ویژه&zwnj;هایی در اسنپ&zwnj;شاپ هست؟</span>

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and **an Iranian IP address**
(Snapp! Shop blocks foreign IPs; see [FAQ](#faq)). No API key or account.

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add snappshop -- uvx snappshop-mcp
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Settings → Developer → Edit Config, then add:

```json
{
  "mcpServers": {
    "snappshop": { "command": "uvx", "args": ["snappshop-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Cursor</b></summary>

Click **Install in Cursor** above, or add the Claude Desktop block to `~/.cursor/mcp.json` (or `.cursor/mcp.json` in a project).
</details>

<details>
<summary><b>VS Code (Copilot agent mode)</b></summary>

Click **Install in VS Code** above, or add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "snappshop": { "type": "stdio", "command": "uvx", "args": ["snappshop-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Codex CLI</b></summary>

```bash
codex mcp add snappshop -- uvx snappshop-mcp
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.snappshop]
command = "uvx"
args = ["snappshop-mcp"]
```
</details>

<details>
<summary><b>Gemini CLI</b></summary>

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "snappshop": { "command": "uvx", "args": ["snappshop-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Windsurf</b></summary>

Add the Claude Desktop block to `~/.codeium/windsurf/mcp_config.json`.
</details>

<details>
<summary><b>Anything else</b></summary>

It's a standard stdio MCP server: run `uvx snappshop-mcp`, or `pip install snappshop-mcp` and run `snappshop-mcp`.
</details>

## Tools

All tools are read-only. Lists return 12 items per page (`page` starts at 1).

| Tool | What it does |
|---|---|
| `ss_search` | Find products by name; filters: price range, brands, specs, colours, in stock, discounted, fast delivery; sort |
| `ss_suggest` | Popular search phrases for a prefix, with popularity scores |
| `ss_filters` | Price range, colours, brands and spec filters (with options) of a category or a search |
| `ss_categories` | Category paths: the top level, or the children of one |
| `ss_category` | Products of a category or category-brand page, with the same filters as `ss_search` |
| `ss_brand` | Products of a brand page |
| `ss_product` | Specs, rating and every seller's offer (price, discount, stock, warranty, delivery, seller rating), cheapest first |
| `ss_compare` | 2-4 products side by side: price, rating, seller count and the specs that differ |
| `ss_reviews` | Buyer reviews: score, text, pros and cons, votes, date; with `total` and `pages` |
| `ss_similar` | Similar products, or accessories sold with the product |
| `ss_seller` | Products of one seller, with the seller's name and score |
| `ss_promotions` | Flash sales (with end times), carousels and campaign pages; links to the tool that opens each |
| `ss_collection` | Every product of one promotion from `ss_promotions` |

Filters use names, not ids: `specs=["حافظه داخلی=256 گیگابایت"]`, `colors=["مشکی"]`. Call `ss_filters` first to see
what a category offers.

## How it works

The server calls the same JSON API (`apix.snappshop.ir`) that the Snapp! Shop web app uses, with the guest token the
site hands to every visitor. Requests go out with a Chrome TLS fingerprint and the headers the site's own frontend
sends, so they look like normal browsing. One shared HTTP client caches reads for 60 seconds, limits concurrency,
retries timeouts and server errors, and refuses any host except `apix.snappshop.ir`.

Nothing is stored and nothing is sent anywhere else. There is no login: the server cannot see or change an account.

## Good to know

- **Iranian IPs only.** From abroad the site answers HTTP 403 ("turn off your VPN"). Use an Iranian connection or `SNAPPSHOP_MCP_PROXY`.
- **Prices are Toman**, as the site shows them, for delivery to Tehran. Stock and prices move during the day.
- **Totals** are capped at 10,000 by the site and can differ by one or two between calls.
- **A phrase nothing matches** falls back to unrelated products, so check the titles.
- **Top-level categories** (such as `mobile`) have no product list: pick a subcategory from `ss_categories`.
- **Reviewer names** are not returned.

## FAQ

**Does it need an API key or an account?** No. It uses the guest session every visitor gets.

**Can it buy something or add to the basket?** No. It is read-only by design.

**Why do I get HTTP 403?** The site only answers Iranian IPs. Run the server from Iran without a VPN, or set `SNAPPSHOP_MCP_PROXY` to an HTTP proxy that exits in Iran.

**Is this the same as snapp-mcp?** No. [snapp-mcp](https://github.com/sepehr071/snapp-mcp) covers Snappfood (restaurants) and SnappMarket (groceries); this server covers the Snapp! Shop marketplace.

**Which language should I ask in?** Persian matches best because titles and specs are Persian; English brand and model names work too.

**How do I filter a phone by storage?** Call `ss_filters(path="mobile/samsung")`, then `ss_category(path="mobile/samsung", specs=["حافظه داخلی=256 گیگابایت"])`.

## Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `SNAPPSHOP_MCP_PROXY` | no | unset | HTTP proxy for every request, e.g. `http://user:pass@host:port`. A comma-separated list is used one at a time: the next proxy takes over when one is blocked (403/429) or cannot connect |

<a id="فارسی"></a>

## فارسی: سرور MCP اسنپ&zwnj;شاپ

<div dir="rtl">

**snappshop-mcp** یک سرور MCP غیررسمی و فقط&zwnj;خواندنی برای اسنپ&zwnj;شاپ (بازار آنلاین اسنپ با هزاران فروشنده و داروخانه) در ایران است. این سرور به دستیار هوش مصنوعی شما (Claude، Cursor، Copilot و ...) اجازه می&zwnj;دهد در اسنپ&zwnj;شاپ جستجو کند، قیمت و گارانتی همهٔ فروشنده&zwnj;های یک کالا را مقایسه کند، مشخصات و نظرات خریداران را بخواند و فروش ویژه&zwnj;های فعال را پیدا کند.

- فقط خواندنی است: وارد حساب نمی&zwnj;شود، سبد خرید نمی&zwnj;سازد و سفارش ثبت نمی&zwnj;کند.
- قیمت&zwnj;ها به تومان هستند، همان&zwnj;طور که سایت نشان می&zwnj;دهد.
- روی سیستم خود شما اجرا می&zwnj;شود و به هیچ سرور واسطی داده نمی&zwnj;فرستد.
- نیازی به کلید API یا حساب کاربری ندارد.

**نصب در Claude Code:**

</div>

```bash
claude mcp add snappshop -- uvx snappshop-mcp
```

<div dir="rtl">

بعد بپرسید: «ارزان&zwnj;ترین گوشی سامسونگ موجود با حافظهٔ ۲۵۶ گیگابایت کدام است و کدام فروشنده ارسال سریع دارد؟»

**نکته:** سرور باید روی سیستمی با IP ایران و بدون VPN اجرا شود، چون اسنپ&zwnj;شاپ درخواست&zwnj;های خارج از ایران را مسدود می&zwnj;کند. اگر ناچار به VPN هستید، متغیر `SNAPPSHOP_MCP_PROXY` را روی یک پروکسی HTTP با خروجی ایران بگذارید.

**عبارت&zwnj;های پرجستجو:** اسنپ&zwnj;شاپ، خرید آنلاین، مقایسه قیمت، قیمت گوشی، مقایسه فروشنده، گارانتی، فروش ویژه، تخفیف، دستیار هوش مصنوعی، سرور MCP فارسی.

</div>

## Development

```bash
git clone https://github.com/sepehr071/snappshop-mcp && cd snappshop-mcp
uv sync
uv run python -m pytest            # offline, against recorded responses
uv run python -m pytest -m live    # real API (needs an Iranian IP)
uv run ruff check .
```

Tools live in `src/snappshop_mcp/shop.py`; each is a typed async function with a docstring that tells the agent when
to use it. Issues and PRs are welcome, especially new tools and fixes for API changes.

Releases: bump the version in `pyproject.toml` and `server.json`, then push a `v*` tag. GitHub Actions tests,
publishes to PyPI and the [MCP Registry](https://registry.modelcontextprotocol.io), and creates the GitHub Release.

## Related servers

- [iran-mcp](https://github.com/sepehr071/iran-mcp): catalog of all Iranian-service MCP servers
- [snapp-mcp](https://github.com/sepehr071/snapp-mcp): Snappfood and SnappMarket (restaurants and groceries)
- [digikala-mcp](https://github.com/sepehr071/digikala-mcp): Digikala product search and prices
- [torob-mcp](https://github.com/sepehr071/torob-mcp): price comparison across Iranian shops
- [basalam-mcp](https://github.com/sepehr071/basalam-mcp): handmade and local products on Basalam

## Disclaimer

Unofficial and not affiliated with or endorsed by Snapp. It is read-only: it only reads the public endpoints of the snappshop.ir
web app, which can change without notice. Please keep request rates reasonable.

## Author

<a href="https://www.linkedin.com/in/sepehr-radmard"><img src="https://raw.githubusercontent.com/sepehr071/iran-mcp/main/assets/author-banner.png" alt="Sepehr Radmard: open-source MCP servers for the Iranian web. LinkedIn: linkedin.com/in/sepehr-radmard" width="100%"></a>

Built and maintained by **Sepehr Radmard** (سپهر رادمرد). Connect on [LinkedIn](https://www.linkedin.com/in/sepehr-radmard) or follow [@sepehr071 on GitHub](https://github.com/sepehr071) for more MCP servers for Iranian websites, all listed in [iran-mcp](https://github.com/sepehr071/iran-mcp). If this saves you time, a star on the repo helps other people find it.

## License

[MIT](https://github.com/sepehr071/snappshop-mcp/blob/main/LICENSE)

If this saves you clicks, a star helps others find it.
