"""Portfolio valuation with explicit current-price and analysis coverage."""
from src.market import unpack_frame
from src.screener import finite


def analyze_holdings(holdings: list[dict], snapshot: dict) -> dict:
    rows = []
    invested = priced_basis = current_value = 0.0
    for holding in holdings:
        cost = holding["quantity"] * holding["average_price"]
        invested += cost
        stock = snapshot.get("stocks", {}).get(holding["ticker"], {})
        frame = unpack_frame(stock)
        price, trend = None, "Unassessed"
        data_date = stock.get("data_as_of")
        if not frame.empty and data_date == snapshot.get("as_of") and stock.get("quality") in {"Current", "Insufficient history"}:
            price = finite(frame["Close"].iloc[-1])
            if price is not None and price <= 0:
                price = None
            if price is not None:
                priced_basis += cost
                current_value += price * holding["quantity"]
                row = frame.iloc[-1]
                e200, adjusted = finite(row.get("EMA_200")), finite(row.get("AnalysisClose"))
                if e200 is not None and adjusted is not None:
                    trend = "Above 200 EMA" if adjusted > e200 else "At / below 200 EMA"
        value = price * holding["quantity"] if price is not None else None
        pnl = value - cost if value is not None else None
        rows.append({**holding, "invested": cost, "price": price, "value": value, "pnl": pnl,
                     "pnl_pct": pnl / cost * 100 if pnl is not None else None,
                     "trend": trend, "data_as_of": data_date or "Unavailable"})
    for row in rows:
        row["weight_pct"] = row["invested"] / invested * 100 if invested else 0
    return {"rows": rows, "invested": invested, "priced_basis": priced_basis, "priced_value": current_value,
            "priced_pnl": current_value - priced_basis, "priced_pnl_pct": (current_value / priced_basis - 1) * 100 if priced_basis else None,
            "price_coverage_pct": priced_basis / invested * 100 if invested else 0,
            "analysis_coverage_pct": sum(row["invested"] for row in rows if row["trend"] != "Unassessed") / invested * 100 if invested else 0,
            "unpriced": sum(row["price"] is None for row in rows), "unassessed": sum(row["trend"] == "Unassessed" for row in rows)}
