from datetime import date
from decimal import Decimal
from paper_live.corporate_actions import CorporateAction, CorporateActionBook

def test_split_is_kept_separate_from_prices_and_adjustment_factor():
    book=CorporateActionBook([CorporateAction("KRX","A",date(2026,8,28),"SPLIT",Decimal("2"),source="test")])
    assert book.adjustment_factor("KRX","A",date(2026,8,29))==Decimal("2")
    assert len(book.for_symbol("KRX","A"))==1
