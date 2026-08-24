from agent.business_data import BUSINESS_INFO, PRODUCTS, find_product, format_catalog_for_prompt

EXPECTED_PRICES = {
    "L-type sofa": 42000,
    "Teak solid-wood king-size bed without box": 35000,
    "L-corner sofa": 35000,
    "Dining table": 32000,
    "U-shape sofa": 55000,
    "Double recliner": 42000,
    "Convertible sofa bed": 42000,
}


def test_product_count():
    assert len(PRODUCTS) == 7


def test_prices_match_spec():
    actual = {p.name: p.price_inr for p in PRODUCTS}
    assert actual == EXPECTED_PRICES


def test_business_info_fields():
    assert BUSINESS_INFO["name"] == "BVHomes Furniture"
    assert BUSINESS_INFO["phone"] == "7702 702 888"
    assert "Visakhapatnam" in BUSINESS_INFO["address"]


def test_catalog_prompt_has_no_currency_symbol():
    # ₹ symbol is deliberately excluded — TTS pronounces "rupees" more
    # reliably than the glyph. Regression-guard that choice.
    catalog_text = format_catalog_for_prompt()
    assert "₹" not in catalog_text
    assert "rupees" in catalog_text
    for name in EXPECTED_PRICES:
        assert name in catalog_text


def test_find_product_matches():
    assert find_product("l type sofa") is not None
    assert find_product("L-type sofa").price_inr == 42000


def test_find_product_no_match_returns_none():
    # Critical: unknown items must return None, not a guessed nearest product.
    assert find_product("wardrobe") is None
    assert find_product("TV unit") is None
