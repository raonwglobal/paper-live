from paper_live.features import DailyFeatureEngine

def test_features_are_point_in_time_safe():
    engine=DailyFeatureEngine()
    rows=[
      {"market":"KRX","symbol":"A","trade_date":"2026-08-27","close":100,"volume":1000,"available_at":"2026-08-27T18:00:00+09:00"},
      {"market":"KRX","symbol":"A","trade_date":"2026-08-28","close":110,"volume":2000,"available_at":"2026-08-28T18:00:00+09:00"},
      {"market":"KRX","symbol":"A","trade_date":"2026-08-29","close":200,"volume":3000,"available_at":"2026-08-29T18:00:00+09:00"},
    ]
    out=engine.build(rows,decision_time="2026-08-28T19:00:00+09:00")
    assert len(out)==2
    assert all(x["trade_date"]!="2026-08-29" for x in out)
    assert out[-1]["return_1d"]==0.1
