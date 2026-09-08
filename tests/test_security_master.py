from paper_live.security_master import Security, SecurityMaster, batch_symbols

def test_security_master_is_canonical_and_batches():
    m=SecurityMaster([Security("0001","One","KRX","KR","KRW"),Security("0002","Two","KRX","KR","KRW"),Security("0003","Three","KRX","KR","KRW")])
    assert m.symbols("krx")==("0001","0002","0003")
    assert batch_symbols(m,market="KRX",batch_size=2)==[("0001","0002"),("0003",)]
